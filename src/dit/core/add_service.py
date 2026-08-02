"""Stage tracked files as dit pointer files."""

from __future__ import annotations

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
from dit.core.tracker import iter_pointer_files, iter_tracked_files

if TYPE_CHECKING:
    from dit.core.repo import Repo


def run_add(repo: Repo, *, quiet: bool = False, prune: bool = False) -> int:
    """Write or update pointer files for tracked paths."""
    config = load_config(repo)
    changed = 0
    with StatIndex(repo.index_db) as index:
        tracked = iter_tracked_files(repo, config)
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
                _git_add(repo, repo.root / pointer.pointer_relpath)
                changed += 1
                if not quiet:
                    logger.info(f"add {pointer.path}")
        if prune:
            changed += _prune_orphaned_pointers(repo, tracked_rels, quiet=quiet)
    return changed


def _prune_orphaned_pointers(repo: Repo, tracked_rels: set[str], *, quiet: bool) -> int:
    removed = 0
    for pointer_path in iter_pointer_files(repo):
        try:
            pointer = read_pointer(pointer_path)
        except ValueError:
            continue
        if pointer.path in tracked_rels:
            continue
        pointer_path.unlink(missing_ok=True)
        _git_add(repo, pointer_path)
        removed += 1
        if not quiet:
            logger.info(f"prune {pointer.path}")
    return removed


def _git_add(repo: Repo, path: Path) -> None:
    git = shutil.which("git")
    if git is None:
        msg = "git executable not found"
        raise RepoError(msg)
    try:
        # git path from shutil.which; args are fixed literals plus a Path
        subprocess.run(  # noqa: S603
            [git, "add", "--", str(path)],
            cwd=repo.root,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        msg = f"git add failed for {path}: {exc}"
        raise RepoError(msg) from exc
