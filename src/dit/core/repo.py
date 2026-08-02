"""Repository layout discovery and path helpers."""

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
    """Paths for a dit-enabled git repository."""

    root: Path

    @property
    def dit_dir(self) -> Path:
        """Return the .dit directory path."""
        return self.root / DIT_DIR_NAME

    @property
    def dit_toml(self) -> Path:
        """Return the dit.toml path."""
        return self.root / DIT_TOML_NAME

    @property
    def index_db(self) -> Path:
        """Return the SQLite index database path."""
        return self.dit_dir / INDEX_DB_NAME

    @property
    def scope_toml(self) -> Path:
        """Return the scope.toml path."""
        return self.dit_dir / SCOPE_TOML_NAME

    def rel(self, path: Path) -> str:
        """Return a path relative to the repository root."""
        return path.resolve().relative_to(self.root.resolve()).as_posix()

    def abs(self, rel_path: str) -> Path:
        """Resolve a repository-relative path to an absolute path."""
        return (self.root / rel_path).resolve()


def find_repo(start: Path | None = None) -> Repo:
    """Find the enclosing git repository from a starting path."""
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
    """Find a repository and require dit initialization."""
    repo = find_repo(start)
    if not repo.dit_toml.is_file():
        msg = f"{DIT_TOML_NAME} not found in {repo.root}. Run `dit init` first."
        raise RepoError(msg)
    if not repo.dit_dir.is_dir():
        msg = f"{DIT_DIR_NAME}/ not found in {repo.root}. Run `dit init` first."
        raise RepoError(msg)
    return repo
