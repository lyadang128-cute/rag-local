
# RAG Knowledge Base — AI Rules

## Project Overview

RAG知识库系统：Vue 3 前端 + FastAPI 后端 + Qdrant 向量库，支持文档检索、混合搜索、流式对话。

## Commands

```bash
# Dev
cd backend && python -m uvicorn app.main:app --host 127.0.0.1 --port 9090
cd frontend && npm run dev

# One-click (Windows)
start.bat

# Docker
docker compose up -d

# Eval
cd backend && python -m eval.evaluate --kb-name default
```

## Architecture

```
Vue 3 (:5173) → FastAPI (:9090) → DeepSeek API
                       ↓
              Qdrant (embedded or Docker :6333)
                       ↑
         Document → Parser → Chunker → Embedder
```

## Key Rules

- **QdrantClient 是模块级单例** (retriever.py) — 嵌入式模式不能创建多个实例，会文件锁冲突
- **QDRANT_URL 和 QDRANT_LOCAL_PATH 互斥** — 远程模式填 URL，嵌入式模式填 LOCAL_PATH，不能同时有值
- **文档入库是异步的** — upload/import 立即返回 202，后台线程处理 Parse→Chunk→Embed→Upsert
- **Embedding 维度是动态的** — local bge-small=512D, bge-large=1024D, api=4096D；切换 embed_mode 时 Qdrant collection 会自动重建
- **Python 版本** — 3.11/3.12，禁止 3.13（numpy DLL 崩溃）
- **数据库只有 SQLite** — app/utils/db.py，每线程一个连接，存放文档元数据和 QA Memory
- **HF_ENDPOINT 默认 hf-mirror.com** — 国内镜像，海外部署改为 huggingface.co

## API Routes

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/documents/upload` | 上传文件 (multipart, 202 async) |
| POST | `/api/v1/documents/import` | URL 导入 (202 async) |
| GET | `/api/v1/documents` | 文档列表 |
| GET | `/api/v1/documents/{id}` | 文档详情 |
| DELETE | `/api/v1/documents/{id}` | 删除文档+chunks |
| POST | `/api/v1/search` | 混合搜索 |
| POST | `/api/v1/chat` | RAG 对话 (SSE 流式) |
| GET | `/api/v1/kb/list` | 知识库列表 |
| GET | `/api/v1/kb/{name}` | 知识库统计 |
| DELETE | `/api/v1/kb/{name}` | 删除知识库 |
| GET | `/api/v1/config` | 当前配置（脱敏） |

## Retrieval Pipeline

```
Query → Embedding ─┬→ Dense (bge/DeepSeek) ─┐
                   └→ BM25 Sparse            ─┴→ RRF Fusion → Reranker → LLM
```

BM25 失败 → 纯稠密 fallback；Reranker 失败 → 原始结果 fallback。

## Pitfalls

- 本地模型 `bge-small-zh-v1.5` 的 MIN_SCORE 建议 0.15-0.35，设太高（>0.5）会导致零召回
- Qdrant embedded 模式不支持并发写入 — 后台 ingestion 是单线程串行的
- fastembed 缓存放 `./data/fastembed_cache`，不要放系统 TEMP（会被清理导致重新下载）

## Deep Docs

| Document | Content |
|----------|---------|
| `ARCHITECTURE.md` | 完整架构、API 协议、数据流、配置参考 |
| `CHANGELOG.md` | v0.1.0→v0.2.1 重构对照（检索/分块/异步/安全） |
| `README.md` | 快速开始、功能概览、配置速查 |
