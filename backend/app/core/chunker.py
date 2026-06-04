"""Novel-aware chunker.

Strategy:
1. Detect chapter boundaries (第X章, 第X回, etc.)
2. Within each chapter, split by paragraphs
3. Merge paragraphs into chunks of ~chunk_size tokens
4. Preserve chapter metadata for context expansion during retrieval

For non-novel text (no chapter markers), falls back to recursive splitting.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.config import settings
from app.core.retriever import ChunkRecord

logger = logging.getLogger(__name__)

# ── Token counting (tiktoken or fallback) ──────────────────────
try:
    import tiktoken

    _TIKTOKEN_ENC = tiktoken.get_encoding("cl100k_base")

    def count_tokens(text: str) -> int:
        return len(_TIKTOKEN_ENC.encode(text))

except ImportError:
    _TIKTOKEN_ENC = None

    def count_tokens(text: str) -> int:
        # Chinese ~1.5 chars/token, English ~4 chars/token
        chinese_chars = sum(1 for c in text if '一' <= c <= '鿿')
        other_chars = len(text) - chinese_chars
        return chinese_chars // 2 + other_chars // 4


# ── Chapter detection ─────────────────────────────────────────
_CHAPTER_RE = re.compile(
    r"^(第[0-9零一二三四五六七八九十百千万]+[章节回卷])",
    re.MULTILINE,
)


def _detect_chapters(text: str) -> list[tuple[str, int]]:
    """Find chapter markers and return [(chapter_title, start_position), ...].

    If no chapters found, returns a single pseudo-chapter covering the whole text.
    """
    matches = list(_CHAPTER_RE.finditer(text))
    if not matches or len(matches) < 3:
        # Fewer than 3 chapter markers → probably not a chapter-structured novel
        return []

    chapters = []
    for i, m in enumerate(matches):
        chapters.append((m.group(1).strip(), m.start()))
    return chapters


# ── Backward-compatible recursive chunker (fallback for non-novel) ──

_SEPARATORS = [
    "\n\n", "\r\n\r\n",
    "\n", "\r\n",
    "。", "！", "？",
    ". ", "! ", "? ",
    "；", "; ",
    "，", ", ",
    " ",
    "",
]


def _recursive_split(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """Original recursive splitter used as fallback."""
    import copy
    separators = copy.copy(_SEPARATORS)
    return _split_impl(text, 0, separators, chunk_size, chunk_overlap)


def _split_impl(text: str, sep_idx: int, seps: list[str], cs: int, co: int) -> list[str]:
    if sep_idx >= len(seps) or seps[sep_idx] == "":
        return _split_by_size(text, cs, co)

    sep = seps[sep_idx]
    parts = text.split(sep)
    parts = [parts[0]] + [sep + p for p in parts[1:]]
    parts = [p for p in parts if p]

    if len(parts) == 1:
        return _split_impl(text, sep_idx + 1, seps, cs, co)

    return _merge_parts(parts, sep, sep_idx, seps, cs, co)


def _merge_parts(parts: list[str], sep: str, sep_idx: int, seps: list[str], cs: int, co: int) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for part in parts:
        plen = count_tokens(part)
        if plen > cs:
            if current:
                chunks.append("".join(current))
                overlap = _extract_overlap(current, co)
                current = [overlap] if overlap else []
                current_len = count_tokens("".join(current))
            chunks.extend(_split_impl(part, sep_idx + 1, seps, cs, co))
            continue

        if current_len + plen > cs and current:
            chunks.append("".join(current))
            overlap = _extract_overlap(current, co)
            current = [overlap] if overlap else []
            current_len = count_tokens("".join(current))

        current.append(part)
        current_len += plen

    if current:
        chunks.append("".join(current))

    return chunks


def _split_by_size(text: str, cs: int, co: int) -> list[str]:
    chars = list(text)
    chunks: list[str] = []
    step = max(1, cs - co)
    i = 0
    while i < len(chars):
        end = min(i + cs, len(chars))
        chunk = "".join(chars[i:end])
        if count_tokens(chunk) <= cs * 1.2:
            chunks.append(chunk)
            i += step
        else:
            mid = (i + end) // 2
            chunks.append("".join(chars[i:mid]))
            chunks.append("".join(chars[mid:end]))
            i = end
    return chunks


def _extract_overlap(parts: list[str], target: int) -> str:
    if not parts or target <= 0:
        return ""
    full = "".join(parts)
    return _take_suffix_by_tokens(full, target)


def _take_suffix_by_tokens(text: str, target: int) -> str:
    if count_tokens(text) <= target:
        return text
    chars = list(text)
    suffix: list[str] = []
    for ch in reversed(chars):
        suffix.insert(0, ch)
        if count_tokens("".join(suffix)) >= target:
            break
    return "".join(suffix)


# ── Main Chunker ──────────────────────────────────────────────

class Chunker:
    """Chapter-aware text chunker.

    For novels: detects chapter boundaries, chunks within each chapter.
    For non-novels: falls back to recursive semantic splitting.
    """

    def __init__(
        self,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
    ):
        self.chunk_size = chunk_size or settings.chunk_size
        self.chunk_overlap = chunk_overlap or settings.chunk_overlap

    def split(self, text: str) -> list[str]:
        """Split text into chunks. Uses chapter-aware splitting when possible."""
        if not text:
            return []

        chapters = _detect_chapters(text)
        if chapters:
            logger.info(f"Detected {len(chapters)} chapters → chapter-aware chunking")
            return self._split_by_chapters(text, chapters)
        else:
            logger.info("No chapter markers detected → recursive chunking")
            return _recursive_split(text, self.chunk_size, self.chunk_overlap)

    def split_with_records(
        self,
        text: str,
        doc_id: str = "",
        filename: str = "",
        kb_name: str = "",
    ) -> list[ChunkRecord]:
        """Split text and return ChunkRecords with chapter metadata."""
        if not text:
            return []

        chapters = _detect_chapters(text)
        if chapters:
            return self._split_by_chapters_with_meta(text, chapters, doc_id, filename, kb_name)
        else:
            # Fallback: use old split method, wrap in records
            chunks = _recursive_split(text, self.chunk_size, self.chunk_overlap)
            return [
                ChunkRecord(
                    doc_id=doc_id, filename=filename, kb_name=kb_name,
                    chunk_index=i, text=c,
                )
                for i, c in enumerate(chunks)
            ]

    # ── Chapter-aware splitting ────────────────────────────────

    def _split_by_chapters(self, text: str, chapters: list[tuple[str, int]]) -> list[str]:
        """Split by chapters then merge paragraphs into chunks."""
        all_chunks: list[str] = []
        for i, (title, start) in enumerate(chapters):
            end = chapters[i + 1][1] if i + 1 < len(chapters) else len(text)
            chapter_text = text[start:end]
            chapter_chunks = self._split_one_chapter(chapter_text)
            all_chunks.extend(chapter_chunks)
        return all_chunks

    def _split_by_chapters_with_meta(
        self,
        text: str,
        chapters: list[tuple[str, int]],
        doc_id: str,
        filename: str,
        kb_name: str,
    ) -> list[ChunkRecord]:
        """Split by chapters with full metadata for each chunk."""
        records: list[ChunkRecord] = []
        global_idx = 0

        for ci, (title, start) in enumerate(chapters):
            end = chapters[ci + 1][1] if ci + 1 < len(chapters) else len(text)
            chapter_text = text[start:end]
            chapter_chunks = self._split_one_chapter(chapter_text)

            for li, chunk_text in enumerate(chapter_chunks):
                prev_text = chapter_chunks[li - 1] if li > 0 else ""
                next_text = chapter_chunks[li + 1] if li + 1 < len(chapter_chunks) else ""
                records.append(ChunkRecord(
                    doc_id=doc_id, filename=filename, kb_name=kb_name,
                    chunk_index=global_idx,
                    text=chunk_text,
                    chapter_title=title,
                    chapter_index=ci,
                    prev_chunk_text=prev_text,
                    next_chunk_text=next_text,
                ))
                global_idx += 1

        return records

    def _split_one_chapter(self, chapter_text: str) -> list[str]:
        """Split a single chapter into chunks.

        Steps:
        1. Split by double-newline (paragraphs), fall back to single newline (lines)
        2. Merge paragraphs/lines into ~chunk_size token chunks
        3. Only use recursive split as last resort for truly oversized pieces
        """
        # Try double-newline first (proper paragraphs)
        blocks = re.split(r"(\r?\n\r?\n)", chapter_text)
        if len(blocks) <= 3 and "\n" in chapter_text:
            # No double-newline found → use single newlines (dialogue-heavy writing)
            blocks = re.split(r"(\r?\n)", chapter_text)

        # Re-merge separator-pieces into their preceding text
        merged: list[str] = []
        buf = ""
        for piece in blocks:
            if re.match(r"^\r?\n(\r?\n)?$", piece):
                buf += piece
            else:
                if buf:
                    merged.append(buf)
                buf = piece
        if buf:
            merged.append(buf)

        merged = [p for p in merged if p.strip()]
        if not merged:
            return []

        # Merge blocks into ~chunk_size token chunks
        chunks: list[str] = []
        current_parts: list[str] = []
        current_len = 0

        for block in merged:
            blen = count_tokens(block)

            # If a single block exceeds chunk_size (rare: very long paragraph)
            # try splitting by sentence endings before falling back to recursive
            if blen > self.chunk_size:
                if current_parts:
                    chunks.append("".join(current_parts))
                    olap = _extract_overlap(current_parts, self.chunk_overlap)
                    current_parts = [olap] if olap else []
                    current_len = count_tokens("".join(current_parts))

                # Split oversized block by sentence endings first
                sub = re.split(r"([。！？!?])", block)
                sub = ["".join(sub[i:i+2]) for i in range(0, len(sub)-1, 2)] + ([sub[-1]] if len(sub) % 2 else [])
                sub = [s for s in sub if s.strip()]

                for s in sub:
                    slen = count_tokens(s)
                    if current_len + slen > self.chunk_size and current_parts:
                        chunks.append("".join(current_parts))
                        olap = _extract_overlap(current_parts, self.chunk_overlap)
                        current_parts = [olap] if olap else []
                        current_len = count_tokens("".join(current_parts))
                    current_parts.append(s)
                    current_len += slen
                continue

            if current_len + blen > self.chunk_size and current_parts:
                chunks.append("".join(current_parts))
                olap = _extract_overlap(current_parts, self.chunk_overlap)
                current_parts = [olap] if olap else []
                current_len = count_tokens("".join(current_parts))

            current_parts.append(block)
            current_len += blen

        if current_parts:
            chunks.append("".join(current_parts))

        return chunks
