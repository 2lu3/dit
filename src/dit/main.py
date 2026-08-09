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
    """MD 計算向けの大容量ファイル版管理.

    用語:

    \b
      ポインタ (*.dit)  Git に載るメタデータ（hash / size）
      実体              大容量ファイル本体（Git には入れない）
      scope             このマシンで実体を置くディレクトリ

    ポインタ・実体・scope と sync の動き:

    \b
      ポインタ+実体 / scope 内   一致確認。必要なら push / pull
      ポインタ+実体 / scope 外   一致確認のあと、リモートにあれば実体を削除
      ポインタのみ / scope 内    リモートから pull
      ポインタのみ / scope 外    そのまま（ローカルに実体なし）
      実体のみ                   警告（ポインタ未作成）
    """  # noqa: D301


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
