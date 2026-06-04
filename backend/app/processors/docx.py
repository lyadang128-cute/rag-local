import asyncio

import docx

from app.processors.base import BaseProcessor


class DocxProcessor(BaseProcessor):
    async def extract(self, file_path: str) -> list[str]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._extract_sync, file_path)

    def _extract_sync(self, file_path: str) -> list[str]:
        doc = docx.Document(file_path)
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return ["\n".join(paragraphs)] if paragraphs else []
