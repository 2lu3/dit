"""SQLite-backed file stat index for tracked content."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True)
class IndexEntry:
    """Cached file metadata and content hash for one path."""

    path: str
    size: int
    mtime_ns: int
    inode: int
    hash: str
    pushed_at: str | None = None


class StatIndex:
    """Persistent index of file stats and hashes."""

    def __init__(self, db_path: Path) -> None:
        """Open or create the index database at db_path."""
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._ensure_schema()

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    def __enter__(self) -> Self:
        """Enter the context manager."""
        return self

    def __exit__(self, *_exc: object) -> None:
        """Exit the context manager and close the database."""
        self.close()

    def _ensure_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS entries (
                path TEXT PRIMARY KEY,
                size INTEGER NOT NULL,
                mtime_ns INTEGER NOT NULL,
                inode INTEGER NOT NULL,
                hash TEXT NOT NULL,
                pushed_at TEXT
            )
            """
        )
        self._conn.commit()

    def get(self, path: str) -> IndexEntry | None:
        """Return the index entry for a path, if any."""
        row = self._conn.execute(
            "SELECT path, size, mtime_ns, inode, hash, pushed_at FROM entries WHERE path = ?",
            (path,),
        ).fetchone()
        if row is None:
            return None
        return IndexEntry(
            path=row["path"],
            size=row["size"],
            mtime_ns=row["mtime_ns"],
            inode=row["inode"],
            hash=row["hash"],
            pushed_at=row["pushed_at"],
        )

    def upsert(self, entry: IndexEntry) -> None:
        """Insert or update an index entry."""
        self._conn.execute(
            """
            INSERT INTO entries (path, size, mtime_ns, inode, hash, pushed_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                size=excluded.size,
                mtime_ns=excluded.mtime_ns,
                inode=excluded.inode,
                hash=excluded.hash,
                pushed_at=excluded.pushed_at
            """,
            (
                entry.path,
                entry.size,
                entry.mtime_ns,
                entry.inode,
                entry.hash,
                entry.pushed_at,
            ),
        )
        self._conn.commit()

    def mark_pushed(self, path: str, pushed_at: str) -> None:
        """Record the push timestamp for a path."""
        self._conn.execute(
            "UPDATE entries SET pushed_at = ? WHERE path = ?",
            (pushed_at, path),
        )
        self._conn.commit()

    def delete(self, path: str) -> None:
        """Delete the index entry for a path."""
        self._conn.execute("DELETE FROM entries WHERE path = ?", (path,))
        self._conn.commit()

    def all_entries(self) -> list[IndexEntry]:
        """Return all index entries."""
        rows = self._conn.execute(
            "SELECT path, size, mtime_ns, inode, hash, pushed_at FROM entries"
        ).fetchall()
        return [
            IndexEntry(
                path=row["path"],
                size=row["size"],
                mtime_ns=row["mtime_ns"],
                inode=row["inode"],
                hash=row["hash"],
                pushed_at=row["pushed_at"],
            )
            for row in rows
        ]


def file_stat_tuple(path: Path) -> tuple[int, int, int]:
    """Return size, mtime_ns, and inode for a file path."""
    st = path.stat()
    return (st.st_size, st.st_mtime_ns, getattr(st, "st_ino", 0))


def stats_match(entry: IndexEntry, size: int, mtime_ns: int, inode: int) -> bool:
    """Return whether an entry matches the given file stats."""
    return entry.size == size and entry.mtime_ns == mtime_ns and entry.inode == inode
