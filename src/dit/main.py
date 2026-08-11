"""CLI entrypoint for dit."""

from __future__ import annotations

import click

from dit.command.add import add_cmd
from dit.command.hook import hook_group
from dit.command.init import init_cmd
from dit.command.scope import scope_group
from dit.command.status import status_cmd
from dit.command.transfer import pull_cmd, push_cmd, sync_cmd


def _cli_callback() -> None:
    """MD 計算向けの大容量ファイル版管理.

    用語:

    \b
      ポインタ (*.dit)  Git に載るメタデータ（hash / size）
      実体              大容量ファイル本体（Git には入れない）
      scope             このマシンで実体を置くディレクトリ

    ポインタ・実体・scope と sync の動き:

    \b
      ポインタ+実体 / scope 内   一致確認。必要なら push / pull
      ポインタ+実体 / scope 外   無視（触らない）
      ポインタのみ / scope 内    リモートから pull
      ポインタのみ / scope 外    無視
      実体のみ / scope 内        警告（ポインタ未作成）
      実体のみ / scope 外        無視
    """  # noqa: D301


def create_cli() -> click.Group:
    """Create a fully registered CLI without invoking any command."""
    group = click.Group(name="dit", callback=_cli_callback, help=_cli_callback.__doc__)
    group.add_command(init_cmd)
    group.add_command(add_cmd)
    group.add_command(status_cmd)
    group.add_command(push_cmd)
    group.add_command(pull_cmd)
    group.add_command(sync_cmd)
    group.add_command(scope_group)
    group.add_command(hook_group)
    return group


cli = create_cli()


def main() -> None:
    """Register commands and invoke the Click group."""
    cli()


if __name__ == "__main__":
    main()
