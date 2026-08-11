"""dit hook コマンド."""

from __future__ import annotations

import click

from dit.core.githook import hook_status, install_hook, uninstall_hook
from dit.core.repo import find_repo


@click.group("hook")
def hook_group() -> None:
    """pre-commit フックを管理する."""


@hook_group.command("install")
@click.option("--force", is_flag=True, help="管理外のフックを上書きする")
def hook_install(*, force: bool) -> None:
    """pre-commit フックをインストールする."""
    repo = find_repo()
    try:
        path = install_hook(repo.root, force=force)
    except FileExistsError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"installed {path}")


@hook_group.command("uninstall")
def hook_uninstall() -> None:
    """pre-commit フックをアンインストールする."""
    repo = find_repo()
    try:
        removed = uninstall_hook(repo.root)
    except RuntimeError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo("removed" if removed else "nothing to remove")


@hook_group.command("status")
def hook_status_cmd() -> None:
    """pre-commit フックの状態を表示する."""
    repo = find_repo()
    click.echo(hook_status(repo.root))
