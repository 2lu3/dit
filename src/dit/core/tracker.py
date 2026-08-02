"""Resolve tracked and pointer files from dit.toml patterns."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import pathspec

from dit.core.repo import POINTER_SUFFIX

if TYPE_CHECKING:
    from dit.core.config import DitConfig
    from dit.core.repo import Repo

SKIP_DIR_NAMES = {".git", ".dit", "__pycache__", ".venv", "venv"}


def build_track_spec(patterns: list[str]) -> pathspec.PathSpec:
    """Build a gitwildmatch PathSpec from track patterns."""
    return pathspec.PathSpec.from_lines("gitwildmatch", patterns)


def load_gitignore_spec(repo: Repo) -> pathspec.PathSpec:
    """Load .gitignore patterns as a PathSpec."""
    patterns: list[str] = []
    gitignore = repo.root / ".gitignore"
    if gitignore.is_file():
        patterns.extend(gitignore.read_text(encoding="utf-8").splitlines())
    return pathspec.PathSpec.from_lines("gitwildmatch", patterns)


def is_tracked_path(rel_posix: str, *, is_dir: bool, track_spec: pathspec.PathSpec) -> bool:
    """Return whether a relative path matches the track spec."""
    candidate = rel_posix + ("/" if is_dir and not rel_posix.endswith("/") else "")
    return track_spec.match_file(candidate)


def iter_tracked_files(repo: Repo, config: DitConfig) -> list[Path]:
    """List tracked data files under the repo root."""
    track_spec = build_track_spec(config.track_patterns)
    ignore_spec = load_gitignore_spec(repo)
    results: list[Path] = []
    for path in _walk(repo.root):
        rel = path.relative_to(repo.root).as_posix()
        if rel.endswith(POINTER_SUFFIX):
            continue
        # still allow tracked large files that are gitignored
        if ignore_spec.match_file(rel) and not is_tracked_path(
            rel, is_dir=False, track_spec=track_spec
        ):
            continue
        if is_tracked_path(rel, is_dir=False, track_spec=track_spec):
            results.append(path)
    return sorted(results)


def iter_pointer_files(repo: Repo) -> list[Path]:
    """List pointer files under the repo root."""
    return sorted(
        path for path in _walk(repo.root) if path.name.endswith(POINTER_SUFFIX) and path.is_file()
    )


def _walk(root: Path) -> list[Path]:
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIR_NAMES]
        found.extend(Path(dirpath) / name for name in filenames)
    return found
