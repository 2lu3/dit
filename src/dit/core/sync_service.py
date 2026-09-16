"""push / pull / sync のオーケストレーション."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

from dit.core.config import load_config
from dit.core.content import resolve_content_hash, utc_now_iso, write_pointer_for_file
from dit.core.errors import ConfigError, RepoError
from dit.core.index import StatIndex
from dit.core.pointer import Pointer, read_pointer
from dit.core.remote.s3 import open_remote
from dit.core.scope import Scope
from dit.core.tracker import iter_pointer_files, iter_tracked_files

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from dit.core.config import DitConfig
    from dit.core.remote.base import Remote
    from dit.core.repo import Repo

GIT_FETCH_TIMEOUT_S = 600
GIT_REV_LIST_TIMEOUT_S = 600
GIT_LS_TREE_TIMEOUT_S = 120
GIT_SHOW_TIMEOUT_S = 60


class SyncAction(StrEnum):
    """同期対象 1 パスの結果ラベル."""

    OK = "ok"
    PUSH = "push"
    PULL = "pull"
    UPDATE_POINTER = "update_pointer"
    DELETE_REMOTE = "delete_remote"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class SyncResult:
    """同期操作の結果 1 行."""

    path: str
    action: SyncAction
    message: str


@dataclass
class SyncCtx:
    """同期ヘルパー共有の入力."""

    repo: Repo
    index: StatIndex
    remote: Remote
    scope: Scope
    dry_run: bool


@dataclass
class SyncItem:
    """処理対象の追跡パスまたはポインタパス."""

    rel: str
    data_path: Path
    pointer: Pointer | None = None


@dataclass
class TransferJob:
    """1 ファイル分の転送対象."""

    path: str
    data_path: Path
    content_hash: str
    size: int


class TransferProgress(Protocol):
    """バイト転送の進捗通知."""

    def add_bytes(self, amount: int) -> None:
        """転送増分バイトを記録する."""
        ...

    def set_path(self, path: str) -> None:
        """現在転送中のパスを表示する."""
        ...


@dataclass
class SyncStep:
    """計画済みの同期 1 件."""

    result: SyncResult
    transfer: TransferJob | None = None


_TRANSFER_ACTIONS = frozenset({SyncAction.PUSH, SyncAction.PULL})


def require_remote(config: DitConfig) -> Remote:
    """設定されたリモートを開く。未設定なら例外を送出する."""
    if config.remote is None:
        msg = "remote is not configured in dit.toml"
        raise ConfigError(msg)
    return open_remote(config.remote)


def plan_push(repo: Repo) -> list[TransferJob]:
    """アップロード対象を収集する."""
    config = load_config(repo)
    remote = require_remote(config)
    return collect_push_jobs(repo, remote, Scope(repo))


def plan_pull(repo: Repo) -> list[TransferJob]:
    """ダウンロード対象を収集する."""
    return collect_pull_jobs(repo, Scope(repo))


def plan_sync(repo: Repo) -> list[SyncStep]:
    """同期の更新と転送を計画する."""
    config = load_config(repo)
    remote = require_remote(config)
    with StatIndex(repo.index_db) as index:
        ctx = SyncCtx(
            repo=repo,
            index=index,
            remote=remote,
            scope=Scope(repo),
            dry_run=True,
        )
        return _plan_all(ctx, config)


def collect_sync_jobs(steps: list[SyncStep]) -> list[TransferJob]:
    """計画済みステップから転送ジョブだけを取り出す."""
    return [
        step.transfer
        for step in steps
        if step.transfer is not None and step.result.action in _TRANSFER_ACTIONS
    ]


def collect_push_jobs(repo: Repo, remote: Remote, scope: Scope) -> list[TransferJob]:
    """Scope 内で未アップロードの実体を列挙する."""
    jobs = [_push_job(repo, remote, scope, read_pointer(path)) for path in iter_pointer_files(repo)]
    return [job for job in jobs if job is not None]


def collect_pull_jobs(repo: Repo, scope: Scope) -> list[TransferJob]:
    """Scope 内で欠落している実体を列挙する."""
    jobs = [_pull_job(repo, scope, read_pointer(path)) for path in iter_pointer_files(repo)]
    return [job for job in jobs if job is not None]


def _push_job(
    repo: Repo,
    remote: Remote,
    scope: Scope,
    pointer: Pointer,
) -> TransferJob | None:
    if not scope.contains(pointer.path):
        return None
    data_path = repo.abs(pointer.path)
    if not data_path.is_file() or remote.exists(pointer.hash):
        return None
    return TransferJob(
        path=pointer.path,
        data_path=data_path,
        content_hash=pointer.hash,
        size=data_path.stat().st_size,
    )


def _pull_job(repo: Repo, scope: Scope, pointer: Pointer) -> TransferJob | None:
    if not scope.contains(pointer.path):
        return None
    data_path = repo.abs(pointer.path)
    if data_path.is_file():
        return None
    return TransferJob(
        path=pointer.path,
        data_path=data_path,
        content_hash=pointer.hash,
        size=pointer.size,
    )


def _byte_callback(progress: TransferProgress | None) -> Callable[[int], None] | None:
    if progress is None:
        return None
    return progress.add_bytes


def _notify_path(progress: TransferProgress | None, path: str) -> None:
    if progress is not None:
        progress.set_path(path)


def run_push(
    repo: Repo,
    *,
    dry_run: bool = False,
    progress: TransferProgress | None = None,
    jobs: list[TransferJob] | None = None,
) -> list[SyncResult]:
    """Scope 内でリモートに無いローカル実体をアップロードする."""
    config = load_config(repo)
    remote = require_remote(config)
    pending = jobs if jobs is not None else collect_push_jobs(repo, remote, Scope(repo))
    if dry_run:
        return [SyncResult(job.path, SyncAction.PUSH, "upload") for job in pending]
    with StatIndex(repo.index_db) as index:
        return [_upload_job(remote, index, job, progress) for job in pending]


def _upload_job(
    remote: Remote,
    index: StatIndex,
    job: TransferJob,
    progress: TransferProgress | None,
) -> SyncResult:
    _notify_path(progress, job.path)
    remote.upload(job.data_path, job.content_hash, progress=_byte_callback(progress))
    index.mark_pushed(job.path, utc_now_iso())
    return SyncResult(job.path, SyncAction.PUSH, "upload")


def run_pull(
    repo: Repo,
    *,
    dry_run: bool = False,
    progress: TransferProgress | None = None,
    jobs: list[TransferJob] | None = None,
) -> list[SyncResult]:
    """Scope 内で欠落しているローカルファイルへリモート実体をダウンロードする."""
    config = load_config(repo)
    remote = require_remote(config)
    pending = jobs if jobs is not None else collect_pull_jobs(repo, Scope(repo))
    if dry_run:
        return [SyncResult(job.path, SyncAction.PULL, "download") for job in pending]
    return [_download_job(remote, job, progress) for job in pending]


def _download_job(
    remote: Remote,
    job: TransferJob,
    progress: TransferProgress | None,
) -> SyncResult:
    _notify_path(progress, job.path)
    remote.download(job.content_hash, job.data_path, progress=_byte_callback(progress))
    return SyncResult(job.path, SyncAction.PULL, "download")


def run_sync(
    repo: Repo,
    *,
    dry_run: bool = False,
    prune_remote: bool = False,
    progress: TransferProgress | None = None,
    steps: list[SyncStep] | None = None,
) -> list[SyncResult]:
    """ローカル実体・ポインタ・リモートオブジェクトを突き合わせる."""
    config = load_config(repo)
    remote = require_remote(config)
    with StatIndex(repo.index_db) as index:
        ctx = SyncCtx(
            repo=repo,
            index=index,
            remote=remote,
            scope=Scope(repo),
            dry_run=dry_run,
        )
        pending = steps if steps is not None else _plan_all(ctx, config)
        results = [_apply_step(ctx, step, progress) for step in pending]
        if prune_remote:
            results.extend(_prune_remote_orphans(repo, remote, dry_run=dry_run))
    return results


def _plan_all(ctx: SyncCtx, config: DitConfig) -> list[SyncStep]:
    return [step for item in _iter_sync_items(ctx.repo, config) for step in _plan_item(ctx, item)]


def _load_pointers(repo: Repo) -> dict[str, Pointer]:
    pointers: dict[str, Pointer] = {}
    for pointer_path in iter_pointer_files(repo):
        pointer = read_pointer(pointer_path)
        pointers[pointer.path] = pointer
    return pointers


def _iter_sync_items(repo: Repo, config: DitConfig) -> list[SyncItem]:
    tracked = {repo.rel(path): path for path in iter_tracked_files(repo, config)}
    pointers = _load_pointers(repo)
    rels = sorted(set(tracked) | set(pointers))
    return [
        SyncItem(rel=rel, data_path=tracked.get(rel) or repo.abs(rel), pointer=pointers.get(rel))
        for rel in rels
    ]


def _status_step(item: SyncItem, action: SyncAction, message: str) -> SyncStep:
    return SyncStep(SyncResult(item.rel, action, message), None)


def _transfer_step(
    item: SyncItem,
    action: SyncAction,
    message: str,
    content_hash: str,
    size: int,
) -> SyncStep:
    job = TransferJob(item.rel, item.data_path, content_hash, size)
    return SyncStep(SyncResult(item.rel, action, message), job)


def _plan_item(ctx: SyncCtx, item: SyncItem) -> list[SyncStep]:
    if not ctx.scope.contains(item.rel):
        return []
    has_data = item.data_path.is_file()
    if item.pointer is not None and has_data:
        return _plan_both(ctx, item)
    if item.pointer is not None:
        return _plan_pointer_only(ctx, item)
    if has_data:
        return [_status_step(item, SyncAction.WARNING, "missing pointer or untracked")]
    return []


def _plan_both(ctx: SyncCtx, item: SyncItem) -> list[SyncStep]:
    pointer = _require_pointer(item)
    local_hash = resolve_content_hash(ctx.repo, ctx.index, item.data_path)
    if local_hash == pointer.hash:
        return _plan_after_active(ctx, item, pointer.hash, pointer.size)
    return _plan_both_mismatch(ctx, item, local_hash)


def _plan_after_active(
    ctx: SyncCtx,
    item: SyncItem,
    content_hash: str,
    size: int,
) -> list[SyncStep]:
    steps = _plan_push_if_needed(ctx, item, content_hash, size)
    return steps or [_status_step(item, SyncAction.OK, "in sync")]


def _plan_push_if_needed(
    ctx: SyncCtx,
    item: SyncItem,
    content_hash: str,
    size: int,
) -> list[SyncStep]:
    remote_has = ctx.remote.exists(content_hash)
    if not has_local_needing_push(item.data_path, remote_has=remote_has):
        return []
    return [_transfer_step(item, SyncAction.PUSH, "upload", content_hash, size)]


def _is_local_newer(ctx: SyncCtx, item: SyncItem) -> bool:
    pointer = _require_pointer(item)
    data_mtime = item.data_path.stat().st_mtime_ns
    pointer_mtime = (ctx.repo.root / pointer.pointer_relpath).stat().st_mtime_ns
    return data_mtime >= pointer_mtime


def _plan_both_mismatch(ctx: SyncCtx, item: SyncItem, local_hash: str) -> list[SyncStep]:
    pointer = _require_pointer(item)
    if _is_local_newer(ctx, item):
        size = item.data_path.stat().st_size
        updated = _transfer_step(item, SyncAction.UPDATE_POINTER, "local newer", local_hash, size)
        return [updated, *_plan_push_if_needed(ctx, item, local_hash, size)]
    if not ctx.remote.exists(pointer.hash):
        return [_status_step(item, SyncAction.ERROR, "pointer newer but remote missing")]
    return [_transfer_step(item, SyncAction.PULL, "pointer newer", pointer.hash, pointer.size)]


def _plan_pointer_only(ctx: SyncCtx, item: SyncItem) -> list[SyncStep]:
    pointer = _require_pointer(item)
    if not ctx.remote.exists(pointer.hash):
        return [_status_step(item, SyncAction.ERROR, "file not found locally or remotely")]
    return [_transfer_step(item, SyncAction.PULL, "download", pointer.hash, pointer.size)]


def _apply_step(
    ctx: SyncCtx,
    step: SyncStep,
    progress: TransferProgress | None,
) -> SyncResult:
    if not ctx.dry_run:
        _execute_step(ctx, step, progress)
    return step.result


def _execute_step(
    ctx: SyncCtx,
    step: SyncStep,
    progress: TransferProgress | None,
) -> None:
    job = step.transfer
    if job is None:
        return
    action = step.result.action
    if action == SyncAction.UPDATE_POINTER:
        write_pointer_for_file(ctx.repo, ctx.index, job.data_path, job.content_hash)
        return
    if action == SyncAction.PUSH:
        _upload_job(ctx.remote, ctx.index, job, progress)
        return
    if action == SyncAction.PULL:
        _download_job(ctx.remote, job, progress)


def has_local_needing_push(data_path: Path, *, remote_has: bool) -> bool:
    """ローカル実体がありリモートにオブジェクトが無いとき True を返す."""
    return data_path.is_file() and not remote_has


def _require_pointer(item: SyncItem) -> Pointer:
    if item.pointer is None:
        msg = f"pointer required for {item.rel}"
        raise RepoError(msg)
    return item.pointer


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
