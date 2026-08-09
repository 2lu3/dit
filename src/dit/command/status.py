"""dit status command."""

from __future__ import annotations

import click

from dit.core.config import load_config
from dit.core.content import resolve_content_hash
from dit.core.index import StatIndex
from dit.core.pointer import read_pointer
from dit.core.repo import require_initialized
from dit.core.scope import Scope
from dit.core.tracker import iter_pointer_files, iter_tracked_files


@click.command("status")
def status_cmd() -> None:
    """ポインタと scope に対する追跡ファイルの状態を表示する.

    状態記号:

    \b
      ?  実体はあるがポインタがない（未登録、scope 内）
      ↓  実体がなく、scope 内（要 pull）
      .  実体がなく、scope 外
      M  実体のハッシュがポインタと不一致（変更あり、scope 内）
      S  実体はあるが scope 外（触らない）
         問題なし（ポインタと一致し、scope 内）
    """  # noqa: D301
    try:
        repo = require_initialized()
        config = load_config(repo)
    except (FileNotFoundError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    scope = Scope(repo)
    with StatIndex(repo.index_db) as index:
        tracked = {repo.rel(p): p for p in iter_tracked_files(repo, config)}
        pointers = {}
        for pointer_path in iter_pointer_files(repo):
            pointer = read_pointer(pointer_path)
            pointers[pointer.path] = pointer

        for rel in sorted(set(tracked) | set(pointers)):
            data_path = tracked.get(rel)
            pointer = pointers.get(rel)
            has_data = data_path is not None and data_path.is_file()
            if not scope.contains(rel):
                _echo_out_of_scope(rel, has_pointer=pointer is not None, has_data=has_data)
                continue
            if pointer is None and data_path is not None:
                click.echo(f"? {rel}")
                continue
            if pointer is not None and not has_data:
                click.echo(f"↓ {rel}")
                continue
            if pointer is None or data_path is None:
                continue
            digest = resolve_content_hash(repo, index, data_path)
            if digest != pointer.hash:
                click.echo(f"M {rel}")
            else:
                click.echo(f"  {rel}")


def _echo_out_of_scope(rel: str, *, has_pointer: bool, has_data: bool) -> None:
    if has_pointer and has_data:
        click.echo(f"S {rel}")
    elif has_pointer:
        click.echo(f". {rel}")
