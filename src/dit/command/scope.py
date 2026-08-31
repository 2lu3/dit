"""dit scope コマンド."""

from __future__ import annotations

from pathlib import Path

import click

from dit.core.repo import require_initialized
from dit.core.scope import Scope


@click.group("scope")
def scope_group() -> None:
    """同期対象ディレクトリ（scope）を管理する."""


@scope_group.command("add")
@click.argument("directory", type=click.Path(exists=True, file_okay=False, path_type=Path))
def scope_add(directory: Path) -> None:
    """ディレクトリを scope に追加する."""
    try:
        repo = require_initialized()
        rel = Scope(repo).add(directory.resolve())
    except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"added {rel}")


@scope_group.command("remove")
@click.argument("directory")
def scope_remove(directory: str) -> None:
    """ディレクトリを scope から削除する."""
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
    """現在の scope ディレクトリを一覧表示する."""
    try:
        repo = require_initialized()
        for directory in Scope(repo).list():
            click.echo(directory)
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc
