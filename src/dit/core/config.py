"""Load and save dit.toml configuration."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

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
    """Remote storage bucket and key prefix."""

    bucket: str
    prefix: str

    def __post_init__(self) -> None:
        """Reject an empty bucket name."""
        if not self.bucket:
            msg = "remote bucket must not be empty"
            raise ConfigError(msg)


@dataclass(frozen=True)
class DitConfig:
    """In-memory representation of dit.toml."""

    remote: RemoteConfig | None = None
    track_patterns: list[str] = field(
        default_factory=lambda: list(DEFAULT_TRACK_PATTERNS)
    )

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
        remote_data = data.get("remote")
        remote: RemoteConfig | None = None
        if remote_data is not None:
            if not isinstance(remote_data, dict):
                msg = "[remote] must be a table"
                raise ConfigError(msg)
            if "bucket" not in remote_data:
                msg = "[remote].bucket is required"
                raise ConfigError(msg)
            if "prefix" not in remote_data:
                msg = "[remote].prefix is required"
                raise ConfigError(msg)
            remote = RemoteConfig(
                bucket=str(remote_data["bucket"]),
                prefix=str(remote_data["prefix"]),
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
            result["remote"] = {
                "bucket": self.remote.bucket,
                "prefix": self.remote.prefix,
            }
        return result

    def save(self, path: Path) -> None:
        """Write configuration to a TOML file path."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as f:
            tomli_w.dump(self.to_dict(), f)


def load_config(repo: Repo) -> DitConfig:
    """Load dit.toml for the given repository."""
    return DitConfig.load(repo.dit_toml)


def init_config(bucket: str, prefix: str) -> DitConfig:
    """Build configuration for `dit init`."""
    return DitConfig(
        remote=RemoteConfig(bucket=bucket, prefix=prefix),
        track_patterns=list(DEFAULT_TRACK_PATTERNS),
    )
