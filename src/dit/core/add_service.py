"""追跡ファイルを dit ポインタとしてステージする."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from dit.core.config import load_config
from dit.core.content import resolve_content_hash, write_pointer_for_file
from dit.core.errors import RepoError
from dit.core.index import StatIndex
from dit.core.pointer import read_pointer
from dit.core.scope import Scope
from dit.core.tracker import iter_pointer_files, iter_tracked_files

if TYPE_CHECKING:
    from dit.core.repo import Repo


def run_add(repo: Repo, *, quiet: bool = False, prune: bool = False) -> int:
    """追跡パスについてポインタを作成または更新する."""
    config = load_config(repo)
    scope = Scope(repo)
    changed: list[Path] = []
    with StatIndex(repo.index_db) as index:
        # ポインタの確認・更新をリンク先の実体にそろえる。
        tracked = sorted({p.resolve() for p in iter_tracked_files(repo, config)})
        tracked_rels = {repo.rel(p) for p in tracked}
        for data_path in tracked:
            digest = resolve_content_hash(repo, index, data_path)
            pointer_path = Path(str(data_path) + ".dit")
            needs_write = True
            if pointer_path.is_file():
                existing = read_pointer(pointer_path)
                if existing.hash == digest and existing.size == data_path.stat().st_size:
                    needs_write = False
            if needs_write:
                pointer = write_pointer_for_file(repo, index, data_path, digest)
                changed.append(repo.root / pointer.pointer_relpath)
                if not quiet:
                    logger.info(f"add {pointer.path}")
        if prune:
            changed.extend(_prune_orphaned_pointers(repo, scope, tracked_rels, quiet=quiet))
    if changed:
        _git_add(repo, changed)
    return len(changed)


def _prune_orphaned_pointers(
    repo: Repo,
    scope: Scope,
    tracked_rels: set[str],
    *,
    quiet: bool,
) -> list[Path]:
    removed: list[Path] = []
    for pointer_path in iter_pointer_files(repo):
        try:
            pointer = read_pointer(pointer_path)
        except ValueError:
            continue
        if not scope.contains(pointer.path):
            continue
        if pointer.path in tracked_rels:
            continue
        pointer_path.unlink(missing_ok=True)
        removed.append(pointer_path)
        if not quiet:
            logger.info(f"prune {pointer.path}")
    return removed


def _git_add(repo: Repo, paths: list[Path]) -> None:
    git = shutil.which("git")
    if git is None:
        msg = "git executable not found"
        raise RepoError(msg)
    try:
        result = subprocess.run(  # noqa: S603
            [git, "--literal-pathspecs", "add", "--pathspec-from-file=-", "--pathspec-file-nul"],
            cwd=repo.root,
            input=b"\0".join(os.fsencode(path.relative_to(repo.root)) for path in paths) + b"\0",
            check=False,
            capture_output=True,
        )
    except OSError as exc:
        msg = f"git add failed: {exc}"
        raise RepoError(msg) from exc
    if result.returncode:
        detail = os.fsdecode(result.stderr).strip()
        msg = f"git add failed (exit {result.returncode}): {detail}"
        raise RepoError(msg)
