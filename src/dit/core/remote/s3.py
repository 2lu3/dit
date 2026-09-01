"""S3 互換のリモートストレージバックエンド."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from dit.core.config import S3_REQUEST_TIMEOUT_SEC, RemoteConfig
from dit.core.errors import ConfigError, RemoteError
from dit.core.hasher import strip_hash_prefix
from dit.core.remote.base import Remote

if TYPE_CHECKING:
    from pathlib import Path

MULTIPART_THRESHOLD_BYTES = 64 * 1024 * 1024
MULTIPART_CHUNKSIZE_BYTES = 16 * 1024 * 1024
MAX_CONCURRENCY = 4
HASH_KEY_PART_COUNT = 2

REQUIRED_ENV_VARS = (
    "DIT_ACCESS_KEY",
    "DIT_SECRET_KEY",
    "DIT_ENDPOINT_URL",
)


def _require_env_vars() -> dict[str, str]:
    missing = [name for name in REQUIRED_ENV_VARS if not os.environ.get(name)]
    if missing:
        msg = "required environment variables not set: " + ", ".join(missing)
        raise ConfigError(msg)
    return {name: os.environ[name] for name in REQUIRED_ENV_VARS}


def _s3_client_kwargs() -> dict[str, Any]:
    """必須の DIT_* 環境変数から boto3 S3 クライアント用 kwargs を構築する."""
    env = _require_env_vars()
    return {
        "endpoint_url": env["DIT_ENDPOINT_URL"],
        "aws_access_key_id": env["DIT_ACCESS_KEY"],
        "aws_secret_access_key": env["DIT_SECRET_KEY"],
        "config": BotoConfig(
            connect_timeout=S3_REQUEST_TIMEOUT_SEC,
            read_timeout=S3_REQUEST_TIMEOUT_SEC,
            retries={"max_attempts": 3, "mode": "standard"},
        ),
    }


class S3Remote(Remote):
    """コンテンツアドレスキーでオブジェクトを保存する S3 リモート."""

    def __init__(self, remote: RemoteConfig) -> None:
        """指定のリモート設定で S3 クライアントを作成する."""
        self.remote = remote
        self._client = boto3.client("s3", **_s3_client_kwargs())
        self._transfer = boto3.s3.transfer.TransferConfig(
            multipart_threshold=MULTIPART_THRESHOLD_BYTES,
            multipart_chunksize=MULTIPART_CHUNKSIZE_BYTES,
            max_concurrency=MAX_CONCURRENCY,
        )

    def object_key(self, content_hash: str) -> str:
        """コンテンツハッシュから S3 オブジェクトキーを構築する."""
        digest = strip_hash_prefix(content_hash)
        prefix = self.remote.prefix.rstrip("/")
        base = f"files/blake3/{digest[:2]}/{digest[2:]}"
        return f"{prefix}/{base}" if prefix else base

    def exists(self, content_hash: str) -> bool:
        """オブジェクトがバケットに存在するかを返す."""
        key = self.object_key(content_hash)
        try:
            self._client.head_object(Bucket=self.remote.bucket, Key=key)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            if code in {"404", "NoSuchKey", "NotFound"}:
                return False
            msg = f"failed to head s3://{self.remote.bucket}/{key}: {exc}"
            raise RemoteError(msg) from exc
        else:
            return True

    def upload(self, local_path: Path, content_hash: str) -> None:
        """リモートに未存在ならローカルファイルをアップロードする."""
        key = self.object_key(content_hash)
        if self.exists(content_hash):
            return
        try:
            self._client.upload_file(
                Filename=str(local_path),
                Bucket=self.remote.bucket,
                Key=key,
                Config=self._transfer,
            )
        except ClientError as exc:
            msg = f"failed to upload {local_path} to s3://{self.remote.bucket}/{key}: {exc}"
            raise RemoteError(msg) from exc

    def download(self, content_hash: str, local_path: Path) -> None:
        """一時ファイル経由でリモートオブジェクトをローカルパスへダウンロードする."""
        key = self.object_key(content_hash)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = local_path.with_suffix(local_path.suffix + ".ditdownload")
        try:
            self._client.download_file(
                Bucket=self.remote.bucket,
                Key=key,
                Filename=str(tmp),
                Config=self._transfer,
            )
            tmp.replace(local_path)
        except ClientError as exc:
            if tmp.exists():
                tmp.unlink(missing_ok=True)
            msg = f"failed to download s3://{self.remote.bucket}/{key} to {local_path}: {exc}"
            raise RemoteError(msg) from exc

    def delete(self, content_hash: str) -> None:
        """コンテンツハッシュでリモートオブジェクトを削除する."""
        key = self.object_key(content_hash)
        try:
            self._client.delete_object(Bucket=self.remote.bucket, Key=key)
        except ClientError as exc:
            msg = f"failed to delete s3://{self.remote.bucket}/{key}: {exc}"
            raise RemoteError(msg) from exc

    def list_hashes(self) -> list[str]:
        """リモートプレフィックス配下に保存されたコンテンツハッシュを一覧する."""
        prefix = self.remote.prefix.rstrip("/")
        list_prefix = f"{prefix}/files/blake3/" if prefix else "files/blake3/"
        hashes: list[str] = []
        continuation: str | None = None
        while True:
            kwargs = {"Bucket": self.remote.bucket, "Prefix": list_prefix}
            if continuation:
                kwargs["ContinuationToken"] = continuation
            try:
                resp = self._client.list_objects_v2(**kwargs)
            except ClientError as exc:
                msg = f"failed to list s3://{self.remote.bucket}/{list_prefix}: {exc}"
                raise RemoteError(msg) from exc
            for obj in resp.get("Contents") or []:
                key = obj["Key"]
                digest = _digest_from_key(key, list_prefix)
                if digest:
                    hashes.append(f"blake3:{digest}")
            if not resp.get("IsTruncated"):
                break
            continuation = resp.get("NextContinuationToken")
        return hashes


def _digest_from_key(key: str, list_prefix: str) -> str | None:
    if not key.startswith(list_prefix):
        return None
    rest = key[len(list_prefix) :]
    parts = rest.split("/")
    if len(parts) != HASH_KEY_PART_COUNT:
        return None
    return parts[0] + parts[1]


def open_remote(remote: RemoteConfig) -> S3Remote:
    """指定設定で S3 リモートを開く."""
    return S3Remote(remote)
