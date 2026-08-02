"""dit push, pull, and sync commands."""

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
@click.option("--dry-run", is_flag=True)
def push_cmd(*, dry_run: bool) -> None:
    """Upload local objects referenced by in-scope pointers."""
    try:
        repo = require_initialized()
        results = run_push(repo, dry_run=dry_run)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        raise click.ClickException(str(exc)) from exc
    errors = _print_results(results)
    if errors:
        raise SystemExit(1)


@click.command("pull")
@click.option("--dry-run", is_flag=True)
def pull_cmd(*, dry_run: bool) -> None:
    """Download remote objects for in-scope pointers."""
    try:
        repo = require_initialized()
        results = run_pull(repo, dry_run=dry_run)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        raise click.ClickException(str(exc)) from exc
    errors = _print_results(results)
    if errors:
        raise SystemExit(1)


@click.command("sync")
@click.option("--dry-run", is_flag=True)
@click.option(
    "--prune-remote",
    is_flag=True,
    help="after git fetch --all --prune, delete unreferenced remote objects",
)
def sync_cmd(*, dry_run: bool, prune_remote: bool) -> None:
    """Push, pull, and apply scope deletes for in-scope pointers."""
    try:
        repo = require_initialized()
        results = run_sync(repo, dry_run=dry_run, prune_remote=prune_remote)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        raise click.ClickException(str(exc)) from exc
    errors = _print_results(results)
    if errors:
        raise SystemExit(1)
