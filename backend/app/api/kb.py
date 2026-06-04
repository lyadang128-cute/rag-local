import glob
import os

from fastapi import APIRouter, Depends

from app.core.retriever import Retriever
from app.models.schemas import APIResponse
from app.utils.db import db
from app.utils.file import remove_file
from qdrant_client.http import models as qmodels

router = APIRouter(prefix="/kb", tags=["kb"])


def _get_retriever() -> Retriever:
    return Retriever()


@router.get("/list", response_model=APIResponse)
async def list_kb():
    names = db.list_kb_names()
    return APIResponse(data={"kb_names": names})


@router.get("/{kb_name}", response_model=APIResponse)
async def kb_stats(kb_name: str, retriever: Retriever = Depends(_get_retriever)):
    try:
        count = retriever.count(kb_name=kb_name)
    except Exception:
        count = 0
    docs, total = db.list_documents(kb_name=kb_name, page=1, page_size=1)
    return APIResponse(
        data={
            "kb_name": kb_name,
            "document_count": total,
            "chunk_count": count,
            "total_size_bytes": 0,
        }
    )


@router.delete("/{kb_name}", response_model=APIResponse)
async def delete_kb(kb_name: str, retriever: Retriever = Depends(_get_retriever)):
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
    # clean up uploaded files
    for d in docs:
        for f in glob.glob(os.path.join("data", "uploads", f"{d['id']}*")):
            remove_file(f)
    return APIResponse(message=f"KB '{kb_name}' deleted")
