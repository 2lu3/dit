"""Pointer file read and write helpers."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

import tomli_w

from dit.core.errors import PointerError
from dit.core.repo import POINTER_SUFFIX


@dataclass(frozen=True)
class Pointer:
    """Metadata pointer for a tracked data file."""

    path: str
    hash: str
    size: int

    @property
    def pointer_relpath(self) -> str:
        """Return the relative pointer path for this entry."""
        return self.path + POINTER_SUFFIX

    def to_dict(self) -> dict[str, str | int]:
        """Return a TOML-serializable dict of pointer fields."""
        return {"path": self.path, "hash": self.hash, "size": self.size}


def pointer_path_for(data_path: Path) -> Path:
    """Return the pointer path next to a data file."""
    return Path(str(data_path) + POINTER_SUFFIX)


def data_path_for_pointer(pointer_path: Path) -> Path:
    """Return the data file path for a pointer path."""
    text = str(pointer_path)
    if not text.endswith(POINTER_SUFFIX):
        msg = f"not a pointer path: {pointer_path}"
        raise PointerError(msg)
    return Path(text[: -len(POINTER_SUFFIX)])


def read_pointer(path: Path) -> Pointer:
    """Load a Pointer from a TOML pointer file."""
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError as exc:
        msg = f"pointer not found: {path}"
        raise PointerError(msg) from exc
    except tomllib.TOMLDecodeError as exc:
        msg = f"invalid pointer TOML {path}: {exc}"
        raise PointerError(msg) from exc
    try:
        return Pointer(path=str(data["path"]), hash=str(data["hash"]), size=int(data["size"]))
    except (KeyError, TypeError, ValueError) as exc:
        msg = f"invalid pointer fields in {path}: {exc}"
        raise PointerError(msg) from exc


def write_pointer(repo_root: Path, pointer: Pointer) -> Path:
    """Write a pointer file under the repository root."""
    out = repo_root / pointer.pointer_relpath
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("wb") as f:
        tomli_w.dump(pointer.to_dict(), f)
    return out


def ensure_gitignore_entry(data_file: Path, rel_name: str) -> None:
    """Ensure a data file name is listed in the nearest .gitignore."""
    gitignore = data_file.parent / ".gitignore"
    line = rel_name
    if gitignore.is_file():
        existing = gitignore.read_text(encoding="utf-8").splitlines()
        if line in existing or f"/{line}" in existing:
            return
        with gitignore.open("a", encoding="utf-8") as f:
            f.write(f"\n{line}\n")
        return
    gitignore.write_text(f"{line}\n", encoding="utf-8")
