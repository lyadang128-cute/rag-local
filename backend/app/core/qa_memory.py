"""QA Memory — lightweight persistent memory for corrected answers.

Stores (question, answer, embedding) in a SQLite table.
On each new question, checks for semantically similar memorized questions
and returns the memorized answer directly, bypassing the RAG pipeline.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

DB_DIR = Path(__file__).resolve().parent.parent.parent / "data"
DB_PATH = DB_DIR / "qa_memory.db"

SIMILARITY_THRESHOLD = 0.85  # cosine similarity >= 0.85 -> use memorized answer
UPSERT_THRESHOLD = 0.98     # similarity >= 0.98 -> same question, update instead of insert
MAX_SCAN_ROWS = 500         # max rows to scan per search (most recent)


def _ensure_db() -> sqlite3.Connection:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS qa_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            embedding TEXT NOT NULL,  -- JSON list[float]
            kb_name TEXT NOT NULL DEFAULT 'default',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_qa_memory_kb
        ON qa_memory(kb_name, id DESC)
    """)
    conn.commit()
    return conn


def _cosine_similarity_batch(query: np.ndarray, stored: np.ndarray) -> np.ndarray:
    """Vectorized cosine similarity between one query vector and N stored vectors.

    query: (D,)     stored: (N, D)     returns: (N,)
    """
    query_norm = np.linalg.norm(query)
    stored_norms = np.linalg.norm(stored, axis=1)
    denom = query_norm * stored_norms
    denom[denom == 0] = 1.0
    return np.dot(stored, query) / denom


# ── Public API ────────────────────────────────────────────────


async def save(
    question: str,
    answer: str,
    embedding: list[float],
    kb_name: str = "default",
    overwrite: bool = False,
) -> bool:
    """Save a Q&A pair to memory. Returns True if saved, False if skipped.

    - If a very similar question already exists (sim >= UPSERT_THRESHOLD) and
      overwrite=False, the save is SKIPPED to protect existing entries from being
      overwritten by auto-save.
    - If overwrite=True (e.g. /correct endpoint), the existing entry is UPDATED.
    - If no similar question exists, a new row is INSERTED.
    """
    conn = _ensure_db()
    emb_array = np.asarray(embedding, dtype=np.float32)

    # Check for existing similar questions (limited to recent rows)
    rows = conn.execute(
        "SELECT id, answer, embedding FROM qa_memory WHERE kb_name = ? ORDER BY id DESC LIMIT ?",
        (kb_name, MAX_SCAN_ROWS),
    ).fetchall()

    if rows:
        stored_embs = np.asarray([json.loads(r[2]) for r in rows], dtype=np.float32)
        sims = _cosine_similarity_batch(emb_array, stored_embs)
        best_idx = int(np.argmax(sims))
        best_sim = float(sims[best_idx])

        if best_sim >= UPSERT_THRESHOLD:
            row_id = rows[best_idx][0]
            if overwrite:
                conn.execute(
                    "UPDATE qa_memory SET question=?, answer=?, embedding=? WHERE id=?",
                    (question, answer, json.dumps(embedding), row_id),
                )
                conn.commit()
                conn.close()
                logger.info(
                    f"QA memory updated (sim={best_sim:.3f}): {question[:40]}..."
                )
                return True
            else:
                conn.close()
                logger.info(
                    f"QA memory: similar question exists (sim={best_sim:.3f}), "
                    f"skipping auto-save to protect existing entry"
                )
                return False

    # No similar question found — insert new
    conn.execute(
        "INSERT INTO qa_memory (question, answer, embedding, kb_name) VALUES (?, ?, ?, ?)",
        (question, answer, json.dumps(embedding), kb_name),
    )
    conn.commit()
    conn.close()
    logger.info(f"QA memory saved: {question[:40]}...")
    return True


async def search(question_embedding: list[float], kb_name: str = "default") -> tuple[str, float] | None:
    """Search QA memory for a similar question.

    Returns (answer, similarity_score) if found, None otherwise.
    Uses numpy vectorized cosine similarity over the most recent MAX_SCAN_ROWS entries.
    """
    conn = _ensure_db()
    rows = conn.execute(
        "SELECT question, answer, embedding FROM qa_memory WHERE kb_name = ? ORDER BY id DESC LIMIT ?",
        (kb_name, MAX_SCAN_ROWS),
    ).fetchall()
    conn.close()

    if not rows:
        return None

    query_vec = np.asarray(question_embedding, dtype=np.float32)
    stored_embs = np.asarray([json.loads(r[2]) for r in rows], dtype=np.float32)
    sims = _cosine_similarity_batch(query_vec, stored_embs)

    best_idx = int(np.argmax(sims))
    best_score = float(sims[best_idx])

    if best_score >= SIMILARITY_THRESHOLD:
        logger.info(f"QA memory hit: similarity={best_score:.3f}")
        return rows[best_idx][1], best_score

    return None


async def find_similar(
    embedding: list[float],
    kb_name: str = "default",
) -> tuple[str, float] | None:
    """Like search() but returns (question, sim) instead of (answer, sim).

    Used by /correct fallback to find which question to update.
    """
    conn = _ensure_db()
    rows = conn.execute(
        "SELECT question, embedding FROM qa_memory WHERE kb_name = ? ORDER BY id DESC LIMIT ?",
        (kb_name, MAX_SCAN_ROWS),
    ).fetchall()
    conn.close()

    if not rows:
        return None

    query_vec = np.asarray(embedding, dtype=np.float32)
    stored_embs = np.asarray([json.loads(r[1]) for r in rows], dtype=np.float32)
    sims = _cosine_similarity_batch(query_vec, stored_embs)

    best_idx = int(np.argmax(sims))
    best_score = float(sims[best_idx])

    if best_score >= 0.6:
        return rows[best_idx][0], best_score
    return None


def stats(kb_name: str = "default") -> dict:
    """Return memory stats for a knowledge base."""
    conn = _ensure_db()
    count = conn.execute(
        "SELECT COUNT(*) FROM qa_memory WHERE kb_name = ?", (kb_name,)
    ).fetchone()[0]
    conn.close()
    return {"total_qa_pairs": count}
