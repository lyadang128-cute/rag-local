# RAG Knowledge Base System — Architecture Document

## 1. System Overview

A Retrieval-Augmented Generation (RAG) knowledge base system that ingests documents, indexes them into a vector database, and answers user questions grounded in the retrieved context.

```
User (Browser)  ──►  Vue 3 SPA  ──►  FastAPI  ──►  DeepSeek API
                                                    │
                              ┌─────────────────────┘
                              ▼
                         Qdrant (Vector DB)
                              ▲
                              │
              Document  ──►  Parser  ──►  Chunker  ──►  Embedder
```

## 2. Directory Structure

```
RAG-demo/
├── ARCHITECTURE.md                 # This file
├── docker-compose.yml              # Qdrant + backend services
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── .env.example
│   ├── .env                        # Actual config (gitignored)
│   ├── app/
│   │   ├── main.py                 # FastAPI application entry
│   │   ├── config.py               # Settings via pydantic-settings
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── router.py           # Aggregate router
│   │   │   ├── documents.py        # Document upload / CRUD
│   │   │   ├── search.py           # Semantic search
│   │   │   ├── chat.py             # RAG chat (SSE streaming)
│   │   │   └── kb.py               # Knowledge-base management
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── chunker.py          # Text splitting strategies
│   │   │   ├── embedder.py         # DeepSeek embedding client
│   │   │   ├── retriever.py        # Qdrant search wrapper
│   │   │   └── generator.py        # DeepSeek LLM chat (streaming)
│   │   ├── processors/
│   │   │   ├── __init__.py
│   │   │   ├── base.py             # Abstract processor
│   │   │   ├── text.py             # .txt / .md
│   │   │   ├── pdf.py              # .pdf (PyMuPDF)
│   │   │   ├── docx.py             # .docx (python-docx)
│   │   │   ├── excel.py            # .xlsx (openpyxl)
│   │   │   ├── ppt.py              # .pptx (python-pptx)
│   │   │   ├── ocr.py              # Image OCR (paddleocr/easyocr)
│   │   │   └── web.py              # URL scraping (trafilatura)
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   └── schemas.py          # Pydantic request/response models
│   │   └── utils/
│   │       ├── __init__.py
│   │       └── file.py             # File type detection, hash, etc.
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py
│       ├── test_documents.py
│       ├── test_search.py
│       └── test_chat.py
├── frontend/                       # Vue 3 (added in phase 2)
├── data/
│   └── uploads/                    # Persisted uploaded files
└── docs/
    └── superpowers/
        └── specs/                  # Design specs
```

## 3. Technology Stack

| Layer          | Choice                | Version      |
| -------------- | --------------------- | ------------ |
| Backend        | FastAPI               | ≥ 0.111      |
| Async Server   | Uvicorn               | ≥ 0.30       |
| Vector DB      | Qdrant                | ≥ 1.9 (Docker) |
| LLM            | DeepSeek Chat         | API          |
| Embedding      | DeepSeek Embedding    | API          |
| Frontend       | Vue 3 + Vite          | ≥ 3.4        |
| HTTP Client    | httpx                 | ≥ 0.27       |
| Qdrant Client  | qdrant-client         | ≥ 1.9        |
| Doc Parsing    | PyMuPDF, python-docx, openpyxl, python-pptx |
| OCR            | PaddleOCR             |              |

## 4. REST API Protocol

### 4.1 General Conventions

- Base URL: `http://<host>:8000/api/v1`
- Content-Type: `application/json` (except upload: `multipart/form-data`)
- Response envelope:

```json
{
  "code": 0,
  "message": "ok",
  "data": { ... }
}
```

| code | meaning          |
| ---- | ---------------- |
| 0    | Success          |
| 400  | Bad request      |
| 404  | Not found        |
| 500  | Internal error   |

### 4.2 Document Management

| Method | Path                        | Description              |
| ------ | --------------------------- | ------------------------ |
| POST   | `/documents/upload`         | Upload files (multipart) |
| POST   | `/documents/import`         | Import from URL          |
| GET    | `/documents`                | List uploaded documents  |
| GET    | `/documents/{doc_id}`       | Get document detail      |
| DELETE | `/documents/{doc_id}`       | Remove document + chunks |

**POST `/documents/upload`**

- Content-Type: `multipart/form-data`
- Body: `files: List[UploadFile]`, `kb_name: str` (optional)
- Response:

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "documents": [
      {
        "id": "uuid",
        "filename": "report.pdf",
        "size": 123456,
        "status": "processing",
        "chunk_count": 0,
        "created_at": "2026-05-11T10:00:00Z"
      }
    ]
  }
}
```

**POST `/documents/import`**

```json
// Request
{
  "url": "https://example.com/article",
  "kb_name": "default"
}
// Response: same as upload
```

**GET `/documents`**

- Query: `?kb_name=default&page=1&page_size=20`
- Response: paginated document list

**DELETE `/documents/{doc_id}`**

- Cascades: removes all chunks from Qdrant + file from disk

### 4.3 Semantic Search

| Method | Path       | Description           |
| ------ | ---------- | --------------------- |
| POST   | `/search`  | Search by query text  |

```json
// Request
{
  "query": "什么是向量数据库",
  "kb_name": "default",
  "top_k": 5
}
// Response
{
  "code": 0,
  "data": {
    "results": [
      {
        "chunk_id": "uuid",
        "doc_id": "uuid",
        "filename": "vector-db.md",
        "text": "...matched snippet...",
        "score": 0.92,
        "metadata": { "page": 3 }
      }
    ]
  }
}
```

### 4.4 RAG Chat

| Method | Path     | Description                       |
| ------ | -------- | --------------------------------- |
| POST   | `/chat`  | Ask question, get RAG answer      |

```json
// Request
{
  "question": "Qdrant 有哪些优势？",
  "kb_name": "default",
  "top_k": 5,
  "history": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}
```

Response: **Server-Sent Events (SSE)** with `text/event-stream`.

```
event: chunk
data: {"content": "Qdrant 的优势包括"}

event: chunk
data: {"content": "：高性能 Rust 实现..."}

event: sources
data: {"items": [{"filename": "qdrant.md", "text": "...", "score": 0.92}]}

event: done
data: {}
```

### 4.5 Knowledge Base Management

| Method | Path               | Description          |
| ------ | ------------------ | -------------------- |
| GET    | `/kb/list`         | List all KB names    |
| GET    | `/kb/{kb_name}`    | KB statistics        |
| DELETE | `/kb/{kb_name}`    | Delete entire KB     |

## 5. Core Module Interfaces (Python)

### 5.1 BaseProcessor (`processors/base.py`)

```python
from abc import ABC, abstractmethod

class BaseProcessor(ABC):
    """Return a list of text chunks extracted from the file."""
    @abstractmethod
    async def extract(self, file_path: str) -> list[str]:
        ...
```

### 5.2 Embedder (`core/embedder.py`)

```python
class Embedder:
    def __init__(self, api_key: str, model: str, base_url: str): ...

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Batch embed texts, returns vectors (dim=1024)."""

    async def embed_query(self, text: str) -> list[float]:
        """Single query embedding."""
```

### 5.3 Retriever (`core/retriever.py`)

```python
class Retriever:
    def __init__(self, client: QdrantClient, collection: str): ...

    async def search(self, query_vector: list[float], top_k: int = 5,
                     filters: dict | None = None) -> list[SearchHit]:
        """Semantic search, returns hits with payload + score."""

    async def upsert(self, chunks: list[ChunkRecord]) -> None:
        """Batch insert chunk vectors + payload."""

    async def delete_by_doc(self, doc_id: str) -> None:
        """Remove all chunks belonging to a document."""
```

### 5.4 Generator (`core/generator.py`)

```python
class Generator:
    def __init__(self, api_key: str, model: str, base_url: str): ...

    async def generate(self, prompt: str,
                       history: list[dict] | None = None) -> AsyncIterator[str]:
        """Stream-generate answer tokens."""

    def build_rag_prompt(self, question: str,
                         contexts: list[str]) -> str:
        """Build system + user prompt from retrieved contexts."""
```

### 5.5 Chunker (`core/chunker.py`)

```python
class Chunker:
    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 64): ...

    def split(self, text: str) -> list[str]:
        """Split text into overlapping chunks, respecting sentence boundaries."""
```

## 6. Data Flow

### 6.1 Document Ingestion

```
Upload ──► Save to disk ──► Detect file type
                                │
            ┌───────────────────┘
            ▼
    ┌──────────────┐
    │   Processor   │  (text/pdf/docx/excel/ppt/ocr/web)
    └──────┬───────┘
           ▼       raw text string
    ┌──────────────┐
    │   Chunker    │
    └──────┬───────┘
           ▼       list[str] chunks
    ┌──────────────┐
    │   Embedder   │  (DeepSeek Embedding API)
    └──────┬───────┘
           ▼       list[list[float]]
    ┌──────────────┐
    │  Retriever   │  (Qdrant upsert)
    └──────────────┘
           ▼
      Indexed ✓
```

### 6.2 RAG Query

```
User Question
      │
      ▼
┌──────────────┐
│   Embedder   │  query vector
└──────┬───────┘
       ▼
┌──────────────┐
│  Retriever   │  top_k chunks from Qdrant
└──────┬───────┘
       ▼
┌──────────────┐
│  Generator   │  build_rag_prompt(question, contexts)
└──────┬───────┘
       ▼
   SSE Stream  ──► User
```

## 7. Configuration

All settings via environment variables / `.env`:

| Variable               | Description                 | Default                          |
| ---------------------- | --------------------------- | -------------------------------- |
| `DEEPSEEK_API_KEY`     | DeepSeek API key            | (required)                       |
| `DEEPSEEK_BASE_URL`    | DeepSeek API base URL       | `https://api.deepseek.com`       |
| `DEEPSEEK_CHAT_MODEL`  | Chat model name             | `deepseek-chat`                  |
| `DEEPSEEK_EMBED_MODEL` | Embedding model name        | `deepseek-embedding-v1`          |
| `QDRANT_URL`           | Qdrant server URL           | `http://localhost:6333`          |
| `QDRANT_COLLECTION`    | Default collection name     | `rag_knowledge_base`             |
| `CHUNK_SIZE`           | Max tokens per chunk        | `512`                            |
| `CHUNK_OVERLAP`        | Overlap between chunks      | `64`                             |
| `TOP_K`                | Default retrieval count     | `5`                              |
| `UPLOAD_DIR`           | Uploaded files directory    | `./data/uploads`                 |

## 8. Qdrant Schema

Collection name: `rag_knowledge_base`

Vector: 1024 dimensions, Cosine distance

Point payload:

```json
{
  "doc_id": "uuid",
  "filename": "report.pdf",
  "kb_name": "default",
  "chunk_index": 0,
  "text": "raw chunk text...",
  "metadata": {
    "page": 1,
    "source_type": "pdf"
  }
}
```
