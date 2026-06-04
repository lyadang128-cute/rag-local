import asyncio

import fitz  # PyMuPDF

from app.processors.base import BaseProcessor


class PDFProcessor(BaseProcessor):
    async def extract(self, file_path: str) -> list[str]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._extract_sync, file_path)

    def _extract_sync(self, file_path: str) -> list[str]:
        doc = fitz.open(file_path)
        pages: list[str] = []
        for page in doc:
            text = page.get_text()
            if text.strip():
                pages.append(text)
        doc.close()
        return pages
