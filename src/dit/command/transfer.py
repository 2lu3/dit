"""dit push / pull / sync コマンド."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

import click

from dit.command.progress import ByteTransferBar
from dit.core.repo import require_initialized
from dit.core.sync_service import (
    SyncAction,
    collect_sync_jobs,
    plan_pull,
    plan_push,
    plan_sync,
    run_pull,
    run_push,
    run_sync,
)

if TYPE_CHECKING:
    from dit.core.repo import Repo
    from dit.core.sync_service import SyncResult, TransferJob, TransferProgress


class _TransferPlan(Protocol):
    def __call__(self, repo: Repo) -> list[TransferJob]: ...


class _TransferExecute(Protocol):
    def __call__(
        self,
        repo: Repo,
        *,
        dry_run: bool = False,
        progress: TransferProgress | None = None,
        jobs: list[TransferJob] | None = None,
    ) -> list[SyncResult]: ...


def _print_results(results: list[SyncResult]) -> int:
    errors = 0
    for item in results:
        click.echo(f"{item.action.value:16} {item.path}  ({item.message})")
        if item.action == SyncAction.ERROR:
            errors += 1
    return errors


def _finish(results: list[SyncResult]) -> None:
    if _print_results(results):
        raise SystemExit(1)


def _run_byte_transfer(
    *,
    title: str,
    dry_run: bool,
    plan: _TransferPlan,
    execute: _TransferExecute,
) -> list[SyncResult]:
    repo = require_initialized()
    jobs = plan(repo)
    total_bytes = sum(job.size for job in jobs)
    if dry_run or total_bytes == 0:
        return execute(repo, dry_run=dry_run, jobs=jobs)
    with ByteTransferBar(total_bytes, title) as bar:
        return execute(repo, jobs=jobs, progress=bar)


@click.command("push")
@click.option("--dry-run", is_flag=True, help="実行せずに予定だけ表示する")
def push_cmd(*, dry_run: bool) -> None:
    """Scope 内ポインタが指すローカルオブジェクトをアップロードする.

    転送中はバイト量を Kbyte / Mbyte / Gbyte の N/N で表示する.
    """
    try:
        results = _run_byte_transfer(
            title="push",
            dry_run=dry_run,
            plan=plan_push,
            execute=run_push,
        )
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        raise click.ClickException(str(exc)) from exc
    _finish(results)


@click.command("pull")
@click.option("--dry-run", is_flag=True, help="実行せずに予定だけ表示する")
def pull_cmd(*, dry_run: bool) -> None:
    """欠落しているオブジェクトを scope 内からダウンロードする.

    転送中はバイト量を Kbyte / Mbyte / Gbyte の N/N で表示する.
    """
    try:
        results = _run_byte_transfer(
            title="pull",
            dry_run=dry_run,
            plan=plan_pull,
            execute=run_pull,
        )
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        raise click.ClickException(str(exc)) from exc
    _finish(results)


def _run_sync(*, dry_run: bool, prune_remote: bool) -> list[SyncResult]:
    repo = require_initialized()
    steps = plan_sync(repo)
    total_bytes = sum(job.size for job in collect_sync_jobs(steps))
    if dry_run or total_bytes == 0:
        return run_sync(repo, dry_run=dry_run, prune_remote=prune_remote, steps=steps)
    with ByteTransferBar(total_bytes, "sync") as bar:
        return run_sync(repo, prune_remote=prune_remote, steps=steps, progress=bar)


@click.command("sync")
@click.option("--dry-run", is_flag=True, help="実行せずに予定だけ表示する")
@click.option(
    "--prune-remote",
    is_flag=True,
    help="git fetch --all --prune のあと、参照されないリモートオブジェクトを削除する",
)
def sync_cmd(*, dry_run: bool, prune_remote: bool) -> None:
    """Scope 内だけリモートと同期する.

    転送中はバイト量を Kbyte / Mbyte / Gbyte の N/N で表示する.
    """
    try:
        results = _run_sync(dry_run=dry_run, prune_remote=prune_remote)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        raise click.ClickException(str(exc)) from exc
    _finish(results)
