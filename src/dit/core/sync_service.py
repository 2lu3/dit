"""Push, pull, and sync orchestration."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from dit.core.config import load_config
from dit.core.content import resolve_content_hash, utc_now_iso, write_pointer_for_file
from dit.core.errors import ConfigError, RepoError
from dit.core.index import StatIndex
from dit.core.pointer import Pointer, read_pointer
from dit.core.remote.s3 import open_remote
from dit.core.scope import Scope
from dit.core.tracker import iter_pointer_files, iter_tracked_files

if TYPE_CHECKING:
    from pathlib import Path

    from dit.core.config import DitConfig
    from dit.core.remote.base import Remote
    from dit.core.repo import Repo

GIT_FETCH_TIMEOUT_S = 600
GIT_REV_LIST_TIMEOUT_S = 600
GIT_LS_TREE_TIMEOUT_S = 120
GIT_SHOW_TIMEOUT_S = 60


class SyncAction(StrEnum):
    """Outcome label for one sync path."""

    OK = "ok"
    PUSH = "push"
    PULL = "pull"
    UPDATE_POINTER = "update_pointer"
    DELETE_LOCAL = "delete_local"
    DELETE_REMOTE = "delete_remote"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class SyncResult:
    """Result row for a sync operation."""

    path: str
    action: SyncAction
    message: str


@dataclass
class SyncCtx:
    """Shared inputs for sync helpers."""

    repo: Repo
    index: StatIndex
    remote: Remote
    scope: Scope
    dry_run: bool


@dataclass
class SyncItem:
    """One tracked or pointer path under consideration."""

    rel: str
    data_path: Path
    pointer: Pointer | None = None


def require_remote(config: DitConfig) -> Remote:
    """Open the configured remote or raise if missing."""
    if config.remote is None:
        msg = "remote is not configured in dit.toml"
        raise ConfigError(msg)
    return open_remote(config.remote)


def run_push(repo: Repo, *, dry_run: bool = False) -> list[SyncResult]:
    """Upload local content missing from the remote."""
    config = load_config(repo)
    remote = require_remote(config)
    results: list[SyncResult] = []
    with StatIndex(repo.index_db) as index:
        for pointer_path in iter_pointer_files(repo):
            pointer = read_pointer(pointer_path)
            data_path = repo.abs(pointer.path)
            if not data_path.is_file():
                continue
            if remote.exists(pointer.hash):
                continue
            results.append(SyncResult(pointer.path, SyncAction.PUSH, "upload"))
            if not dry_run:
                remote.upload(data_path, pointer.hash)
                index.mark_pushed(pointer.path, utc_now_iso())
    return results


def run_pull(repo: Repo, *, dry_run: bool = False) -> list[SyncResult]:
    """Download remote content for in-scope missing local files."""
    config = load_config(repo)
    remote = require_remote(config)
    scope = Scope(repo)
    results: list[SyncResult] = []
    for pointer_path in iter_pointer_files(repo):
        pointer = read_pointer(pointer_path)
        if not scope.contains(pointer.path):
            continue
        data_path = repo.abs(pointer.path)
        if data_path.is_file():
            continue
        results.append(SyncResult(pointer.path, SyncAction.PULL, "download"))
        if not dry_run:
            remote.download(pointer.hash, data_path)
    return results


def run_sync(
    repo: Repo,
    *,
    dry_run: bool = False,
    prune_remote: bool = False,
) -> list[SyncResult]:
    """Reconcile local files, pointers, and remote objects."""
    config = load_config(repo)
    remote = require_remote(config)
    scope = Scope(repo)
    results: list[SyncResult] = []
    with StatIndex(repo.index_db) as index:
        tracked = {repo.rel(path): path for path in iter_tracked_files(repo, config)}
        pointers: dict[str, Pointer] = {}
        for pointer_path in iter_pointer_files(repo):
            pointer = read_pointer(pointer_path)
            pointers[pointer.path] = pointer

        ctx = SyncCtx(
            repo=repo,
            index=index,
            remote=remote,
            scope=scope,
            dry_run=dry_run,
        )
        for rel in sorted(set(tracked) | set(pointers)):
            data_path = tracked.get(rel) or repo.abs(rel)
            results.extend(
                _sync_one(
                    ctx,
                    SyncItem(rel=rel, data_path=data_path, pointer=pointers.get(rel)),
                )
            )
        if prune_remote:
            results.extend(_prune_remote_orphans(repo, remote, dry_run=dry_run))
    return results


def _sync_one(ctx: SyncCtx, item: SyncItem) -> list[SyncResult]:
    has_data = item.data_path.is_file()
    if item.pointer is not None and has_data:
        return _sync_both(ctx, item)
    if item.pointer is not None and not has_data:
        return _sync_pointer_only(ctx, item)
    if item.pointer is None and has_data:
        return [SyncResult(item.rel, SyncAction.WARNING, "missing pointer or untracked")]
    return []


def _sync_both(ctx: SyncCtx, item: SyncItem) -> list[SyncResult]:
    pointer = _require_pointer(item)
    local_hash = resolve_content_hash(ctx.repo, ctx.index, item.data_path)
    active = pointer
    results: list[SyncResult] = []

    if local_hash != pointer.hash:
        results.extend(_resolve_hash_mismatch(ctx, item, local_hash=local_hash))
        if results and results[-1].action == SyncAction.ERROR:
            return results
        if not ctx.dry_run:
            active = read_pointer(ctx.repo.root / pointer.pointer_relpath)
        else:
            data_mtime = item.data_path.stat().st_mtime_ns
            pointer_mtime = (ctx.repo.root / pointer.pointer_relpath).stat().st_mtime_ns
            if data_mtime >= pointer_mtime:
                active = Pointer(
                    path=item.rel,
                    hash=local_hash,
                    size=item.data_path.stat().st_size,
                )

    remote_has = ctx.remote.exists(active.hash)
    if has_local_needing_push(item.data_path, remote_has=remote_has):
        results.append(SyncResult(item.rel, SyncAction.PUSH, "upload"))
        if not ctx.dry_run:
            ctx.remote.upload(item.data_path, active.hash)
            ctx.index.mark_pushed(item.rel, utc_now_iso())
            remote_has = True

    if not ctx.scope.contains(item.rel):
        return results + _delete_local_if_safe(
            ctx.remote,
            item.rel,
            item.data_path,
            active.hash,
            dry_run=ctx.dry_run,
        )

    if not results:
        results.append(SyncResult(item.rel, SyncAction.OK, "in sync"))
    return results


def has_local_needing_push(data_path: Path, *, remote_has: bool) -> bool:
    """Return True when local data exists and remote lacks the object."""
    return data_path.is_file() and not remote_has


def _require_pointer(item: SyncItem) -> Pointer:
    if item.pointer is None:
        msg = f"pointer required for {item.rel}"
        raise RepoError(msg)
    return item.pointer


def _resolve_hash_mismatch(
    ctx: SyncCtx,
    item: SyncItem,
    *,
    local_hash: str,
) -> list[SyncResult]:
    pointer = _require_pointer(item)
    data_mtime = item.data_path.stat().st_mtime_ns
    pointer_mtime = (ctx.repo.root / pointer.pointer_relpath).stat().st_mtime_ns
    if data_mtime >= pointer_mtime:
        results = [SyncResult(item.rel, SyncAction.UPDATE_POINTER, "local newer")]
        if not ctx.dry_run:
            write_pointer_for_file(ctx.repo, ctx.index, item.data_path, local_hash)
        return results

    if not ctx.remote.exists(pointer.hash):
        return [SyncResult(item.rel, SyncAction.ERROR, "pointer newer but remote missing")]
    if ctx.scope.contains(item.rel):
        if not ctx.dry_run:
            ctx.remote.download(pointer.hash, item.data_path)
        return [SyncResult(item.rel, SyncAction.PULL, "pointer newer")]
    return _delete_local_if_safe(
        ctx.remote,
        item.rel,
        item.data_path,
        pointer.hash,
        dry_run=ctx.dry_run,
    )


def _sync_pointer_only(ctx: SyncCtx, item: SyncItem) -> list[SyncResult]:
    pointer = _require_pointer(item)
    if not ctx.remote.exists(pointer.hash):
        return [SyncResult(item.rel, SyncAction.ERROR, "file not found locally or remotely")]
    if not ctx.scope.contains(item.rel):
        return [SyncResult(item.rel, SyncAction.OK, "out of scope; no local copy")]
    if not ctx.dry_run:
        ctx.remote.download(pointer.hash, item.data_path)
    return [SyncResult(item.rel, SyncAction.PULL, "download")]


def _delete_local_if_safe(
    remote: Remote,
    rel: str,
    data_path: Path,
    content_hash: str,
    *,
    dry_run: bool,
) -> list[SyncResult]:
    if not remote.exists(content_hash):
        return [SyncResult(rel, SyncAction.ERROR, "cannot delete local; remote missing")]
    if not dry_run and data_path.is_file():
        data_path.unlink()
    return [SyncResult(rel, SyncAction.DELETE_LOCAL, "out of scope")]


def _prune_remote_orphans(
    repo: Repo,
    remote: Remote,
    *,
    dry_run: bool,
) -> list[SyncResult]:
    _git_fetch_all(repo)
    referenced = _hashes_from_all_refs(repo)
    results: list[SyncResult] = []
    for content_hash in remote.list_hashes():
        if content_hash in referenced:
            continue
        results.append(SyncResult(content_hash, SyncAction.DELETE_REMOTE, "orphan"))
        if not dry_run:
            remote.delete(content_hash)
    return results


def _git_executable() -> str:
    git = shutil.which("git")
    if git is None:
        msg = "git executable not found on PATH"
        raise RepoError(msg)
    return git


def _git_fetch_all(repo: Repo) -> None:
    git = _git_executable()
    try:
        subprocess.run(  # noqa: S603 — fixed git argv; path from shutil.which
            [git, "fetch", "--all", "--prune"],
            cwd=repo.root,
            check=True,
            capture_output=True,
            text=True,
            timeout=GIT_FETCH_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired, subprocess.CalledProcessError) as exc:
        msg = f"git fetch --all --prune failed: {exc}"
        raise RepoError(msg) from exc


def _hashes_from_all_refs(repo: Repo) -> set[str]:
    git = _git_executable()
    try:
        commits = subprocess.run(  # noqa: S603 — fixed git argv; path from shutil.which
            [git, "rev-list", "--all"],
            cwd=repo.root,
            check=True,
            capture_output=True,
            text=True,
            timeout=GIT_REV_LIST_TIMEOUT_S,
        ).stdout.splitlines()
    except (OSError, subprocess.TimeoutExpired, subprocess.CalledProcessError) as exc:
        msg = f"git rev-list --all failed: {exc}"
        raise RepoError(msg) from exc

    hashes: set[str] = set()
    for commit in commits:
        names = _ls_tree_names(repo, commit)
        for name in names:
            if not name.endswith(".dit"):
                continue
            digest = _hash_from_blob(repo, commit, name)
            if digest:
                hashes.add(digest)
    for pointer_path in iter_pointer_files(repo):
        hashes.add(read_pointer(pointer_path).hash)
    return hashes


def _ls_tree_names(repo: Repo, commit: str) -> list[str]:
    git = _git_executable()
    try:
        result = subprocess.run(  # noqa: S603 — fixed git argv; path from shutil.which
            [git, "ls-tree", "-r", "--name-only", commit],
            cwd=repo.root,
            check=True,
            capture_output=True,
            text=True,
            timeout=GIT_LS_TREE_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
        return []
    return result.stdout.splitlines()


def _hash_from_blob(repo: Repo, commit: str, name: str) -> str | None:
    git = _git_executable()
    try:
        blob = subprocess.run(  # noqa: S603 — fixed git argv; path from shutil.which
            [git, "show", f"{commit}:{name}"],
            cwd=repo.root,
            check=True,
            capture_output=True,
            text=True,
            timeout=GIT_SHOW_TIMEOUT_S,
        ).stdout
    except (OSError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
        return None
    for line in blob.splitlines():
        if line.startswith("hash = "):
            return line.split("=", 1)[1].strip().strip('"')
    return None
