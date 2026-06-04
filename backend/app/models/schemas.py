from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ── Generic response envelope ────────────────────────────────────────

class APIResponse(BaseModel):
    code: int = 0
    message: str = "ok"
    data: Any | None = None


# ── Document ─────────────────────────────────────────────────────────

class DocumentOut(BaseModel):
    id: str
    filename: str
    size: int
    status: str  # processing | indexed | failed
    chunk_count: int
    kb_name: str
    created_at: datetime


class DocumentListOut(BaseModel):
    items: list[DocumentOut]
    total: int
    page: int
    page_size: int


class ImportRequest(BaseModel):
    url: str
    kb_name: str = "default"


# ── Search ───────────────────────────────────────────────────────────

class SearchRequest(BaseModel):
    query: str
    kb_name: str = "default"
    top_k: int = 5


class SearchHit(BaseModel):
    chunk_id: str
    doc_id: str
    filename: str
    text: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    results: list[SearchHit]


# ── Chat ─────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str  # user | assistant
    content: str


class ChatRequest(BaseModel):
    question: str
    kb_name: str = "default"
    top_k: int = 5
    history: list[ChatMessage] = Field(default_factory=list)
    fast_mode: bool = False  # skip query rewriting, search directly


class CorrectionRequest(BaseModel):
    question: str
    answer: str
    kb_name: str = "default"


# ── KB Management ────────────────────────────────────────────────────

class KBStats(BaseModel):
    kb_name: str
    document_count: int
    chunk_count: int
    total_size_bytes: int


class KBListOut(BaseModel):
    kb_names: list[str]
