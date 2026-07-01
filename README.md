# RAG Knowledge Base

基于检索增强生成（RAG）的智能知识库系统，支持文档上传、混合检索、交叉精排和流式对话。

## 功能

- **文档管理** — 支持 PDF / Word / Excel / PPT / TXT / 网页，拖拽上传
- **混合检索** — Dense（bge-small-zh-v1.5 512D）+ Sparse（BM25），RRF 融合
- **交叉精排** — bge-reranker-v2-m3 对候选 chunk 二次排序
- **流式对话** — SSE 流式输出，支持多知识库切换
- **记忆系统** — 手动保存优质回答到 QA Memory，后续相似问题直接命中
- **快速模式** — 跳过查询改写，直搜出结果
- **评测工具** — 内置检索评测脚本，调参有数据可依

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 18+
- [可选] Docker（用于 Qdrant 服务端模式）

### 1. 克隆项目

```bash
git clone https://github.com/lyadang128-cute/rag-local.git
cd rag-local
```

### 2. 配置环境

```bash
cd backend
cp .env.example .env
# 编辑 .env，填入你的 DEEPSEEK_API_KEY
```

### 3. 安装依赖

```bash
# 后端
cd backend
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt

# 前端
cd ../frontend
npm install
```

### 4. 启动服务

**方式一：一键启动（Windows）**

双击项目根目录的 `start.bat`，自动启动前后端。

**方式二：手动启动**

```bash
# 后端 (http://localhost:9090)
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 9090

# 前端 (http://localhost:5173)
cd frontend
npm run dev
```

**方式三：Docker Compose**

```bash
# 首次使用需先创建 .env 文件
cp backend/.env.example backend/.env
# 编辑 .env 填入你的 DEEPSEEK_API_KEY，然后启动
docker compose up -d
```

> Docker 模式使用 Qdrant 服务端，启动更快但需额外资源。**海外用户注意：** 默认配置了 HuggingFace 国内镜像 `hf-mirror.com`，海外部署请在 `.env` 中将 `HF_ENDPOINT` 改为 `https://huggingface.co`，否则模型下载会失败。

### 5. 使用

1. 打开 `http://localhost:5173`
2. 在「文档管理」页面上传文档
3. 切换到「AI 对话」页面开始提问

## 配置说明

| 参数 | 说明 | 默认值 |
|---|---|---|
| `EMBED_MODE` | 嵌入模式：`local`（免费离线）或 `api`（DeepSeek） | `local` |
| `CHUNK_SIZE` | 分块大小（tokens） | `1024` |
| `MIN_SCORE` | 最小相关度阈值（越低召回越全） | `0.15` |
| `RECALL_TOP_K` | 初检候选数 | `100` |
| `RERANK_TOP_K` | 精排后保留数 | `5` |
| `HF_ENDPOINT` | HuggingFace 镜像（国内用 `hf-mirror.com`，海外用 `huggingface.co`） | `https://hf-mirror.com` |

## 项目结构

```
├── backend/
│   ├── app/
│   │   ├── api/          # FastAPI 路由
│   │   ├── core/         # 检索/嵌入/生成/精排/分块
│   │   ├── models/       # Pydantic schemas
│   │   └── tasks/        # 文档解析与入库
│   ├── eval/             # 评测脚本与测试集
│   └── requirements.txt
├── frontend/
│   └── src/views/        # Vue 3 页面
├── docker-compose.yml
├── start.bat             # 一键启动
└── test.bat              # 一键评测
```

## 评测

```bash
# 双击 test.bat 或
cd backend
python -m eval.evaluate --kb-name default
```

结果输出到 `backend/eval/results.json`。

## License

MIT
