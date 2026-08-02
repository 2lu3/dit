"""Local content hash and pointer helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from dit.core.hasher import hash_file
from dit.core.index import IndexEntry, file_stat_tuple, stats_match
from dit.core.pointer import Pointer, ensure_gitignore_entry, write_pointer

if TYPE_CHECKING:
    from pathlib import Path

    from dit.core.index import StatIndex
    from dit.core.repo import Repo


def resolve_content_hash(repo: Repo, index: StatIndex, data_path: Path) -> str:
    """Return content hash, using the stat index cache when possible."""
    rel = repo.rel(data_path)
    size, mtime_ns, inode = file_stat_tuple(data_path)
    cached = index.get(rel)
    if cached is not None and stats_match(cached, size, mtime_ns, inode):
        return cached.hash
    digest = hash_file(data_path)
    index.upsert(
        IndexEntry(
            path=rel,
            size=size,
            mtime_ns=mtime_ns,
            inode=inode,
            hash=digest,
            pushed_at=cached.pushed_at if cached else None,
        )
    )
    return digest


def write_pointer_for_file(
    repo: Repo,
    index: StatIndex,
    data_path: Path,
    content_hash: str | None = None,
) -> Pointer:
    """Write a pointer file for local data and update gitignore."""
    rel = repo.rel(data_path)
    digest = content_hash or resolve_content_hash(repo, index, data_path)
    size, _, _ = file_stat_tuple(data_path)
    pointer = Pointer(path=rel, hash=digest, size=size)
    write_pointer(repo.root, pointer)
    ensure_gitignore_entry(data_path, data_path.name)
    return pointer


def utc_now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).replace(microsecond=0).isoformat()
