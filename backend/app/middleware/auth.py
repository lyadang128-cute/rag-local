"""Optional API Key authentication middleware.

When settings.api_key is non-empty, all /api/* requests require
an `X-API-Key` header matching that key.  /health is always public.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import settings


PUBLIC_PATHS = {"/health", "/"}


class APIKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Only enforce if api_key is configured
        if not settings.api_key or request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        key = request.headers.get("X-API-Key") or request.headers.get("x-api-key")
        if key != settings.api_key:
            return JSONResponse(
                status_code=401,
                content={"code": 401, "message": "Invalid or missing API key"},
            )

        return await call_next(request)
