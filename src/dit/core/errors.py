"""Domain-specific exceptions for dit."""

from __future__ import annotations


class DitError(Exception):
    """Base error for dit operations."""


class ConfigError(DitError):
    """Invalid or missing dit configuration."""


class RepoError(DitError):
    """Repository layout or discovery failure."""


class HookError(DitError):
    """Git hook install or uninstall failure."""


class RemoteError(DitError):
    """Remote storage operation failure."""


class PointerError(DitError):
    """Pointer file read or write failure."""


class TrackError(DitError):
    """Track pattern or path resolution failure."""
