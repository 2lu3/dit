"""追跡ファイルを dit ポインタとしてステージする."""

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
from dit.core.scope import Scope
from dit.core.tracker import iter_pointer_files, iter_tracked_files

if TYPE_CHECKING:
    from dit.core.repo import Repo


def run_add(repo: Repo, *, quiet: bool = False, prune: bool = False) -> int:
    """Scope 内の追跡パスについてポインタを作成または更新する."""
    config = load_config(repo)
    scope = Scope(repo)
    changed = 0
    with StatIndex(repo.index_db) as index, index.transaction():
        # ポインタの確認・更新をリンク先の実体にそろえる。
        tracked = sorted(
            {p.resolve() for p in iter_tracked_files(repo, config) if scope.contains(repo.rel(p))}
        )
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
                changed += 1
                if not quiet:
                    logger.info(f"add {pointer.path}")
            # 中断時にポインタの書き込みだけが済んだ場合も再実行でステージする。
            _git_add(repo, pointer_path)
        if prune:
            changed += _prune_orphaned_pointers(repo, scope, tracked_rels, quiet=quiet)
    return changed


def _prune_orphaned_pointers(
    repo: Repo,
    scope: Scope,
    tracked_rels: set[str],
    *,
    quiet: bool,
) -> int:
    removed = 0
    _stage_deleted_pointers(repo, scope, tracked_rels)
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
        _git_add(repo, pointer_path)
        removed += 1
        if not quiet:
            logger.info(f"prune {pointer.path}")
    return removed


def _stage_deleted_pointers(repo: Repo, scope: Scope, tracked_rels: set[str]) -> None:
    # 削除後、Git へのステージ前に中断したポインタも再実行で処理する。
    git = shutil.which("git")
    if git is not None:
        result = subprocess.run(  # noqa: S603
            [git, "ls-files", "--deleted", "-z", "--", "*.dit"],
            cwd=repo.root,
            check=False,
            capture_output=True,
            timeout=60,
        )
        if result.returncode == 0:
            for raw_path in result.stdout.split(b"\0"):
                if not raw_path:
                    continue
                path = Path(raw_path.decode("utf-8", errors="surrogateescape"))
                data_rel = str(path)[:-4]
                if scope.contains(data_rel) and data_rel not in tracked_rels:
                    _git_add(repo, repo.root / path)


def _git_add(repo: Repo, path: Path) -> None:
    git = shutil.which("git")
    if git is None:
        msg = "git executable not found"
        raise RepoError(msg)
    try:
        if not path.exists():
            tracked = subprocess.run(  # noqa: S603
                [git, "ls-files", "--error-unmatch", "--", str(path)],
                cwd=repo.root,
                check=False,
                capture_output=True,
                timeout=60,
            )
            if tracked.returncode == 1:
                return
            tracked.check_returncode()
        # git path from shutil.which; args are fixed literals plus a Path
        subprocess.run(  # noqa: S603
            [git, "add", "--", str(path)],
            cwd=repo.root,
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired, subprocess.CalledProcessError) as exc:
        msg = f"git add failed for {path}: {exc}"
        raise RepoError(msg) from exc
