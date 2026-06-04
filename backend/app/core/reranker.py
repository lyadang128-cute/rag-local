from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


class Reranker:
    """Cross-Encoder re-ranker that scores query-chunk pairs for relevance.

    Uses sentence-transformers CrossEncoder under the hood.
    Default model: BAAI/bge-reranker-v2-m3 (multilingual, good for Chinese).
    """

    _model: Any = None
    _model_lock = threading.Lock()

    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or settings.rerank_model

    @classmethod
    def _get_model(cls, model_name: str):
        if cls._model is None:
            with cls._model_lock:
                if cls._model is None:
                    from sentence_transformers import CrossEncoder

                    logger.info(f"Loading reranker model: {model_name}")
                    cls._model = CrossEncoder(model_name)
        return cls._model

    async def rerank(
        self,
        query: str,
        documents: list[str],
        top_k: int | None = None,
    ) -> list[tuple[int, float]]:
        """Re-rank documents against query.

        Returns a list of (original_index, relevance_score), sorted by score descending.
        Scores above 0 indicate positive relevance; below 0 indicate likely irrelevant.
        """
        top_k = top_k or settings.rerank_top_k
        if not documents:
            return []

        loop = asyncio.get_running_loop()
        model = self._get_model(self.model_name)

        # Build query-doc pairs
        pairs = [(query, doc) for doc in documents]

        # CrossEncoder returns a list of scores (one per pair)
        scores: list[float] = await loop.run_in_executor(
            None, lambda: model.predict(pairs).tolist()  # type: ignore[union-attr]
        )

        # Pair with original indices, filter negatives, sort descending
        indexed = [(i, s) for i, s in enumerate(scores) if s >= 0]
        indexed.sort(key=lambda x: x[1], reverse=True)

        return indexed[:top_k]

    async def filter_and_sort(
        self,
        query: str,
        documents: list[str],
        doc_metas: list[dict] | None = None,
        top_k: int | None = None,
    ) -> tuple[list[str], list[dict], list[float]]:
        """Re-rank documents and return filtered + sorted documents with metadata.

        Returns (sorted_texts, sorted_metas, sorted_scores).
        Documents with negative relevance scores are dropped.
        """
        ranked = await self.rerank(query, documents, top_k)
        sorted_texts = [documents[i] for i, _ in ranked]
        sorted_scores = [s for _, s in ranked]
        sorted_metas = [doc_metas[i] for i, _ in ranked] if doc_metas else [{}] * len(sorted_texts)
        return sorted_texts, sorted_metas, sorted_scores
