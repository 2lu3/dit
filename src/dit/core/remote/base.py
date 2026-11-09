"""リモートストレージの抽象インタフェース."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


class Remote(ABC):
    """コンテンツアドレス方式のリモートオブジェクトストレージのバックエンド."""

    @abstractmethod
    def exists(self, content_hash: str) -> bool:
        """指定ハッシュのオブジェクトがリモートに存在するかを返す."""

    @abstractmethod
    def exists_many(
        self,
        content_hashes: list[str],
        *,
        on_checked: Callable[[str], None] | None = None,
    ) -> dict[str, bool]:
        """ハッシュごとの存在を確認し、確認済みハッシュを通知する."""

    @abstractmethod
    def upload(
        self,
        local_path: Path,
        content_hash: str,
        *,
        progress: Callable[[int], None] | None = None,
    ) -> None:
        """指定コンテンツハッシュでローカルファイルをアップロードする."""

    @abstractmethod
    def download(
        self,
        content_hash: str,
        local_path: Path,
        *,
        progress: Callable[[int], None] | None = None,
    ) -> None:
        """リモートオブジェクトをローカルパスへダウンロードする."""

    @abstractmethod
    def download_many(
        self,
        downloads: list[tuple[str, Path]],
        *,
        progress: Callable[[int], None] | None = None,
        on_start: Callable[[Path], None] | None = None,
    ) -> None:
        """ハッシュと保存先の組を取得し、全件の完了を待つ."""

    @abstractmethod
    def delete(self, content_hash: str) -> None:
        """コンテンツハッシュでリモートオブジェクトを削除する."""

    @abstractmethod
    def list_hashes(self) -> list[str]:
        """リモートに保存されているコンテンツハッシュを一覧する."""
