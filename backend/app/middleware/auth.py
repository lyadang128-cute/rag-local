"""Auth middleware — supports JWT (Bearer token) and API Key.

- JWT: validates Authorization header, injects request.state.user
- API Key (legacy): when settings.api_key is set, requires X-API-Key header
- PUBLIC_PATHS: always allowed without auth
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from jose import JWTError, jwt

from app.config import settings

PUBLIC_PATHS = {
    "/health", "/",
    "/api/v1/auth/login",
    "/api/v1/auth/register",
}


class JWTAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Public paths — no auth required
        if request.url.path in PUBLIC_PATHS or request.url.path.startswith("/docs") or request.url.path.startswith("/openapi"):
            return await call_next(request)

        # API Key check (if configured)
        if settings.api_key:
            key = request.headers.get("X-API-Key") or request.headers.get("x-api-key")
            if key != settings.api_key:
                return JSONResponse(
                    status_code=401,
                    content={"code": 401, "message": "Invalid or missing API key"},
                )

        # JWT check — try to extract user, but don't fail if not present
        # (some endpoints may work without auth)
        request.state.user = None
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
                request.state.user = {
                    "username": payload["sub"],
                    "role": payload["role"],
                    "department": payload.get("department", ""),
                }
            except JWTError:
                pass  # invalid token → user remains None

        return await call_next(request)
