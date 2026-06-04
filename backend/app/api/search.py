import logging

from fastapi import APIRouter, Depends

from app.config import settings
from app.core.embedder import Embedder
from app.core.retriever import Retriever
from app.core.reranker import Reranker
from app.models.schemas import APIResponse, SearchRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/search", tags=["search"])


def _get_embedder() -> Embedder:
    return Embedder()


def _get_retriever() -> Retriever:
    return Retriever()


def _get_reranker() -> Reranker:
    return Reranker()


@router.post("", response_model=APIResponse)
async def search(
    req: SearchRequest,
    embedder: Embedder = Depends(_get_embedder),
    retriever: Retriever = Depends(_get_retriever),
    reranker: Reranker = Depends(_get_reranker),
):
    query_vec = await embedder.embed_query(req.query)

    # Hybrid search (dense + BM25)
    try:
        hits = await retriever.hybrid_search(
            query_vector=query_vec,
            query_text=req.query,
            top_k=settings.recall_top_k,
            kb_name=req.kb_name,
        )
    except Exception:
        logger.warning("Hybrid search failed, falling back to dense-only", exc_info=True)
        hits = await retriever.search(query_vec, top_k=settings.recall_top_k, kb_name=req.kb_name)

    # Filter + rerank
    candidates = [h for h in hits if h.score >= settings.min_score]
    if candidates and len(candidates) > req.top_k:
        try:
            texts = [h.text for h in candidates]
            metas = [
                {
                    "chunk_id": h.chunk_id,
                    "doc_id": h.doc_id,
                    "filename": h.filename,
                    "text": h.text,
                    "score": h.score,
                    "prev_text": h.prev_text,
                    "next_text": h.next_text,
                    "chapter_title": h.chapter_title,
                    "metadata": h.metadata,
                }
                for h in candidates
            ]
            sorted_texts, sorted_metas, sorted_scores = await reranker.filter_and_sort(
                req.query, texts, metas, top_k=req.top_k,
            )
            results = []
            for _, meta, score in zip(sorted_texts, sorted_metas, sorted_scores):
                results.append({
                    "chunk_id": meta.get("chunk_id", ""),
                    "doc_id": meta.get("doc_id", ""),
                    "filename": meta.get("filename", ""),
                    "text": meta.get("text", ""),
                    "prev_text": meta.get("prev_text", ""),
                    "next_text": meta.get("next_text", ""),
                    "chapter_title": meta.get("chapter_title", ""),
                    "score": score,
                    "metadata": meta.get("metadata", {}),
                })
            return APIResponse(data={"results": results})
        except Exception:
            logger.warning("Reranking failed, using raw search results", exc_info=True)

    # Fallback: return filtered hits without reranking
    results = [
        {
            "chunk_id": h.chunk_id,
            "doc_id": h.doc_id,
            "filename": h.filename,
            "text": h.text,
            "prev_text": h.prev_text,
            "next_text": h.next_text,
            "chapter_title": h.chapter_title,
            "score": h.score,
            "metadata": h.metadata,
        }
        for h in candidates[: req.top_k]
    ]
    return APIResponse(data={"results": results})
