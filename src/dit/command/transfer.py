"""dit push / pull / sync コマンド."""

from __future__ import annotations

import click

from dit.core.repo import require_initialized
from dit.core.sync_service import SyncAction, run_pull, run_push, run_sync


def _print_results(results: list) -> int:
    errors = 0
    for item in results:
        click.echo(f"{item.action.value:16} {item.path}  ({item.message})")
        if item.action == SyncAction.ERROR:
            errors += 1
    return errors


@click.command("push")
@click.option("--dry-run", is_flag=True, help="実行せずに予定だけ表示する")
def push_cmd(*, dry_run: bool) -> None:
    """Scope 内ポインタが指すローカルオブジェクトをアップロードする."""
    try:
        repo = require_initialized()
        results = run_push(repo, dry_run=dry_run)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        raise click.ClickException(str(exc)) from exc
    errors = _print_results(results)
    if errors:
        raise SystemExit(1)


@click.command("pull")
@click.option("--dry-run", is_flag=True, help="実行せずに予定だけ表示する")
def pull_cmd(*, dry_run: bool) -> None:
    """欠落しているオブジェクトを scope 内からダウンロードする."""
    try:
        repo = require_initialized()
        results = run_pull(repo, dry_run=dry_run)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        raise click.ClickException(str(exc)) from exc
    errors = _print_results(results)
    if errors:
        raise SystemExit(1)


@click.command("sync")
@click.option("--dry-run", is_flag=True, help="実行せずに予定だけ表示する")
@click.option(
    "--prune-remote",
    is_flag=True,
    help="git fetch --all --prune のあと、参照されないリモートオブジェクトを削除する",
)
def sync_cmd(*, dry_run: bool, prune_remote: bool) -> None:
    """Scope 内だけリモートと同期する."""
    try:
        repo = require_initialized()
        results = run_sync(repo, dry_run=dry_run, prune_remote=prune_remote)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        raise click.ClickException(str(exc)) from exc
    errors = _print_results(results)
    if errors:
        raise SystemExit(1)
