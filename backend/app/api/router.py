from fastapi import APIRouter

from app.api import auth, chat, config, documents, kb, search

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(config.router)
api_router.include_router(documents.router)
api_router.include_router(search.router)
api_router.include_router(chat.router)
api_router.include_router(kb.router)
