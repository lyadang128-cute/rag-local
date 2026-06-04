from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings

DB_PATH = Path("data") / "rag.db"


def _row_to_dict(row: sqlite3.Row) -> dict:
    return dict(row)


class Database:
    def __init__(self, path: str | None = None):
        self._path = path or str(DB_PATH)
        self._local = threading.local()
        self._init_db()

    @property
    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self._path)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
        return self._local.conn

    def _init_db(self) -> None:
        Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                size INTEGER NOT NULL,
                status TEXT NOT NULL,
                chunk_count INTEGER NOT NULL DEFAULT 0,
                kb_name TEXT NOT NULL DEFAULT 'default',
                created_at TEXT NOT NULL
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_docs_kb ON documents(kb_name)"
        )
        self._conn.commit()

    def insert_document(
        self, doc_id: str, filename: str, size: int, status: str,
        chunk_count: int, kb_name: str,
    ) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO documents VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                doc_id, filename, size, status, chunk_count, kb_name,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self._conn.commit()

    def get_document(self, doc_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM documents WHERE id = ?", (doc_id,)
        ).fetchone()
        return _row_to_dict(row) if row else None

    def list_documents(self, kb_name: str | None = None, page: int = 1, page_size: int = 20) -> tuple[list[dict], int]:
        if kb_name:
            total = self._conn.execute(
                "SELECT COUNT(*) FROM documents WHERE kb_name = ?", (kb_name,)
            ).fetchone()[0]
            rows = self._conn.execute(
                "SELECT * FROM documents WHERE kb_name = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (kb_name, page_size, (page - 1) * page_size),
            ).fetchall()
        else:
            total = self._conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            rows = self._conn.execute(
                "SELECT * FROM documents ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (page_size, (page - 1) * page_size),
            ).fetchall()
        return [_row_to_dict(r) for r in rows], total

    def delete_document(self, doc_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM documents WHERE id = ?", (doc_id,)
        ).fetchone()
        if row is None:
            return None
        self._conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        self._conn.commit()
        return _row_to_dict(row)

    def list_kb_names(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT DISTINCT kb_name FROM documents ORDER BY kb_name"
        ).fetchall()
        return [r["kb_name"] for r in rows]

    def delete_kb(self, kb_name: str) -> int:
        cur = self._conn.execute(
            "DELETE FROM documents WHERE kb_name = ?", (kb_name,)
        )
        self._conn.commit()
        return cur.rowcount

    def delete_all(self) -> int:
        cur = self._conn.execute("DELETE FROM documents")
        self._conn.commit()
        return cur.rowcount


db = Database()
