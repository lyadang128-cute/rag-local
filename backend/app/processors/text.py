import logging

import aiofiles

from app.processors.base import BaseProcessor

logger = logging.getLogger(__name__)

# Common encodings for Chinese text files, tried in order
_TEXT_ENCODINGS = ["utf-8", "gbk", "gb18030", "gb2312", "big5", "latin-1"]


class TextProcessor(BaseProcessor):
    """Handles .txt and .md files with automatic encoding detection."""

    @staticmethod
    def _detect_encoding(raw: bytes) -> str:
        """Try to decode raw bytes by probing common Chinese encodings."""
        for enc in _TEXT_ENCODINGS:
            try:
                raw.decode(enc)
                return enc
            except (UnicodeDecodeError, LookupError):
                continue
        return "utf-8"  # fallback, may fail

    async def extract(self, file_path: str) -> list[str]:
        # Read raw bytes first
        async with aiofiles.open(file_path, mode="rb") as f:
            raw = await f.read()

        if not raw:
            return []

        encoding = self._detect_encoding(raw)
        logger.info(f"Detected encoding: {encoding} for {file_path}")

        content = raw.decode(encoding) if encoding != "utf-8" else raw.decode("utf-8")
        return [content] if content.strip() else []
