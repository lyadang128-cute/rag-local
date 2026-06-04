from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings

logger = logging.getLogger(__name__)


class Embedder:
    """Embedding via local model (lightweight) or API."""

    # bge-small-zh-v1.5: 512-dim, bge-m3: 1024-dim, api: 4096-dim
    DIM_MAP = {"api": 4096, "local": 512}
    DIM = settings.embed_dim  # read from config (derived from embed_mode)

    # BGE series instruction prefix — required by the model for correct retrieval
    # https://huggingface.co/BAAI/bge-large-zh-v1.5
    QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："

    _model: Any = None
    _model_lock = threading.Lock()
    _client: httpx.AsyncClient | None = None

    def __init__(self) -> None:
        self._api_key = settings.deepseek_api_key
        self._base_url = settings.deepseek_base_url.rstrip("/")

    # ── API mode ──────────────────────────────────────────────

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(60.0),
            )
        return self._client

    async def _embed_api(self, texts: list[str]) -> list[list[float]]:
        @retry(
            retry=retry_if_exception_type((httpx.NetworkError, httpx.TimeoutException, httpx.HTTPStatusError)),
            stop=stop_after_attempt(settings.api_retry_times),
            wait=wait_exponential(multiplier=settings.api_retry_backoff, min=1, max=10),
            reraise=True,
        )
        async def _call():
            client = await self._get_client()
            resp = await client.post(
                "/v1/embeddings",
                json={
                    "model": settings.embed_api_model,
                    "input": texts,
                },
            )
            resp.raise_for_status()
            return resp

        resp = await _call()
        data = resp.json()
        items = sorted(data["data"], key=lambda x: x["index"])
        return [item["embedding"] for item in items]

    # ── Local mode ────────────────────────────────────────────

    @classmethod
    def _get_local_model(cls):
        if cls._model is None:
            with cls._model_lock:
                if cls._model is None:
                    from sentence_transformers import SentenceTransformer

                    cls._model = SentenceTransformer(settings.embed_local_model)
        return cls._model

    async def _embed_local(self, texts: list[str]) -> list[list[float]]:
        loop = asyncio.get_running_loop()
        model = self._get_local_model()
        embeddings = await loop.run_in_executor(None, model.encode, texts)
        return [e.tolist() for e in embeddings]

    # ── Public API ────────────────────────────────────────────

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if settings.embed_mode == "api":
            return await self._embed_api(texts)
        return await self._embed_local(texts)

    async def embed_query(self, text: str) -> list[float]:
        # BGE models require instruction prefix for queries
        if settings.embed_mode == "local":
            text = self.QUERY_INSTRUCTION + text
        vectors = await self.embed([text])
        return vectors[0]

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None
