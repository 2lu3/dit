"""Load and save dit.toml configuration."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import tomli_w

from dit.core.errors import ConfigError

if TYPE_CHECKING:
    from pathlib import Path

    from dit.core.repo import Repo

DEFAULT_TRACK_PATTERNS: list[str] = [
    "*.dcd",
    "*.dvl",
    "*.rst",
    "*.npy",
    "*.pkl",
    "*.tar",
]

S3_REQUEST_TIMEOUT_SEC = 60


@dataclass(frozen=True)
class RemoteConfig:
    """Parsed remote storage URL and optional endpoint."""

    url: str
    endpoint_url: str | None = None

    @property
    def bucket(self) -> str:
        """Return the S3 bucket name from the remote URL."""
        parsed = urlparse(self.url)
        if parsed.scheme != "s3":
            msg = f"unsupported remote scheme: {parsed.scheme!r} in {self.url}"
            raise ConfigError(msg)
        if not parsed.netloc:
            msg = f"missing bucket in remote url: {self.url}"
            raise ConfigError(msg)
        return parsed.netloc

    @property
    def prefix(self) -> str:
        """Return the key prefix from the remote URL path."""
        parsed = urlparse(self.url)
        return parsed.path.lstrip("/")


@dataclass(frozen=True)
class DitConfig:
    """In-memory representation of dit.toml."""

    remote: RemoteConfig | None = None
    track_patterns: list[str] = field(default_factory=lambda: list(DEFAULT_TRACK_PATTERNS))

    @classmethod
    def load(cls, path: Path) -> DitConfig:
        """Load configuration from a TOML file path."""
        try:
            with path.open("rb") as f:
                data = tomllib.load(f)
        except FileNotFoundError as exc:
            msg = f"config not found: {path}"
            raise ConfigError(msg) from exc
        except tomllib.TOMLDecodeError as exc:
            msg = f"invalid TOML in {path}: {exc}"
            raise ConfigError(msg) from exc
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DitConfig:
        """Build configuration from a parsed TOML dictionary."""
        remote_data = data.get("remote") or {}
        remote: RemoteConfig | None = None
        if remote_data.get("url"):
            remote = RemoteConfig(
                url=str(remote_data["url"]),
                endpoint_url=remote_data.get("endpoint_url"),
            )
        track = data.get("track") or {}
        patterns = track.get("patterns") or list(DEFAULT_TRACK_PATTERNS)
        if not isinstance(patterns, list):
            msg = "[track].patterns must be a list of strings"
            raise ConfigError(msg)
        return cls(remote=remote, track_patterns=[str(p) for p in patterns])

    def to_dict(self) -> dict[str, Any]:
        """Serialize configuration to a TOML-ready dictionary."""
        result: dict[str, Any] = {"track": {"patterns": list(self.track_patterns)}}
        if self.remote is not None:
            remote: dict[str, str] = {"url": self.remote.url}
            if self.remote.endpoint_url:
                remote["endpoint_url"] = self.remote.endpoint_url
            result["remote"] = remote
        return result

    def save(self, path: Path) -> None:
        """Write configuration to a TOML file path."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as f:
            tomli_w.dump(self.to_dict(), f)


def load_config(repo: Repo) -> DitConfig:
    """Load dit.toml for the given repository."""
    return DitConfig.load(repo.dit_toml)


def default_init_config(
    remote_url: str | None = None,
    endpoint_url: str | None = None,
) -> DitConfig:
    """Build a default configuration for `dit init`."""
    remote = None
    if remote_url:
        remote = RemoteConfig(url=remote_url, endpoint_url=endpoint_url)
    return DitConfig(remote=remote, track_patterns=list(DEFAULT_TRACK_PATTERNS))
