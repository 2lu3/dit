"""dit scope commands."""

from __future__ import annotations

from pathlib import Path

import click

from dit.core.repo import require_initialized
from dit.core.scope import Scope


@click.group("scope")
def scope_group() -> None:
    """Manage directories included in sync scope."""


@scope_group.command("add")
@click.argument("directory", type=click.Path(exists=True, file_okay=False, path_type=Path))
def scope_add(directory: Path) -> None:
    """Add a directory to sync scope."""
    try:
        repo = require_initialized()
        rel = Scope(repo).add(directory.resolve())
    except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"added {rel}")


@scope_group.command("remove")
@click.argument("directory")
def scope_remove(directory: str) -> None:
    """Remove a directory from sync scope."""
    try:
        repo = require_initialized()
        scope = Scope(repo)
        path = Path(directory)
        rel = scope.remove(path if path.exists() else directory)
    except (FileNotFoundError, KeyError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"removed {rel}")


@scope_group.command("list")
def scope_list() -> None:
    """List directories currently in sync scope."""
    try:
        repo = require_initialized()
        for directory in Scope(repo).list():
            click.echo(directory)
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc
