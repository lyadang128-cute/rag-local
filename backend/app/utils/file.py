from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path

import aiofiles

from app.config import settings

logger = logging.getLogger(__name__)

EXT_PROCESSOR_MAP: dict[str, str] = {
    ".txt": "text",
    ".md": "text",
    ".pdf": "pdf",
    ".docx": "docx",
    ".xlsx": "excel",
    ".pptx": "ppt",
    ".png": "ocr",
    ".jpg": "ocr",
    ".jpeg": "ocr",
    ".bmp": "ocr",
    ".tiff": "ocr",
}

# Magic bytes for file type verification
MAGIC_BYTES: dict[str, list[bytes]] = {
    ".pdf": [b"%PDF"],
    ".docx": [b"PK\x03\x04"],  # ZIP-based OOXML
    ".xlsx": [b"PK\x03\x04"],
    ".pptx": [b"PK\x03\x04"],
    ".png": [b"\x89PNG\r\n\x1a\n"],
    ".jpg": [b"\xff\xd8\xff"],
    ".jpeg": [b"\xff\xd8\xff"],
    ".bmp": [b"BM"],
    ".tiff": [b"II*\x00", b"MM\x00*"],
    # .txt and .md have no reliable magic bytes — skip
}


def detect_processor(ext: str) -> str | None:
    return EXT_PROCESSOR_MAP.get(ext.lower())


def validate_file_magic(ext: str, content: bytes) -> bool:
    """Check file content matches its claimed extension via magic bytes.

    Returns True if the file appears valid for its extension.
    Skips text-based formats (.txt, .md) that lack reliable magic bytes.
    """
    signatures = MAGIC_BYTES.get(ext.lower())
    if signatures is None:
        return True  # No signature to check (txt, md, etc.)
    return any(content.startswith(sig) for sig in signatures)


async def save_upload(file_content: bytes, original_name: str) -> tuple[str, str]:
    """Save uploaded file to disk. Returns (file_id, saved_path)."""
    file_id = str(uuid.uuid4())
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    ext = Path(original_name).suffix.lower()
    saved_name = f"{file_id}{ext}"
    saved_path = upload_dir / saved_name

    async with aiofiles.open(saved_path, "wb") as f:
        await f.write(file_content)

    return file_id, str(saved_path)


def remove_file(file_path: str | None) -> None:
    if file_path and os.path.exists(file_path):
        os.remove(file_path)
