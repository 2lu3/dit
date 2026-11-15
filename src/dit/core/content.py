"""ローカル実体のハッシュとポインタ補助."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from dit.core.errors import RepoError
from dit.core.hasher import hash_file
from dit.core.index import IndexEntry, file_stat_tuple, stats_match
from dit.core.pointer import Pointer, ensure_gitignore_entry, write_pointer

if TYPE_CHECKING:
    from pathlib import Path

    from dit.core.index import StatIndex
    from dit.core.repo import Repo


def resolve_content_hash(repo: Repo, index: StatIndex, data_path: Path) -> str:
    """可能なら stat インデックスキャッシュを使い、コンテンツハッシュを返す."""
    rel = repo.rel(data_path)
    before = file_stat_tuple(data_path)
    size, mtime_ns, inode, ctime_ns = before
    cached = index.get(rel)
    if cached is not None and stats_match(cached, *before):
        return cached.hash
    digest = hash_file(data_path)
    if file_stat_tuple(data_path) != before:
        msg = f"{rel}: local content changed while hashing; retry when the file is stable"
        raise RepoError(msg)
    index.upsert(
        IndexEntry(
            path=rel,
            size=size,
            mtime_ns=mtime_ns,
            inode=inode,
            ctime_ns=ctime_ns,
            hash=digest,
            pushed_at=cached.pushed_at if cached and cached.hash == digest else None,
        )
    )
    return digest


def write_pointer_for_file(
    repo: Repo,
    index: StatIndex,
    data_path: Path,
    content_hash: str | None = None,
) -> Pointer:
    """ローカル実体のポインタを書き込み、gitignore を更新する."""
    rel = repo.rel(data_path)
    digest = content_hash or resolve_content_hash(repo, index, data_path)
    size = data_path.stat().st_size
    pointer = Pointer(path=rel, hash=digest, size=size)
    write_pointer(repo.root, pointer)
    ensure_gitignore_entry(data_path, data_path.name)
    return pointer


def utc_now_iso() -> str:
    """現在の UTC 時刻を ISO-8601 文字列で返す."""
    return datetime.now(UTC).replace(microsecond=0).isoformat()
