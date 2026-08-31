"""リモートストレージの抽象インタフェース."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


class Remote(ABC):
    """コンテンツアドレス方式のリモートオブジェクトストレージのバックエンド."""

    @abstractmethod
    def exists(self, content_hash: str) -> bool:
        """指定ハッシュのオブジェクトがリモートに存在するかを返す."""

    @abstractmethod
    def upload(self, local_path: Path, content_hash: str) -> None:
        """指定コンテンツハッシュでローカルファイルをアップロードする."""

    @abstractmethod
    def download(self, content_hash: str, local_path: Path) -> None:
        """リモートオブジェクトをローカルパスへダウンロードする."""

    @abstractmethod
    def delete(self, content_hash: str) -> None:
        """コンテンツハッシュでリモートオブジェクトを削除する."""

    @abstractmethod
    def list_hashes(self) -> list[str]:
        """リモートに保存されているコンテンツハッシュを一覧する."""
