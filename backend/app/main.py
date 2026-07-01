import logging
import os
from contextlib import asynccontextmanager

# MUST be set before any import that pulls in huggingface_hub (sentence-transformers,
# fastembed, etc.) — otherwise the ENDPOINT constant is frozen to huggingface.co.
from app.config import settings
if settings.hf_endpoint:
    os.environ["HF_ENDPOINT"] = settings.hf_endpoint
if settings.fastembed_cache_path:
    os.environ["FASTEMBED_CACHE_PATH"] = settings.fastembed_cache_path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.middleware.auth import JWTAuthMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Qdrant mode: local path={settings.qdrant_local_path}")
    logger.info(f"Embed mode: {settings.embed_mode} (dim={settings.embed_dim})")
    logger.info(
        f"Auth: {'enabled' if settings.api_key else 'disabled'}, "
        f"CORS: {settings.allowed_origins}"
    )
    if not settings.deepseek_api_key:
        logger.warning("DEEPSEEK_API_KEY not set — embedding/chat endpoints will fail")
    yield


app = FastAPI(
    title="RAG Knowledge Base",
    description="Retrieval-Augmented Generation knowledge base system",
    version="0.2.0",
    lifespan=lifespan,
)

# CORS — configurable
origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth middleware — JWT + API Key
app.add_middleware(JWTAuthMiddleware)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled error on {request.method} {request.url.path}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"code": 500, "message": "Internal server error"},
    )


app.include_router(api_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
