from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.config import settings

logger = logging.getLogger(__name__)

DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "bm25"

# Shared client for embedded mode — Qdrant local storage only allows ONE client instance
_shared_client: QdrantClient | None = None
_shared_sparse_model: Any = None
_shared_sparse_model_lock: Any = None


def _get_shared_client() -> QdrantClient:
    global _shared_client
    if _shared_client is None:
        if settings.qdrant_url and not settings.qdrant_local_path:
            _shared_client = QdrantClient(url=settings.qdrant_url)
        elif settings.qdrant_local_path:
            _shared_client = QdrantClient(path=settings.qdrant_local_path)
        else:
            _shared_client = QdrantClient(url=settings.qdrant_url)
    return _shared_client


def _get_sparse_model():
    global _shared_sparse_model
    if _shared_sparse_model is None:
        try:
            from fastembed import SparseTextEmbedding
            _shared_sparse_model = SparseTextEmbedding(model_name="Qdrant/bm25")
        except Exception:
            logger.warning(
                "Failed to load BM25 sparse model (network issue?). "
                "Falling back to dense-only search.",
                exc_info=True,
            )
            _shared_sparse_model = False  # sentinel: tried and failed
    return _shared_sparse_model if _shared_sparse_model is not False else None


@dataclass
class ChunkRecord:
    doc_id: str
    filename: str
    kb_name: str
    chunk_index: int
    text: str
    chapter_title: str = ""
    chapter_index: int = -1
    prev_chunk_text: str = ""
    next_chunk_text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchHit:
    chunk_id: str
    doc_id: str
    filename: str
    text: str
    score: float
    prev_text: str = ""
    next_text: str = ""
    chapter_title: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


def _build_filter(kb_name: str | None = None) -> qmodels.Filter | None:
    if kb_name:
        return qmodels.Filter(
            must=[
                qmodels.FieldCondition(
                    key="kb_name", match=qmodels.MatchValue(value=kb_name)
                )
            ]
        )
    return None


class Retriever:
    def __init__(
        self,
        url: str | None = None,
        collection: str | None = None,
        local_path: str | None = None,
    ):
        self.collection_name = collection or settings.qdrant_collection
        self.vector_dim = settings.embed_dim
        self._client = _get_shared_client()

    @property
    def client(self) -> QdrantClient:
        return self._client

    def _get_sparse_model(self):
        """Lazy-load the BM25 sparse embedding model via fastembed."""
        return _get_sparse_model()

    def _encode_sparse(self, texts: list[str]) -> list[tuple[list[int], list[float]]]:
        """Generate BM25 sparse vectors for a batch of texts.

        Returns empty list ([( [], [] ), ...]) on failure — callers fall back to dense-only.
        """
        model = self._get_sparse_model()
        if model is None:
            return [([], []) for _ in texts]
        results: list[tuple[list[int], list[float]]] = []
        for embedding in model.embed(texts, batch_size=len(texts)):
            results.append((embedding.indices.tolist(), embedding.values.tolist()))
        return results

    def ensure_collection(self) -> None:
        """Create collection if absent; warn + recreate if dense dimension changed."""
        if self._client.collection_exists(self.collection_name):
            info = self._client.get_collection(self.collection_name)
            # Check dense vector dimension (handles both named and unnamed configs)
            dense_config = info.config.params.vectors
            if isinstance(dense_config, dict):
                vector_params = dense_config.get(DENSE_VECTOR_NAME)
                if vector_params is not None:
                    current_dim = vector_params.size
                else:
                    # Old unnamed collection — recreate anyway
                    current_dim = -1
            else:
                current_dim = dense_config.size  # type: ignore[union-attr]

            if current_dim != self.vector_dim:
                logger.warning(
                    f"Collection '{self.collection_name}' dim={current_dim}, "
                    f"but embed_dim={self.vector_dim}. Recreating collection (existing data will be lost)."
                )
                self._client.delete_collection(self.collection_name)

        if not self._client.collection_exists(self.collection_name):
            self._client.create_collection(
                collection_name=self.collection_name,
                vectors_config={
                    DENSE_VECTOR_NAME: qmodels.VectorParams(
                        size=self.vector_dim,
                        distance=qmodels.Distance.COSINE,
                    ),
                },
                sparse_vectors_config={
                    SPARSE_VECTOR_NAME: qmodels.SparseVectorParams(),
                },
            )
            logger.info(
                f"Created collection '{self.collection_name}' "
                f"with dense({self.vector_dim}D) + sparse(BM25) vectors."
            )

    # ── Dense-only search (kept for backward compat / when BM25 model is unavailable) ──

    async def search(
        self,
        query_vector: list[float],
        top_k: int = 5,
        kb_name: str | None = None,
    ) -> list[SearchHit]:
        """Pure dense vector search (no BM25)."""
        self.ensure_collection()
        results = self._client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            using=DENSE_VECTOR_NAME,
            limit=top_k,
            query_filter=_build_filter(kb_name),
        )
        return self._hits_from_results(results)

    # ── Hybrid search (dense + BM25 with RRF fusion) ──

    async def hybrid_search(
        self,
        query_vector: list[float],
        query_text: str,
        top_k: int = 5,
        kb_name: str | None = None,
    ) -> list[SearchHit]:
        """Dense + BM25 hybrid search with Reciprocal Rank Fusion."""
        self.ensure_collection()
        q_filter = _build_filter(kb_name)

        # Generate BM25 sparse query vector from query text
        sparse_indices, sparse_values = self._encode_sparse([query_text])[0]
        if not sparse_indices:
            # Fallback to dense-only if BM25 fails to produce a sparse vector
            return await self.search(query_vector, top_k=top_k, kb_name=kb_name)

        results = self._client.query_points(
            collection_name=self.collection_name,
            prefetch=[
                qmodels.Prefetch(
                    query=query_vector,
                    using=DENSE_VECTOR_NAME,
                    limit=top_k * 4,
                    filter=q_filter,
                ),
                qmodels.Prefetch(
                    query=qmodels.SparseVector(
                        indices=sparse_indices, values=sparse_values
                    ),
                    using=SPARSE_VECTOR_NAME,
                    limit=top_k * 4,
                    filter=q_filter,
                ),
            ],
            query=qmodels.FusionQuery(fusion=qmodels.Fusion.RRF),
            limit=top_k,
        )
        return self._hits_from_results(results)

    # ── Upsert / Delete / Count ──

    async def upsert(self, vectors: list[list[float]], chunks: list[ChunkRecord]) -> None:
        self.ensure_collection()
        # Generate BM25 sparse vectors
        texts = [c.text for c in chunks]
        sparse_vectors = self._encode_sparse(texts)

        points = []
        for vec, (sparse_idx, sparse_val), chunk in zip(vectors, sparse_vectors, chunks):
            # Content-based point ID = duplicate chunks within the same KB are
            # overwritten (upsert) instead of duplicated
            content_hash = hashlib.md5(
                (chunk.kb_name + "\x00" + chunk.text).encode()
            ).hexdigest()
            vectors_dict: dict = {DENSE_VECTOR_NAME: vec}
            if sparse_idx:
                vectors_dict[SPARSE_VECTOR_NAME] = qmodels.SparseVector(
                    indices=sparse_idx,
                    values=sparse_val,
                )
            points.append(
                qmodels.PointStruct(
                    id=content_hash,
                    vector=vectors_dict,
                    payload={
                        "doc_id": chunk.doc_id,
                        "filename": chunk.filename,
                        "kb_name": chunk.kb_name,
                        "chunk_index": chunk.chunk_index,
                        "text": chunk.text,
                        "chapter_title": chunk.chapter_title,
                        "chapter_index": chunk.chapter_index,
                        "prev_chunk_text": chunk.prev_chunk_text,
                        "next_chunk_text": chunk.next_chunk_text,
                        "metadata": chunk.metadata,
                    },
                )
            )
        self._client.upsert(collection_name=self.collection_name, points=points)

    async def delete_by_doc(self, doc_id: str) -> None:
        if not self._client.collection_exists(self.collection_name):
            return  # nothing to delete
        self._client.delete(
            collection_name=self.collection_name,
            points_selector=qmodels.FilterSelector(
                filter=qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(
                            key="doc_id", match=qmodels.MatchValue(value=doc_id)
                        )
                    ]
                )
            ),
        )

    def count(self, kb_name: str | None = None) -> int:
        if not self._client.collection_exists(self.collection_name):
            return 0
        if kb_name:
            result = self._client.count(
                collection_name=self.collection_name,
                count_filter=qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(
                            key="kb_name", match=qmodels.MatchValue(value=kb_name)
                        )
                    ]
                ),
            )
        else:
            result = self._client.count(collection_name=self.collection_name)
        return result.count

    @staticmethod
    def _hits_from_results(results) -> list[SearchHit]:
        hits: list[SearchHit] = []
        for r in results.points:
            p = r.payload or {}
            hits.append(
                SearchHit(
                    chunk_id=r.id,
                    doc_id=p.get("doc_id", ""),
                    filename=p.get("filename", ""),
                    text=p.get("text", ""),
                    score=r.score,
                    prev_text=p.get("prev_chunk_text", ""),
                    next_text=p.get("next_chunk_text", ""),
                    chapter_title=p.get("chapter_title", ""),
                    metadata=p.get("metadata", {}),
                )
            )
        return hits
