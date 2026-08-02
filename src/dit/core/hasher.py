"""Content hashing helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

import blake3

from dit.core.errors import DitError

if TYPE_CHECKING:
    from pathlib import Path

HASH_PREFIX = "blake3:"
HASH_CHUNK_SIZE = 1024 * 1024


def hash_file(path: Path) -> str:
    """Return blake3 content hash for a file."""
    hasher = blake3.blake3()
    try:
        with path.open("rb") as f:
            while True:
                chunk = f.read(HASH_CHUNK_SIZE)
                if not chunk:
                    break
                hasher.update(chunk)
    except OSError as exc:
        msg = f"failed to hash {path}: {exc}"
        raise DitError(msg) from exc
    return HASH_PREFIX + hasher.hexdigest()


def strip_hash_prefix(value: str) -> str:
    """Strip the blake3: prefix when present."""
    if value.startswith(HASH_PREFIX):
        return value[len(HASH_PREFIX) :]
    return value
