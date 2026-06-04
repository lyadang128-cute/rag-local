from abc import ABC, abstractmethod


class BaseProcessor(ABC):
    """Extract plain text from a file.  Returns a list of text segments (pages/sections)."""

    @abstractmethod
    async def extract(self, file_path: str) -> list[str]:
        ...
