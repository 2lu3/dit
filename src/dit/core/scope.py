""".dit/scope.toml に永続化されるディレクトリ scope."""

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
    """dit が管理するディレクトリ集合."""

    def __init__(self, repo: Repo) -> None:
        """リポジトリの scope 状態を読み込む."""
        self.repo = repo
        self._directories: set[str] = set()
        self._load()

    @property
    def directories(self) -> set[str]:
        """Scope 内ディレクトリパスのコピーを返す."""
        return set(self._directories)

    def add(self, dir_path: Path) -> str:
        """ディレクトリを scope に追加して永続化する."""
        if not dir_path.is_dir():
            msg = f"{dir_path} is not a directory"
            raise ConfigError(msg)
        rel = self.repo.rel(dir_path)
        self._directories.add(rel)
        self._save()
        return rel

    def remove(self, dir_path: Path | str) -> str:
        """ディレクトリを scope から削除して永続化する."""
        rel = dir_path if isinstance(dir_path, str) else self.repo.rel(Path(dir_path))
        if rel not in self._directories:
            msg = f"{rel} is not in scope: {natsorted(self._directories)}"
            raise ConfigError(msg)
        self._directories.remove(rel)
        self._save()
        return rel

    def list(self) -> list[str]:
        """自然順ソートした scope ディレクトリを返す."""
        return natsorted(self._directories)

    def contains(self, rel_path: str) -> bool:
        """相対パスが scope 内かを返す."""
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
