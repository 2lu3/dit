"""dit add command."""

from __future__ import annotations

import click

from dit.core.add_service import run_add
from dit.core.repo import require_initialized


@click.command("add")
@click.option("--quiet", "-q", is_flag=True)
@click.option("--prune", is_flag=True, help="remove pointers no longer matched by dit.toml")
def add_cmd(*, quiet: bool, prune: bool) -> None:
    """Create or update pointer files for tracked paths."""
    try:
        repo = require_initialized()
        count = run_add(repo, quiet=quiet, prune=prune)
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc
    if not quiet:
        click.echo(f"{count} pointer(s) updated")
