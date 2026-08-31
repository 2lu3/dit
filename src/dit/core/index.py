"""追跡コンテンツ用の SQLite ベース file stat インデックス."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True)
class IndexEntry:
    """1 パス分のキャッシュ済みファイルメタデータとコンテンツハッシュ."""

    path: str
    size: int
    mtime_ns: int
    inode: int
    hash: str
    pushed_at: str | None = None


class StatIndex:
    """ファイル stat とハッシュの永続インデックス."""

    def __init__(self, db_path: Path) -> None:
        """db_path のインデックス DB を開くか作成する."""
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._ensure_schema()

    def close(self) -> None:
        """データベース接続を閉じる."""
        self._conn.close()

    def __enter__(self) -> Self:
        """コンテキストマネージャに入る."""
        return self

    def __exit__(self, *_exc: object) -> None:
        """コンテキストマネージャを抜け、データベースを閉じる."""
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
        """パスに対応するインデックスエントリがあれば返す."""
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
        """インデックスエントリを挿入または更新する."""
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
        """パスの push 時刻を記録する."""
        self._conn.execute(
            "UPDATE entries SET pushed_at = ? WHERE path = ?",
            (pushed_at, path),
        )
        self._conn.commit()

    def delete(self, path: str) -> None:
        """パスのインデックスエントリを削除する."""
        self._conn.execute("DELETE FROM entries WHERE path = ?", (path,))
        self._conn.commit()

    def all_entries(self) -> list[IndexEntry]:
        """すべてのインデックスエントリを返す."""
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
    """ファイルパスの size / mtime_ns / inode を返す."""
    st = path.stat()
    return (st.st_size, st.st_mtime_ns, getattr(st, "st_ino", 0))


def stats_match(entry: IndexEntry, size: int, mtime_ns: int, inode: int) -> bool:
    """エントリが指定の file stats と一致するかを返す."""
    return entry.size == size and entry.mtime_ns == mtime_ns and entry.inode == inode
