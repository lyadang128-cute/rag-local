# RAG 知识库系统 — 优化重构对照文档

> 重构日期：2026-05-31 | 版本：v0.1.0 → v0.2.1

---

## 一、总览

| 维度 | 重构前 (v0.1.0) | 重构后 (v0.2.1) |
|------|:-----------:|:-----------:|
| 检索方式 | 纯稠密向量（Cosine） | **混合检索**（稠密 + BM25 稀疏，RRF 融合） |
| 结果重排 | 无 | **Cross-Encoder Reranker** |
| 文档入库 | 同步（请求内完成，大文件易超时） | **异步**（BackgroundTasks，立即返回） |
| 文本分块 | 固定字符数，无重叠 | **Token 级递归切分**，带语义边界感知 |
| API 容错 | 无重试 | **指数退避重试**（最多 3 次） |
| 安全认证 | 无 | **可选 API Key 中间件** |
| 文件校验 | 仅扩展名 | **魔数字节验证** |
| 质量评估 | 无 | **RAGAS 评估框架** |
| 配置管理 | 多处硬编码 | **统一 .env 配置** |
| 启动脚本 | 硬编码 Python 路径，不装依赖 | **自动创建 venv、装依赖、打开浏览器** |

---

## 二、检索架构对比

### 重构前
```
Query → Embedding → Qdrant Dense Search → Top-K → LLM
```
- 仅依赖语义相似度，对关键词/专有名词召回弱
- 无重排序，低质量片段直接进入 LLM 上下文
- 向量维度硬编码 512，切换 embed_mode 会崩溃

### 重构后
```
Query → Embedding ─┬→ Dense (512D/4096D) ─┐
                   └→ BM25 Sparse         ─┴→ RRF Fusion → Reranker → LLM
```
- 稠密 + 稀疏双路召回，互补语义与关键词
- RRF (Reciprocal Rank Fusion) 融合排序
- Cross-Encoder 重排序，过滤低相关片段
- 各环节独立 fallback：BM25 失败 → 纯稠密；Reranker 失败 → 原始结果

---

## 三、分块策略对比

| | 重构前 | 重构后 |
|------|---------|---------|
| 计量单位 | 字符数 | **Token 数** (tiktoken) |
| 分割方式 | 固定位置截断 | **递归语义分隔符** |
| 分隔符优先级 | 无 | `\n\n` → `\n` → `。` → `.` → `；` → `,` → ` ` |
| 重叠 | 无 | 64 tokens (12.5%) |
| 中英文适应性 | 弱（中文标点未处理） | **强**（递归到字符级兜底） |

---

## 四、新增/修改文件清单

### Phase 1 — Bug 修复 + 配置化

| 文件 | 变更 |
|------|------|
| `backend/app/config.py` | 新增 `embed_dim`（自动推导）、`min_score`、`rerank_model`、`rerank_top_k`、`recall_top_k`、`api_retry_times/backoff`、`max_upload_size`、`api_key`、`allowed_origins` |
| `backend/app/core/retriever.py` | `VECTOR_DIM` 改为从 `settings.embed_dim` 读取；`ensure_collection` 增加维度变化检测与重建 |
| `backend/app/api/chat.py` | `MIN_SCORE` 从 `settings.min_score` 读取 |

### Phase 2 — 混合检索 + Reranker

| 文件 | 变更 |
|------|------|
| `backend/app/core/retriever.py` | 新增 `hybrid_search()`：Qdrant named vectors (dense + bm25) + Prefetch + RRF Fusion |
| `backend/app/core/reranker.py` | **新建**：Cross-Encoder 封装，模型 `BAAI/bge-reranker-v2-m3` |
| `backend/app/api/chat.py` | 流水线改为 hybrid_search → min_score 过滤 → reranker 重排 → LLM |
| `backend/app/api/search.py` | 同步改为混合检索 + Reranker |

### Phase 3 — 异步任务 + 工程健壮性

| 文件 | 变更 |
|------|------|
| `backend/app/tasks/ingestion.py` | **新建**：后台文档处理（Parse→Chunk→Embed→Upsert→更新DB状态） |
| `backend/app/api/documents.py` | upload/import 改为 BackgroundTasks 异步模式 |
| `backend/app/core/embedder.py` | `_embed_api()` 加 tenacity 重试装饰器 |
| `backend/app/core/generator.py` | 流式请求加重试 + 连接中断异常捕获 |
| `backend/app/core/chunker.py` | **重写**：tiktoken 计数 + 递归分隔符切分 |
| `backend/requirements.txt` | 新增 `tenacity`、`tiktoken`、`fastembed` |

### Phase 4 — 安全加固 + 评估体系

| 文件 | 变更 |
|------|------|
| `backend/app/middleware/auth.py` | **新建**：API Key 中间件（`X-API-Key` header，可开关） |
| `backend/app/main.py` | CORS 从 settings 读取；注册 Auth 中间件 |
| `backend/app/utils/file.py` | 新增 `MAGIC_BYTES` 魔数校验 + `validate_file_magic()` |
| `backend/app/api/documents.py` | 上传加文件大小限制 + 魔数校验 |
| `backend/tests/eval/test_eval.py` | **新建**：RAGAS 评估脚本 |
| `backend/tests/eval/test_questions.json` | **新建**：测试问题集 |

### 启动与环境修复（上线调试）

| 问题 | 修复 |
|------|------|
| Python 3.13.0b1 numpy DLL 崩溃 | 创建 `backend/.venv`，使用 Python 3.12.10 |
| `qdrant_client` 1.18 `NamedVector` 不兼容 | 降级至 1.17.1 + 改用 `list[float]` + `using` 参数 |
| Qdrant 嵌入式模式文件锁冲突 | Retriever 改为模块级共享 `QdrantClient` 单例 |
| `MIN_SCORE=0.6` 对本地 512D 模型过高 | 降至 `0.35` |
| TXT 文件仅支持 UTF-8，GBK 中文报错 | `TextProcessor` 增加自动编码检测（UTF-8→GBK→GB18030→…） |
| `start.bat` 多次失败 | 完全重写：自动建 venv、装依赖、健康检查、自动开浏览器 |

---

## 五、配置项变化

```ini
# 新增配置项（backend/.env）
EMBED_MODE=local              # "local" / "api"
RERANK_MODEL=BAAI/bge-reranker-v2-m3
RERANK_TOP_K=5
RECALL_TOP_K=20
MIN_SCORE=0.35                # 本地模型建议 0.3~0.4，API 模型可设 0.5~0.7
API_RETRY_TIMES=3
API_RETRY_BACKOFF=1.0
MAX_UPLOAD_SIZE=52428800      # 50MB
API_KEY=                      # 留空则不启用认证
ALLOWED_ORIGINS=http://localhost:5173
```

---

## 六、API 变更

| 端点 | 变更 |
|------|------|
| `POST /api/v1/documents/upload` | **行为变更**：不再同步处理，立即返回 202 + `status="processing"` |
| `POST /api/v1/documents/import` | 同上，异步处理 URL 导入 |
| `POST /api/v1/search` | 内部改用 hybrid_search + reranker |
| `POST /api/v1/chat` | 内部改用 hybrid_search + reranker，SSE 流式不变 |
| `GET /api/v1/documents` | 无变化，通过 `status` 字段查看索引进度 |
| `GET /health` | 无变化 |

---

## 七、启动方式

```
重构前:  双击 start.bat → 可能因硬编码路径、缺失依赖、端口冲突而失败
重构后:  双击 start.bat → 自动建 venv → 装依赖 → 清端口 → 启动 → 开浏览器
```
