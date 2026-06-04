"""
View Qdrant chunk data. Supports both embedded-local and HTTP (Docker) modes.

Usage:
    python view_chunks.py                           # embedded mode (stop backend first!)
    python view_chunks.py --url http://localhost:6333  # HTTP mode (start Docker first)
    python view_chunks.py --stats-only              # summary only
    python view_chunks.py --doc-id X                # filter by doc_id
    python view_chunks.py --kb-name X               # filter by kb_name
    python view_chunks.py --limit 5                 # show first 5 chunks
    python view_chunks.py --full-text               # show full chunk text
"""

import argparse
import sys
import json
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any

COLLECTION = "rag_knowledge_base"
LOCAL_PATH = "./data/qdrant"


# ── HTTP API client (no qdrant_client dependency) ──

class QdrantHTTP:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def _req(self, path: str, method: str = "GET", body: dict | None = None) -> dict:
        url = f"{self.base_url}/{path.lstrip('/')}"
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            print(f"[HTTP {e.code}] {e.reason}")
            return {}
        except urllib.error.URLError as e:
            print(f"[ERROR] Cannot connect to Qdrant at {self.base_url}")
            print("Make sure Qdrant Docker is running: docker-compose up -d")
            sys.exit(1)

    def collection_exists(self) -> bool:
        resp = self._req("/collections")
        return COLLECTION in resp.get("result", {}).get("collections", [])

    def get_collection_info(self) -> dict:
        return self._req(f"/collections/{COLLECTION}").get("result", {})

    def count(self, kb_name: str | None = None) -> int:
        body = {}
        if kb_name:
            body["filter"] = {
                "must": [{"key": "kb_name", "match": {"value": kb_name}}]
            }
        return self._req(f"/collections/{COLLECTION}/points/count", method="POST", body=body).get("result", {}).get("count", 0)

    def scroll(self, limit: int = 100, kb_name: str | None = None,
               doc_id: str | None = None, with_payload: bool = True) -> list[dict]:
        body: dict[str, Any] = {"limit": limit, "with_payload": with_payload, "with_vector": False}
        must: list[dict] = []
        if kb_name:
            must.append({"key": "kb_name", "match": {"value": kb_name}})
        if doc_id:
            must.append({"key": "doc_id", "match": {"value": doc_id}})
        if must:
            body["filter"] = {"must": must}
        return self._req(f"/collections/{COLLECTION}/points/scroll", method="POST", body=body).get("result", {}).get("points", [])


# ── Stats ──

def show_stats_embedded(client) -> None:
    if not client.collection_exists(COLLECTION):
        print(f"Collection '{COLLECTION}' does not exist.")
        return

    info = client.get_collection(COLLECTION)
    total = client.count(collection_name=COLLECTION).count
    print_stats_header(total, info.config.params.vectors)

    if total == 0:
        return

    scroll_result = client.scroll(
        collection_name=COLLECTION,
        with_payload=["kb_name", "doc_id", "filename"],
        limit=total,
    )
    print_doc_summary(scroll_result[0])


def show_stats_http(http: QdrantHTTP) -> None:
    if not http.collection_exists():
        print(f"Collection '{COLLECTION}' does not exist.")
        return

    info = http.get_collection_info()
    total = http.count()
    print_stats_header(total, info.get("config", {}).get("params", {}).get("vectors", {}))
    print(f"  (showing top 1000 chunks summary — HTTP scroll is paginated)")
    print("=" * 60)

    if total == 0:
        return
    points = http.scroll(limit=min(total, 1000), with_payload=True)
    print_doc_summary(points)


def print_stats_header(total: int, vectors_config) -> None:
    print("=" * 60)
    print(f"Collection: {COLLECTION}")
    print(f"Total chunks: {total}")
    print(f"Vectors config: {vectors_config}")
    print("=" * 60)


def print_doc_summary(points: list) -> None:
    kb_counts: dict[str, int] = {}
    doc_counts: dict[str, tuple[str, int]] = {}
    for p in points:
        payload = p.payload if hasattr(p, 'payload') else p.get("payload", {})
        kb = payload.get("kb_name", "unknown")
        doc_id = payload.get("doc_id", "unknown")
        filename = payload.get("filename", "unknown")
        kb_counts[kb] = kb_counts.get(kb, 0) + 1
        if doc_id not in doc_counts:
            doc_counts[doc_id] = (filename, 0)
        doc_counts[doc_id] = (filename, doc_counts[doc_id][1] + 1)

    print(f"\nKnowledge bases ({len(kb_counts)}):")
    for kb, cnt in sorted(kb_counts.items()):
        print(f"  [{kb}] {cnt} chunks")

    print(f"\nDocuments ({len(doc_counts)}):")
    for doc_id, (fname, cnt) in sorted(doc_counts.items()):
        print(f"  [{doc_id[:8]}...] {fname} — {cnt} chunks")


# ── Chunk display ──

def show_chunks_embedded(client, kb_name: str | None, doc_id: str | None,
                         limit: int, show_full_text: bool) -> None:
    from qdrant_client.http import models as qmodels

    if not client.collection_exists(COLLECTION):
        print(f"Collection '{COLLECTION}' does not exist.")
        return

    must_conditions = []
    if kb_name:
        must_conditions.append(qmodels.FieldCondition(key="kb_name", match=qmodels.MatchValue(value=kb_name)))
    if doc_id:
        must_conditions.append(qmodels.FieldCondition(key="doc_id", match=qmodels.MatchValue(value=doc_id)))
    q_filter = qmodels.Filter(must=must_conditions) if must_conditions else None

    scroll_limit = limit if limit > 0 else 99999
    scroll_result = client.scroll(
        collection_name=COLLECTION, with_payload=True, with_vectors=False,
        limit=scroll_limit, scroll_filter=q_filter,
    )
    print_chunks(scroll_result[0], show_full_text)


def show_chunks_http(http: QdrantHTTP, kb_name: str | None, doc_id: str | None,
                     limit: int, show_full_text: bool) -> None:
    if not http.collection_exists():
        print(f"Collection '{COLLECTION}' does not exist.")
        return

    scroll_limit = limit if limit > 0 else 1000
    points = http.scroll(limit=scroll_limit, kb_name=kb_name, doc_id=doc_id, with_payload=True)
    if limit == 0:
        print(f"\n(Showing up to 1000 chunks via HTTP. Use --limit N to narrow down.)")
    print_chunks(points, show_full_text)


def print_chunks(points: list, show_full_text: bool) -> None:
    if not points:
        print("No chunks found.")
        return

    print(f"\nShowing {len(points)} chunks:")
    print("=" * 60)

    for i, p in enumerate(points):
        payload = p.payload if hasattr(p, 'payload') else p.get("payload", {})
        pid = p.id if hasattr(p, 'id') else p.get("id", "?")
        text = payload.get("text", "")
        display_text = text if show_full_text else text[:200] + ("..." if len(text) > 200 else "")

        print(f"[{i + 1}] point_id: {pid}")
        print(f"    doc_id:    {payload.get('doc_id', '')}")
        print(f"    filename:  {payload.get('filename', '')}")
        print(f"    kb_name:   {payload.get('kb_name', '')}")
        print(f"    chunk_idx: {payload.get('chunk_index', '')}")
        ch_title = payload.get('chapter_title', '') or '(none)'
        ch_idx = payload.get('chapter_index', -1)
        print(f"    chapter:   {ch_title} (idx={ch_idx})")
        print(f"    text:      {display_text}")
        if payload.get("prev_chunk_text"):
            print(f"    prev:      {payload['prev_chunk_text'][:80]}...")
        if payload.get("next_chunk_text"):
            print(f"    next:      {payload['next_chunk_text'][:80]}...")
        print()


# ── Main ──

def main() -> None:
    parser = argparse.ArgumentParser(description="View Qdrant chunk data")
    parser.add_argument("--url", type=str, default="", help="Qdrant REST URL (HTTP mode)")
    parser.add_argument("--path", type=str, default=LOCAL_PATH, help="Qdrant local path (embedded mode)")
    parser.add_argument("--stats-only", action="store_true", help="Show summary stats only")
    parser.add_argument("--doc-id", type=str, help="Filter by document ID")
    parser.add_argument("--kb-name", type=str, help="Filter by knowledge base name")
    parser.add_argument("--limit", type=int, default=0, help="Max chunks to show")
    parser.add_argument("--full-text", action="store_true", help="Show full chunk text (no truncation)")
    args = parser.parse_args()

    if args.url:
        # ── HTTP mode ──
        http = QdrantHTTP(args.url)
        show_stats_http(http)
        if not args.stats_only:
            show_chunks_http(http, args.kb_name, args.doc_id, args.limit, args.full_text)
    else:
        # ── Embedded mode ──
        try:
            from qdrant_client import QdrantClient
        except ImportError:
            print("[ERROR] qdrant_client not installed. Options:")
            print("  1. pip install qdrant_client")
            print("  2. Use HTTP mode: python view_chunks.py --url http://localhost:6333")
            sys.exit(1)

        try:
            client = QdrantClient(path=args.path)
        except RuntimeError as e:
            if "already accessed" in str(e):
                print("[ERROR] Embedded Qdrant storage is locked (backend is running).")
                print("Options:")
                print("  1. Stop the backend process, then run this script again.")
                print("  2. Or use HTTP mode with Docker Qdrant:")
                print("       docker-compose up -d")
                print(f"       python view_chunks.py --url http://localhost:6333")
                sys.exit(1)
            raise

        show_stats_embedded(client)
        if not args.stats_only:
            show_chunks_embedded(client, args.kb_name, args.doc_id, args.limit, args.full_text)


if __name__ == "__main__":
    main()
