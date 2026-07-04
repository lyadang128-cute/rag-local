from __future__ import annotations

import asyncio
import glob
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.core.retriever import Retriever
from app.models.schemas import APIResponse, DocumentListOut, DocumentOut, ImportRequest
from app.tasks.ingestion import process_document_async, process_url_async, get_progress
from app.config import settings
from app.utils.db import db
from app.utils.file import detect_processor, remove_file, save_upload, validate_file_magic

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])

ALLOWED_EXTENSIONS = {
    ".txt", ".md", ".pdf", ".docx", ".xlsx", ".pptx",
    ".png", ".jpg", ".jpeg", ".bmp", ".tiff",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _get_retriever() -> Retriever:
    return Retriever()


@router.post("/upload", response_model=APIResponse)
async def upload_documents(
    files: list[UploadFile] = File(...),
    kb_name: str = Form("default"),
):
    """Upload documents. Returns 200 immediately with status='processing'.
    Documents are parsed, chunked, embedded, and indexed in a background thread.
    """
    results: list[DocumentOut] = []
    saved_files: list[tuple[str, str, str, str]] = []  # (doc_id, path, filename, kb_name)

    for f in files:
        filename = f.filename or "unknown"
        ext = Path(filename).suffix.lower()

        # Validate
        if ext not in ALLOWED_EXTENSIONS:
            results.append(DocumentOut(
                id="", filename=filename, size=0, status="failed",
                chunk_count=0, kb_name=kb_name, created_at=_now(),
            ))
            continue

        content = await f.read()
        if len(content) > settings.max_upload_size:
            results.append(DocumentOut(
                id="", filename=filename, size=len(content), status="failed",
                chunk_count=0, kb_name=kb_name, created_at=_now(),
            ))
            continue

        # Validate file type by magic bytes (not just extension)
        if not validate_file_magic(ext, content):
            results.append(DocumentOut(
                id="", filename=filename, size=len(content), status="failed",
                chunk_count=0, kb_name=kb_name, created_at=_now(),
            ))
            continue

        processor_key = detect_processor(ext)
        if processor_key is None:
            results.append(DocumentOut(
                id="", filename=filename, size=len(content), status="failed",
                chunk_count=0, kb_name=kb_name, created_at=_now(),
            ))
            continue

        # Save to disk
        file_id, saved_path = await save_upload(content, filename)

        # Insert DB row as "processing"
        db.insert_document(
            doc_id=file_id, filename=filename, size=len(content),
            status="processing", chunk_count=0, kb_name=kb_name,
        )

        # Schedule background processing in a daemon thread (survives 30+ min)
        threading.Thread(
            target=lambda: asyncio.run(process_document_async(
                doc_id=file_id,
                file_path=saved_path,
                filename=filename,
                kb_name=kb_name,
            )),
            daemon=True,
        ).start()

        entry = db.get_document(file_id)
        results.append(DocumentOut(**entry) if entry else DocumentOut(
            id=file_id, filename=filename, size=len(content),
            status="processing", chunk_count=0, kb_name=kb_name, created_at=_now(),
        ))

    return APIResponse(data={"documents": [r.model_dump() for r in results]})


@router.post("/import", response_model=APIResponse)
async def import_from_url(
    body: ImportRequest,
):
    """Import from URL. Returns 200 immediately, processing happens in background thread."""
    url = body.url
    kb_name = body.kb_name
    doc_id = str(hash(url) % 10 ** 12)

    # Deduplicate
    existing = db.get_document(doc_id)
    if existing and existing.get("status") == "indexed":
        return APIResponse(
            message="URL already imported",
            data={"documents": [DocumentOut(**existing).model_dump()]},
        )

    # Insert as "processing"
    db.insert_document(
        doc_id=doc_id, filename=url, size=0,
        status="processing", chunk_count=0, kb_name=kb_name,
    )

    # Schedule background processing in a daemon thread
    threading.Thread(
        target=lambda: asyncio.run(process_url_async(
            doc_id=doc_id,
            url=url,
            kb_name=kb_name,
        )),
        daemon=True,
    ).start()

    entry = db.get_document(doc_id)
    return APIResponse(data={"documents": [DocumentOut(**entry).model_dump()]})


@router.get("", response_model=APIResponse)
async def list_documents(
    kb_name: str | None = None,
    page: int = 1,
    page_size: int = 20,
):
    items, total = db.list_documents(kb_name=kb_name, page=page, page_size=page_size)
    return APIResponse(
        data=DocumentListOut(
            items=items, total=total, page=page, page_size=page_size,
        ).model_dump()
    )


@router.get("/{doc_id}/progress", response_model=APIResponse)
async def get_document_progress(doc_id: str):
    """Get ingestion progress for a document."""
    prog = get_progress(doc_id)
    if prog:
        return APIResponse(data=prog)
    # Fallback: check DB status
    entry = db.get_document(doc_id)
    if entry:
        if entry["status"] == "indexed":
            return APIResponse(data={"status": "done", "current": entry.get("chunk_count", 0), "total": entry.get("chunk_count", 0)})
        if entry["status"] == "failed":
            return APIResponse(data={"status": "failed", "current": 0, "total": 0})
    return APIResponse(data={"status": "unknown", "current": 0, "total": 0})


@router.get("/{doc_id}/preview", response_model=APIResponse)
async def preview_document(doc_id: str):
    """Get a text preview from the uploaded file (first 2000 chars)."""
    import glob as _glob
    upload_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "uploads"
    )
    matches = _glob.glob(os.path.join(upload_dir, f"{doc_id}*"))
    if not matches:
        raise HTTPException(status_code=404, detail="文件不存在")
    file_path = matches[0]
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            text = f.read(2000)
        return APIResponse(data={"chunks": [text], "total": 1})
    except UnicodeDecodeError:
        return APIResponse(data={"chunks": ["（二进制文件，无法预览）"], "total": 1})


@router.get("/{doc_id}", response_model=APIResponse)
async def get_document(doc_id: str):
    entry = db.get_document(doc_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return APIResponse(data=DocumentOut(**entry).model_dump())


@router.delete("/{doc_id}", response_model=APIResponse)
async def delete_document(
    doc_id: str,
    retriever: Retriever = Depends(_get_retriever),
):
    # Try DB delete first (may already be gone from manual cleanup)
    entry = db.delete_document(doc_id)

    # Always try to clean up vectors (even if DB record was already missing)
    try:
        await retriever.delete_by_doc(doc_id)
    except Exception:
        logger.warning(f"Failed to delete vectors for doc_id={doc_id}", exc_info=True)

    # Clean up uploaded file(s) — use absolute path relative to backend dir
    upload_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "uploads")
    for pattern in (os.path.join(upload_dir, f"{doc_id}*"),):
        for f in glob.glob(pattern):
            try:
                remove_file(f)
            except Exception:
                logger.warning(f"Failed to remove file: {f}", exc_info=True)

    if entry is None:
        return APIResponse(message="already deleted (no DB record)")
    return APIResponse(message="deleted")
