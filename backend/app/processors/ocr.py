import asyncio

from app.processors.base import BaseProcessor


class OCRProcessor(BaseProcessor):
    """Image OCR using PaddleOCR.  Supports .png .jpg .jpeg .bmp .tiff."""

    _ocr = None

    @classmethod
    def _get_ocr(cls):
        if cls._ocr is None:
            from paddleocr import PaddleOCR

            cls._ocr = PaddleOCR(lang="ch", use_angle_cls=True)
        return cls._ocr

    async def extract(self, file_path: str) -> list[str]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._extract_sync, file_path)

    def _extract_sync(self, file_path: str) -> list[str]:
        ocr = self._get_ocr()
        results = ocr.ocr(file_path)
        if not results or not results[0]:
            return []
        lines: list[str] = []
        for line in results[0]:
            text = line[1][0]
            if text.strip():
                lines.append(text)
        return ["\n".join(lines)] if lines else []
