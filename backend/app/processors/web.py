import asyncio

import trafilatura

from app.processors.base import BaseProcessor


class WebProcessor(BaseProcessor):
    """Scrape text content from a URL.  Not for local file — call directly with url."""

    async def extract(self, file_path: str) -> list[str]:
        """
        file_path is overloaded: for web imports this receives the URL string.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._extract_sync, file_path)

    @staticmethod
    def _extract_sync(url: str) -> list[str]:
        downloaded = trafilatura.fetch_url(url)
        if downloaded is None:
            return []
        text = trafilatura.extract(downloaded, include_comments=False, include_tables=True)
        if text is None or not text.strip():
            return []
        return [text]
