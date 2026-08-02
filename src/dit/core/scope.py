"""Directory scope persisted under .dit/scope.toml."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import TYPE_CHECKING

import tomli_w
from natsort import natsorted

from dit.core.errors import ConfigError

if TYPE_CHECKING:
    from dit.core.repo import Repo


class Scope:
    """Managed set of directories tracked by dit."""

    def __init__(self, repo: Repo) -> None:
        """Load scope state for a repository."""
        self.repo = repo
        self._directories: set[str] = set()
        self._load()

    @property
    def directories(self) -> set[str]:
        """Return a copy of scoped directory paths."""
        return set(self._directories)

    def add(self, dir_path: Path) -> str:
        """Add a directory to scope and persist."""
        if not dir_path.is_dir():
            msg = f"{dir_path} is not a directory"
            raise ConfigError(msg)
        rel = self.repo.rel(dir_path)
        self._directories.add(rel)
        self._save()
        return rel

    def remove(self, dir_path: Path | str) -> str:
        """Remove a directory from scope and persist."""
        rel = dir_path if isinstance(dir_path, str) else self.repo.rel(Path(dir_path))
        if rel not in self._directories:
            msg = f"{rel} is not in scope: {natsorted(self._directories)}"
            raise ConfigError(msg)
        self._directories.remove(rel)
        self._save()
        return rel

    def list(self) -> list[str]:
        """Return scoped directories in natural sort order."""
        return natsorted(self._directories)

    def contains(self, rel_path: str) -> bool:
        """Return whether a relative path falls under scope."""
        if not self._directories:
            return False
        for directory in self._directories:
            if rel_path == directory or rel_path.startswith(directory.rstrip("/") + "/"):
                return True
        return False

    def _load(self) -> None:
        path = self.repo.scope_toml
        if not path.is_file():
            self._directories = set()
            return
        with path.open("rb") as f:
            data = tomllib.load(f)
        directories = data.get("directories") or []
        if not isinstance(directories, list):
            msg = f"invalid scope file: {path}"
            raise TypeError(msg)
        self._directories = {str(d) for d in directories}

    def _save(self) -> None:
        self.repo.dit_dir.mkdir(parents=True, exist_ok=True)
        with self.repo.scope_toml.open("wb") as f:
            tomli_w.dump({"directories": natsorted(self._directories)}, f)
