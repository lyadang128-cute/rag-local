from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # DeepSeek
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_chat_model: str = "deepseek-v4-flash"

    # Embedding: "local" for lightweight local model, "api" for Embedding API
    embed_mode: str = "local"
    embed_local_model: str = "BAAI/bge-small-zh-v1.5"
    embed_api_model: str = "deepseek-embedding"

    # Derived from embed_mode and model choice
    @property
    def embed_dim(self) -> int:
        if self.embed_mode == "api":
            return 4096
        # local: bge-m3 or bge-large → 1024, bge-small → 512
        name = self.embed_local_model.lower()
        if "m3" in name or "large" in name:
            return 1024
        return 512

    # Qdrant — set qdrant_url for remote server, or qdrant_local_path for embedded mode
    qdrant_url: str = "http://localhost:6333"
    qdrant_local_path: str = "./data/qdrant"
    qdrant_collection: str = "rag_knowledge_base"

    # Chunking
    chunk_size: int = 512
    chunk_overlap: int = 64

    # Retrieval
    top_k: int = 5
    min_score: float = 0.35  # cosine similarity threshold (lower for small local models)

    # Reranker (Cross-Encoder)
    rerank_model: str = "BAAI/bge-reranker-v2-m3"
    rerank_top_k: int = 5    # final number of chunks after reranking
    recall_top_k: int = 20   # candidate chunks fetched before reranking

    # API resilience
    api_retry_times: int = 3
    api_retry_backoff: float = 1.0  # initial backoff seconds (exponential)

    # Storage
    upload_dir: str = "./data/uploads"
    max_upload_size: int = 50 * 1024 * 1024  # 50 MB

    # Security
    api_key: str = ""  # if set, all /api/* require X-API-Key header
    allowed_origins: str = "http://localhost:5173"  # comma-separated CORS origins

    # HuggingFace
    hf_endpoint: str = "https://hf-mirror.com"  # mirror for China users
    fastembed_cache_path: str = "./data/fastembed_cache"  # avoid system TEMP cleanup

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
