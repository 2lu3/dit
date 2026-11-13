"""push / pull / sync のオーケストレーション."""

from __future__ import annotations

import shutil
import subprocess
from collections import Counter
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

from dit.core.config import load_config
from dit.core.content import resolve_content_hash, utc_now_iso, write_pointer_for_file
from dit.core.errors import ConfigError, PointerError, RemoteError, RepoError
from dit.core.hasher import hash_file
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
    DELETE_LOCAL = "delete_local"
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


class PlanProgress(Protocol):
    """転送計画のファイル確認進捗."""

    def set_total(self, total_files: int) -> None:
        """確認するファイルの総数を設定する."""
        ...

    def advance(self) -> None:
        """確認済みファイルを 1 件加算する."""
        ...


@dataclass
class SyncStep:
    """計画済みの同期 1 件."""

    result: SyncResult
    transfer: TransferJob | None = None


@dataclass
class _RemoteCheck:
    """リモートの存在確認後に選ぶ同期ステップ."""

    content_hash: str
    if_present: list[SyncStep]
    if_missing: list[SyncStep]


_TRANSFER_ACTIONS = frozenset({SyncAction.PUSH, SyncAction.PULL})


def require_remote(config: DitConfig) -> Remote:
    """設定されたリモートを開く。未設定なら例外を送出する."""
    if config.remote is None:
        msg = "remote is not configured in dit.toml"
        raise ConfigError(msg)
    return open_remote(config.remote)


def plan_push(repo: Repo, *, progress: PlanProgress | None = None) -> list[TransferJob]:
    """アップロード対象を収集する."""
    config = load_config(repo)
    remote = require_remote(config)
    return collect_push_jobs(repo, remote, progress=progress)


def plan_pull(repo: Repo, *, progress: PlanProgress | None = None) -> list[TransferJob]:
    """ダウンロード対象を収集する."""
    return collect_pull_jobs(repo, Scope(repo), progress=progress)


def plan_sync(repo: Repo, *, progress: PlanProgress | None = None) -> list[SyncStep]:
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
        return _plan_all(ctx, config, progress=progress)


def collect_sync_jobs(steps: list[SyncStep]) -> list[TransferJob]:
    """計画済みステップから転送ジョブだけを取り出す."""
    return [
        step.transfer
        for step in steps
        if step.transfer is not None and step.result.action in _TRANSFER_ACTIONS
    ]


def collect_push_jobs(
    repo: Repo,
    remote: Remote,
    *,
    progress: PlanProgress | None = None,
) -> list[TransferJob]:
    """未アップロードの実体を列挙する."""
    pointer_files = iter_pointer_files(repo)
    if progress is not None:
        progress.set_total(len(pointer_files))
    jobs: list[TransferJob] = []
    for path in pointer_files:
        job = _push_job(repo, read_pointer(path))
        if job is not None:
            jobs.append(job)
        elif progress is not None:
            progress.advance()
    presence = _check_remote_hashes(remote, [job.content_hash for job in jobs], progress)
    return [job for job in jobs if not presence[job.content_hash]]


def _check_remote_hashes(
    remote: Remote,
    content_hashes: list[str],
    progress: PlanProgress | None,
) -> dict[str, bool]:
    counts = Counter(content_hashes)

    def checked(content_hash: str) -> None:
        if progress is not None:
            for _ in range(counts[content_hash]):
                progress.advance()

    return remote.exists_many(content_hashes, on_checked=checked)


def collect_pull_jobs(
    repo: Repo,
    scope: Scope,
    *,
    progress: PlanProgress | None = None,
) -> list[TransferJob]:
    """Scope 内で欠落している実体を列挙する."""
    pointer_files = iter_pointer_files(repo)
    if progress is not None:
        progress.set_total(len(pointer_files))
    jobs: list[TransferJob] = []
    for path in pointer_files:
        job = _pull_job(repo, scope, read_pointer(path))
        if job is not None:
            jobs.append(job)
        if progress is not None:
            progress.advance()
    return jobs


def _push_job(
    repo: Repo,
    pointer: Pointer,
) -> TransferJob | None:
    data_path = repo.abs(pointer.path)
    if not data_path.is_file():
        return None
    if hash_file(data_path) != pointer.hash:
        msg = f"{pointer.path}: local content differs from pointer; run dit add first"
        raise RepoError(msg)
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
    """リモートに無いローカル実体をアップロードする."""
    config = load_config(repo)
    remote = require_remote(config)
    pending = jobs if jobs is not None else collect_push_jobs(repo, remote)
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
    if hash_file(job.data_path) != job.content_hash:
        msg = f"{job.path}: local content differs from pointer; run dit add first"
        raise RepoError(msg)
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
    _download_jobs(repo, remote, pending, progress)
    return [SyncResult(job.path, SyncAction.PULL, "download") for job in pending]


def _download_jobs(
    repo: Repo,
    remote: Remote,
    jobs: list[TransferJob],
    progress: TransferProgress | None,
) -> None:
    if not jobs:
        return
    remote.download_many(
        [(job.content_hash, job.data_path) for job in jobs],
        progress=_byte_callback(progress),
        on_start=lambda path: _notify_path(progress, repo.rel(path)),
    )


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
        results = _apply_steps(ctx, pending, progress)
        if prune_remote:
            results.extend(_prune_remote_orphans(repo, remote, dry_run=dry_run))
    return results


def _plan_all(
    ctx: SyncCtx,
    config: DitConfig,
    *,
    progress: PlanProgress | None = None,
) -> list[SyncStep]:
    items = _iter_sync_items(ctx.repo, config)
    if progress is not None:
        progress.set_total(len(items))
    plans: list[list[SyncStep] | _RemoteCheck] = []
    for item in items:
        plan = _plan_item(ctx, item)
        plans.append(plan)
        if not isinstance(plan, _RemoteCheck) and progress is not None:
            progress.advance()
    presence = _check_remote_hashes(
        ctx.remote,
        [plan.content_hash for plan in plans if isinstance(plan, _RemoteCheck)],
        progress,
    )
    steps: list[SyncStep] = []
    for plan in plans:
        if isinstance(plan, _RemoteCheck):
            steps.extend(plan.if_present if presence[plan.content_hash] else plan.if_missing)
        else:
            steps.extend(plan)
    return steps


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


def _plan_item(ctx: SyncCtx, item: SyncItem) -> list[SyncStep] | _RemoteCheck:
    if not ctx.scope.contains(item.rel):
        return _plan_outside_scope(ctx, item)
    has_data = item.data_path.is_file()
    if item.pointer is not None and has_data:
        return _plan_both(ctx, item)
    if item.pointer is not None:
        return _plan_pointer_only(item)
    if has_data:
        return [_status_step(item, SyncAction.WARNING, "missing pointer or untracked")]
    return []


def _plan_outside_scope(ctx: SyncCtx, item: SyncItem) -> list[SyncStep]:  # noqa: PLR0911
    if not item.data_path.is_file():
        return []
    if item.pointer is None:
        return [_status_step(item, SyncAction.WARNING, "kept: missing pointer; run dit add")]
    expected_path = ctx.repo.root / item.rel
    if expected_path.resolve() != expected_path.absolute() or item.data_path != expected_path:
        return [_status_step(item, SyncAction.WARNING, "kept: symbolic link")]
    if hash_file(item.data_path) != item.pointer.hash:
        return [_status_step(item, SyncAction.WARNING, "kept: local content differs from pointer")]
    try:
        present = ctx.remote.exists(item.pointer.hash)
    except RemoteError as exc:
        return [_status_step(item, SyncAction.WARNING, f"kept: remote check failed: {exc}")]
    if not present:
        return [_status_step(item, SyncAction.WARNING, "kept: content missing from remote")]
    return [
        _transfer_step(
            item,
            SyncAction.DELETE_LOCAL,
            "remove local content",
            item.pointer.hash,
            item.pointer.size,
        )
    ]


def _plan_both(ctx: SyncCtx, item: SyncItem) -> _RemoteCheck:
    pointer = _require_pointer(item)
    local_hash = resolve_content_hash(ctx.repo, ctx.index, item.data_path)
    if local_hash == pointer.hash:
        return _plan_after_active(item, pointer.hash, pointer.size)
    return _plan_both_mismatch(ctx, item, local_hash)


def _plan_after_active(
    item: SyncItem,
    content_hash: str,
    size: int,
) -> _RemoteCheck:
    return _RemoteCheck(
        content_hash,
        if_present=[_status_step(item, SyncAction.OK, "in sync")],
        if_missing=[_transfer_step(item, SyncAction.PUSH, "upload", content_hash, size)],
    )


def _is_local_newer(ctx: SyncCtx, item: SyncItem) -> bool:
    pointer = _require_pointer(item)
    data_mtime = item.data_path.stat().st_mtime_ns
    pointer_mtime = (ctx.repo.root / pointer.pointer_relpath).stat().st_mtime_ns
    return data_mtime >= pointer_mtime


def _plan_both_mismatch(ctx: SyncCtx, item: SyncItem, local_hash: str) -> _RemoteCheck:
    pointer = _require_pointer(item)
    if _is_local_newer(ctx, item):
        size = item.data_path.stat().st_size
        updated = _transfer_step(item, SyncAction.UPDATE_POINTER, "local newer", local_hash, size)
        return _RemoteCheck(
            local_hash,
            if_present=[updated],
            if_missing=[updated, _transfer_step(item, SyncAction.PUSH, "upload", local_hash, size)],
        )
    return _RemoteCheck(
        pointer.hash,
        if_present=[
            _transfer_step(item, SyncAction.PULL, "pointer newer", pointer.hash, pointer.size)
        ],
        if_missing=[_status_step(item, SyncAction.ERROR, "pointer newer but remote missing")],
    )


def _plan_pointer_only(item: SyncItem) -> _RemoteCheck:
    pointer = _require_pointer(item)
    return _RemoteCheck(
        pointer.hash,
        if_present=[_transfer_step(item, SyncAction.PULL, "download", pointer.hash, pointer.size)],
        if_missing=[_status_step(item, SyncAction.ERROR, "file not found locally or remotely")],
    )


def _apply_steps(
    ctx: SyncCtx,
    steps: list[SyncStep],
    progress: TransferProgress | None,
) -> list[SyncResult]:
    if not ctx.dry_run:
        downloads: list[TransferJob] = []
        for step in steps:
            if step.transfer is None:
                continue
            if step.result.action == SyncAction.PULL:
                downloads.append(step.transfer)
                continue
            # pointer 更新や push より前に、それまでの pull を完了させる。
            _download_jobs(ctx.repo, ctx.remote, downloads, progress)
            downloads.clear()
            _execute_step(ctx, step, progress)
        _download_jobs(ctx.repo, ctx.remote, downloads, progress)
    return [step.result for step in steps]


def _execute_step(
    ctx: SyncCtx,
    step: SyncStep,
    progress: TransferProgress | None,
) -> None:
    job = step.transfer
    if job is None:
        return
    action = step.result.action
    if action == SyncAction.DELETE_LOCAL:
        try:
            pointer = read_pointer(ctx.repo.root / (job.path + ".dit"))
        except (OSError, PointerError):
            step.result.action = SyncAction.WARNING
            step.result.message = "kept: pointer unavailable"
            return
        item = SyncItem(job.path, job.data_path, pointer)
        checked = _plan_outside_scope(ctx, item)
        if (
            pointer.path != job.path
            or ctx.scope.contains(job.path)
            or not checked
            or checked[0].result.action != SyncAction.DELETE_LOCAL
        ):
            step.result.action = SyncAction.WARNING
            step.result.message = (
                checked[0].result.message
                if checked and checked[0].result.action != SyncAction.DELETE_LOCAL
                else "kept: pointer, file or scope changed"
            )
            return
        job.data_path.unlink()
        return
    if action == SyncAction.UPDATE_POINTER:
        write_pointer_for_file(ctx.repo, ctx.index, job.data_path, job.content_hash)
        return
    if action == SyncAction.PUSH:
        _upload_job(ctx.remote, ctx.index, job, progress)
        return


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
    referenced.update(pointer.hash for pointer in _load_pointers(repo).values())
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
