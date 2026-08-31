"""dit 向けドメイン固有例外."""

from __future__ import annotations


class DitError(Exception):
    """dit 操作の基底エラー."""


class ConfigError(DitError):
    """無効または欠落した dit 設定."""


class RepoError(DitError):
    """リポジトリ構成の解決または探索の失敗."""


class HookError(DitError):
    """Git フックのインストールまたはアンインストールの失敗."""


class RemoteError(DitError):
    """リモートストレージ操作の失敗."""


class PointerError(DitError):
    """ポインタファイルの読み書き失敗."""


class TrackError(DitError):
    """追跡パターンまたはパス解決の失敗."""
