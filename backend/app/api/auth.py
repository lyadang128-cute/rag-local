"""Auth endpoints — register, login, user info."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field

from app.config import settings
from app.models.schemas import APIResponse
from app.utils.db import db

router = APIRouter(prefix="/auth", tags=["auth"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ── Request / response models ────────────────────────────────────

class RegisterRequest(BaseModel):
    username: str = Field(min_length=2, max_length=30)
    password: str = Field(min_length=4, max_length=100)
    role: str = Field(default="employee")
    department: str = Field(default="")


class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    username: str
    role: str
    department: str


class LoginResponse(BaseModel):
    token: str
    user: UserOut


# ── Helpers ──────────────────────────────────────────────────────

def create_token(username: str, role: str, department: str) -> str:
    payload = {
        "sub": username,
        "role": role,
        "department": department,
        "exp": datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expire_hours),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def get_user_from_request(request: Request) -> dict | None:
    """Extract user dict from request state (set by JWTAuthMiddleware)."""
    return getattr(request.state, "user", None)


# ── Endpoints ────────────────────────────────────────────────────

@router.post("/register", response_model=APIResponse)
async def register(req: RegisterRequest):
    if db.get_user_by_username(req.username):
        raise HTTPException(status_code=400, detail="用户名已存在")
    if req.role not in ("admin", "manager", "employee"):
        raise HTTPException(status_code=400, detail="无效的角色")

    password_hash = pwd_context.hash(req.password)
    ok = db.create_user(req.username, password_hash, req.role, req.department)
    if not ok:
        raise HTTPException(status_code=500, detail="创建用户失败")

    return APIResponse(message=f"用户 '{req.username}' 注册成功")


@router.post("/login", response_model=APIResponse)
async def login(req: LoginRequest):
    user = db.get_user_by_username(req.username)
    if not user or not pwd_context.verify(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token = create_token(user["username"], user["role"], user["department"])
    return APIResponse(data={
        "token": token,
        "user": {
            "username": user["username"],
            "role": user["role"],
            "department": user["department"],
        },
    })


@router.get("/me", response_model=APIResponse)
async def me(request: Request):
    user = get_user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    return APIResponse(data={
        "username": user["username"],
        "role": user["role"],
        "department": user["department"],
    })
