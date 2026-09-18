"""dit hook コマンド."""

from __future__ import annotations

import click

from dit.core.precommit import hook_status, install_hook, uninstall_hook
from dit.core.repo import find_repo


@click.group("hook")
def hook_group() -> None:
    """pre-commit 設定内の dit hook を管理する."""


@hook_group.command("install")
def hook_install() -> None:
    """pre-commit 設定に dit hook を追加する."""
    repo = find_repo()
    click.echo(f"updated {install_hook(repo.root)}")


@hook_group.command("uninstall")
def hook_uninstall() -> None:
    """pre-commit 設定から dit hook を削除する."""
    repo = find_repo()
    removed = uninstall_hook(repo.root)
    click.echo("removed" if removed else "nothing to remove")


@hook_group.command("status")
def hook_status_cmd() -> None:
    """pre-commit 設定内の dit hook の状態を表示する."""
    repo = find_repo()
    click.echo(hook_status(repo.root))
