"""Background document ingestion tasks.

Runs inside FastAPI BackgroundTasks — no extra infrastructure needed.
"""

from __future__ import annotations

import glob
import logging
import os
from pathlib import Path

from app.config import settings
from app.core.chunker import Chunker
from app.core.retriever import ChunkRecord
from app.core.embedder import Embedder
from app.core.retriever import Retriever
from app.processors import (
    DocxProcessor,
    ExcelProcessor,
    OCRProcessor,
    PDFProcessor,
    PPTProcessor,
    TextProcessor,
    WebProcessor,
)
from app.utils.db import db
from app.utils.file import detect_processor, remove_file

logger = logging.getLogger(__name__)

PROCESSORS = {
    "text": TextProcessor(),
    "pdf": PDFProcessor(),
    "docx": DocxProcessor(),
    "excel": ExcelProcessor(),
    "ppt": PPTProcessor(),
    "ocr": OCRProcessor(),
}

_chunker = Chunker()


async def process_document_async(
    doc_id: str,
    file_path: str,
    filename: str,
    kb_name: str,
    content_type: str | None = None,
) -> None:
    """Parse → chunk → embed → upsert a single uploaded file.

    Called by FastAPI BackgroundTasks after the upload endpoint returns 202.
    Updates the document row in SQLite on completion or failure.
    """
    logger.info(f"Background ingest started: doc_id={doc_id} file={filename}")
    try:
        # Detect processor by extension
        ext = Path(filename).suffix.lower()
        processor_key = detect_processor(ext)
        if processor_key is None:
            raise ValueError(f"Unsupported file type: {ext}")

        processor = PROCESSORS[processor_key]
        segments = await processor.extract(file_path)

        # Chunk — use chapter-aware splitting when possible
        full_text = "".join(segments)

        # Pull KB metadata for department tagging
        kb_meta = db.get_kb(kb_name) or {}
        department = kb_meta.get("department", "")
        access_level = kb_meta.get("access_level", 1)

        records = _chunker.split_with_records(
            full_text, doc_id=doc_id, filename=filename, kb_name=kb_name
        )
        if not records:
            records = [
                ChunkRecord(
                    doc_id=doc_id, filename=filename, kb_name=kb_name,
                    chunk_index=i, text=seg,
                    metadata={"department": department, "access_level": access_level},
                )
                for i, seg in enumerate(segments)
            ]
        else:
            for r in records:
                r.metadata["department"] = department
                r.metadata["access_level"] = access_level

        # Embed + upsert in batches (avoids OOM on large files)
        embedder = Embedder()
        retriever = Retriever()
        BATCH = 64
        all_texts = [r.text for r in records]
        for start in range(0, len(records), BATCH):
            batch_texts = all_texts[start : start + BATCH]
            batch_vectors = await embedder.embed(batch_texts)
            batch_records = records[start : start + BATCH]
            await retriever.upsert(batch_vectors, batch_records)
            logger.info(
                "Ingest progress: doc_id=%s %d/%d chunks",
                doc_id, start + len(batch_texts), len(records),
            )
        await embedder.close()

        # Mark as indexed
        db.insert_document(
            doc_id=doc_id,
            filename=filename,
            size=os.path.getsize(file_path) if os.path.exists(file_path) else 0,
            status="indexed",
            chunk_count=len(records),
            kb_name=kb_name,
        )
        logger.info(f"Ingest complete: doc_id={doc_id} chunks={len(records)}")

    except Exception:
        logger.exception(f"Ingest failed: doc_id={doc_id} file={filename}")
        db.insert_document(
            doc_id=doc_id,
            filename=filename,
            size=0,
            status="failed",
            chunk_count=0,
            kb_name=kb_name,
        )
        if file_path and os.path.exists(file_path):
            remove_file(file_path)


async def process_url_async(
    doc_id: str,
    url: str,
    kb_name: str,
) -> None:
    """Fetch URL → extract text → chunk → embed → upsert.

    Called by FastAPI BackgroundTasks after the import endpoint returns 202.
    """
    logger.info(f"Background URL ingest started: doc_id={doc_id} url={url}")
    try:
        processor = WebProcessor()
        segments = await processor.extract(url)
        if not segments:
            raise ValueError("No content extracted from URL")

        full_text = "".join(segments)
        records = _chunker.split_with_records(
            full_text, doc_id=doc_id, filename=url, kb_name=kb_name
        )
        if not records:
            records = [
                ChunkRecord(
                    doc_id=doc_id, filename=url, kb_name=kb_name,
                    chunk_index=i, text=seg, metadata={"source_url": url},
                )
                for i, seg in enumerate(segments)
            ]

        embedder = Embedder()
        retriever = Retriever()
        BATCH = 64
        all_texts = [r.text for r in records]
        for start in range(0, len(records), BATCH):
            batch_texts = all_texts[start : start + BATCH]
            batch_vectors = await embedder.embed(batch_texts)
            batch_records = records[start : start + BATCH]
            await retriever.upsert(batch_vectors, batch_records)
        await embedder.close()

        db.insert_document(
            doc_id=doc_id,
            filename=url,
            size=0,
            status="indexed",
            chunk_count=len(records),
            kb_name=kb_name,
        )
        logger.info(f"URL ingest complete: doc_id={doc_id} chunks={len(records)}")

    except Exception:
        logger.exception(f"URL ingest failed: doc_id={doc_id} url={url}")
        db.insert_document(
            doc_id=doc_id,
            filename=url,
            size=0,
            status="failed",
            chunk_count=0,
            kb_name=kb_name,
        )
