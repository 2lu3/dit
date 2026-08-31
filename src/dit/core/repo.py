"""リポジトリ構成の探索とパス補助."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dit.core.errors import RepoError

DIT_DIR_NAME = ".dit"
DIT_TOML_NAME = "dit.toml"
POINTER_SUFFIX = ".dit"
INDEX_DB_NAME = "index.db"
SCOPE_TOML_NAME = "scope.toml"


@dataclass(frozen=True)
class Repo:
    """dit 対応 git リポジトリのパス群."""

    root: Path

    @property
    def dit_dir(self) -> Path:
        """.dit ディレクトリのパスを返す."""
        return self.root / DIT_DIR_NAME

    @property
    def dit_toml(self) -> Path:
        """dit.toml のパスを返す."""
        return self.root / DIT_TOML_NAME

    @property
    def index_db(self) -> Path:
        """SQLite インデックス DB のパスを返す."""
        return self.dit_dir / INDEX_DB_NAME

    @property
    def scope_toml(self) -> Path:
        """scope.toml のパスを返す."""
        return self.dit_dir / SCOPE_TOML_NAME

    def rel(self, path: Path) -> str:
        """リポジトリルートからの相対パスを返す."""
        return path.resolve().relative_to(self.root.resolve()).as_posix()

    def abs(self, rel_path: str) -> Path:
        """リポジトリ相対パスを絶対パスへ解決する."""
        return (self.root / rel_path).resolve()


def find_repo(start: Path | None = None) -> Repo:
    """開始パスから包含する git リポジトリを探す."""
    origin = (start or Path.cwd()).resolve()
    current = origin
    while True:
        if (current / ".git").exists() and (current / DIT_TOML_NAME).is_file():
            return Repo(root=current)
        if (current / ".git").exists():
            # git repo without dit.toml yet (e.g. during init)
            return Repo(root=current)
        if current.parent == current:
            msg = f"git repository not found from {origin}"
            raise RepoError(msg)
        current = current.parent


def require_initialized(start: Path | None = None) -> Repo:
    """リポジトリを探し、dit 初期化済みであることを要求する."""
    repo = find_repo(start)
    if not repo.dit_toml.is_file():
        msg = f"{DIT_TOML_NAME} not found in {repo.root}. Run `dit init` first."
        raise RepoError(msg)
    if not repo.dit_dir.is_dir():
        msg = f"{DIT_DIR_NAME}/ not found in {repo.root}. Run `dit init` first."
        raise RepoError(msg)
    return repo
