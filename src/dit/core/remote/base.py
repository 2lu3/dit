"""Abstract remote storage interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


class Remote(ABC):
    """Backend for content-addressed remote object storage."""

    @abstractmethod
    def exists(self, content_hash: str) -> bool:
        """Return whether an object with the given hash exists remotely."""

    @abstractmethod
    def upload(self, local_path: Path, content_hash: str) -> None:
        """Upload a local file under the given content hash."""

    @abstractmethod
    def download(self, content_hash: str, local_path: Path) -> None:
        """Download a remote object to a local path."""

    @abstractmethod
    def delete(self, content_hash: str) -> None:
        """Delete a remote object by content hash."""

    @abstractmethod
    def list_hashes(self) -> list[str]:
        """List content hashes stored on the remote."""
