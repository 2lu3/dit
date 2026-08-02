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
    """Show tracked file status relative to pointers and scope."""
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
            if pointer is None and data_path is not None:
                click.echo(f"? {rel}")
                continue
            if pointer is not None and (data_path is None or not data_path.is_file()):
                mark = "↓" if scope.contains(rel) else "."
                click.echo(f"{mark} {rel}")
                continue
            if pointer is None or data_path is None:
                continue
            digest = resolve_content_hash(repo, index, data_path)
            if digest != pointer.hash:
                click.echo(f"M {rel}")
            elif pointer.path not in scope.directories and not scope.contains(rel):
                click.echo(f"S {rel}")  # present but out of scope
            else:
                click.echo(f"  {rel}")
