"""CLI entrypoint for dit."""

from __future__ import annotations

import click

from dit.command.add import add_cmd
from dit.command.hook import hook_group
from dit.command.init import init_cmd
from dit.command.scope import scope_group
from dit.command.status import status_cmd
from dit.command.transfer import pull_cmd, push_cmd, sync_cmd


@click.group()
def cli() -> None:
    """MD-oriented large-file versioning."""


def main() -> None:
    """Register commands and invoke the Click group."""
    cli.add_command(init_cmd)
    cli.add_command(add_cmd)
    cli.add_command(status_cmd)
    cli.add_command(push_cmd)
    cli.add_command(pull_cmd)
    cli.add_command(sync_cmd)
    cli.add_command(scope_group)
    cli.add_command(hook_group)
    cli()


if __name__ == "__main__":
    main()
