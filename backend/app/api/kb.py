import glob
import os

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.retriever import Retriever
from app.models.schemas import APIResponse, KBCreateRequest, KBOut
from app.utils.db import db
from app.utils.file import remove_file
from qdrant_client.http import models as qmodels

router = APIRouter(prefix="/kb", tags=["kb"])

ROLE_LEVEL = {"employee": 1, "manager": 2, "admin": 3}


def _get_retriever() -> Retriever:
    return Retriever()


def _user_can_access(kb: dict, user: dict | None) -> bool:
    """Check if user can access a KB based on access_level and department.

    Level 1 = public (everyone, including anonymous)
    Level 2 = department (same department members)
    Level 3 = admin only
    Admin sees everything.
    """
    kb_level = kb.get("access_level", 1)

    if kb_level == 1:
        return True

    if user is None:
        return False

    # Admin sees all
    if user["role"] == "admin":
        return True

    # Level 3: admin only (handled above)
    if kb_level == 3:
        return False

    # Level 2: same department
    if kb_level == 2:
        return user["department"] == kb.get("department", "")

    return False


@router.get("/list", response_model=APIResponse)
async def list_kb(request: Request):
    user = getattr(request.state, "user", None)
    meta_kbs = {k["name"]: k for k in db.list_kbs()}
    doc_kb_names = db.list_kb_names()

    all_kbs = []
    seen = set()
    for name, meta in meta_kbs.items():
        all_kbs.append(meta)
        seen.add(name)
    for name in doc_kb_names:
        if name not in seen:
            all_kbs.append({"name": name, "department": "", "access_level": 1, "description": "", "created_at": ""})
            seen.add(name)

    # Filter by user permissions
    visible = [KBOut(**kb) for kb in all_kbs if _user_can_access(kb, user)]
    return APIResponse(data={"kbs": visible})


@router.post("/create", response_model=APIResponse)
async def create_kb(req: KBCreateRequest, request: Request):
    user = getattr(request.state, "user", None)
    if not user or ROLE_LEVEL.get(user["role"], 0) < 2:
        raise HTTPException(status_code=403, detail="仅管理员和部门主管可创建知识库")
    existing = db.get_kb(req.name)
    if existing:
        raise HTTPException(status_code=400, detail=f"知识库 '{req.name}' 已存在")
    ok = db.create_kb(
        name=req.name,
        department=req.department,
        access_level=req.access_level,
        description=req.description,
    )
    if not ok:
        raise HTTPException(status_code=500, detail="创建知识库失败")
    return APIResponse(message=f"知识库 '{req.name}' 创建成功", data={"name": req.name})


@router.get("/{kb_name}", response_model=APIResponse)
async def kb_stats(kb_name: str, retriever: Retriever = Depends(_get_retriever)):
    try:
        count = retriever.count(kb_name=kb_name)
    except Exception:
        count = 0
    docs, total = db.list_documents(kb_name=kb_name, page=1, page_size=1)
    meta = db.get_kb(kb_name)
    return APIResponse(
        data={
            "kb_name": kb_name,
            "document_count": total,
            "chunk_count": count,
            "total_size_bytes": 0,
            "department": meta.get("department", "") if meta else "",
            "access_level": meta.get("access_level", 1) if meta else 1,
            "description": meta.get("description", "") if meta else "",
        }
    )


@router.delete("/{kb_name}", response_model=APIResponse)
async def delete_kb(kb_name: str, request: Request, retriever: Retriever = Depends(_get_retriever)):
    user = getattr(request.state, "user", None)
    if not user or ROLE_LEVEL.get(user["role"], 0) < 2:
        raise HTTPException(status_code=403, detail="仅管理员和部门主管可删除知识库")
    # collect file IDs before deleting from DB
    docs, _ = db.list_documents(kb_name=kb_name, page=1, page_size=9999)

    # delete vectors from Qdrant
    retriever.client.delete(
        collection_name=retriever.collection_name,
        points_selector=qmodels.FilterSelector(
            filter=qmodels.Filter(
                must=[
                    qmodels.FieldCondition(
                        key="kb_name", match=qmodels.MatchValue(value=kb_name)
                    )
                ]
            )
        ),
    )
    # delete doc records from SQLite
    db.delete_kb(kb_name)
    # delete KB metadata
    db.delete_kb_meta(kb_name)
    # clean up uploaded files
    for d in docs:
        for f in glob.glob(os.path.join("data", "uploads", f"{d['id']}*")):
            remove_file(f)
    return APIResponse(message=f"KB '{kb_name}' deleted")
