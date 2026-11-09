"""S3 互換のリモートストレージバックエンド."""

from __future__ import annotations

import os
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from itertools import islice
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import TYPE_CHECKING, Any

import boto3
from boto3.exceptions import RetriesExceededError
from boto3.s3.transfer import S3Transfer, TransferConfig
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError

from dit.core.config import S3_REQUEST_TIMEOUT_SEC, RemoteConfig
from dit.core.errors import ConfigError, RemoteError
from dit.core.hasher import strip_hash_prefix
from dit.core.remote.base import Remote

if TYPE_CHECKING:
    from collections.abc import Callable
    from concurrent.futures import Future

MULTIPART_THRESHOLD_BYTES = 8 * 1024 * 1024
MULTIPART_CHUNKSIZE_BYTES = 8 * 1024 * 1024
DEFAULT_MAX_CONCURRENCY = 16
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


def _transfer_concurrency() -> int:
    value = os.environ.get("DIT_TRANSFER_CONCURRENCY")
    if value is None:
        return DEFAULT_MAX_CONCURRENCY
    msg = "DIT_TRANSFER_CONCURRENCY must be a positive integer"
    try:
        concurrency = int(value)
    except ValueError as exc:
        raise ConfigError(msg) from exc
    if concurrency < 1:
        raise ConfigError(msg)
    return concurrency


def _s3_client_kwargs(max_concurrency: int) -> dict[str, Any]:
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
            max_pool_connections=max_concurrency,
        ),
    }


class S3Remote(Remote):
    """コンテンツアドレスキーでオブジェクトを保存する S3 リモート."""

    def __init__(self, remote: RemoteConfig) -> None:
        """指定のリモート設定で S3 クライアントを作成する."""
        self.remote = remote
        concurrency = _transfer_concurrency()
        self._client = boto3.client("s3", **_s3_client_kwargs(concurrency))
        self._transfer = TransferConfig(
            multipart_threshold=MULTIPART_THRESHOLD_BYTES,
            multipart_chunksize=MULTIPART_CHUNKSIZE_BYTES,
            max_concurrency=concurrency,
            # CRT は max_concurrency を無視するため、設定が反映される転送実装を使う。
            preferred_transfer_client="classic",
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
        except (BotoCoreError, ClientError) as exc:
            if isinstance(exc, ClientError):
                code = exc.response.get("Error", {}).get("Code")
                if code in {"404", "NoSuchKey", "NotFound"}:
                    return False
            msg = f"failed to head s3://{self.remote.bucket}/{key}: {exc}"
            raise RemoteError(msg) from exc
        else:
            return True

    def exists_many(
        self,
        content_hashes: list[str],
        *,
        on_checked: Callable[[str], None] | None = None,
    ) -> dict[str, bool]:
        """重複ハッシュをまとめ、上限内で存在確認を並列に実行する."""
        hashes = dict.fromkeys(content_hashes)
        if not hashes:
            return {}
        workers = min(self._transfer.max_concurrency, len(hashes))
        remaining = iter(hashes)
        results: dict[str, bool] = {}
        with ThreadPoolExecutor(max_workers=workers) as executor:
            pending: dict[Future[bool], str] = {}

            def submit_batch(count: int) -> None:
                for content_hash in islice(remaining, count):
                    pending[executor.submit(self.exists, content_hash)] = content_hash

            try:
                submit_batch(workers)
                while pending:
                    done, _ = wait(pending, return_when=FIRST_COMPLETED)
                    for future in done:
                        content_hash = pending.pop(future)
                        results[content_hash] = future.result()
                        if on_checked is not None:
                            on_checked(content_hash)
                    submit_batch(len(done))
            finally:
                for future in pending:
                    future.cancel()
        return results

    def upload(
        self,
        local_path: Path,
        content_hash: str,
        *,
        progress: Callable[[int], None] | None = None,
    ) -> None:
        """リモートに未存在ならローカルファイルをアップロードする."""
        key = self.object_key(content_hash)
        if self.exists(content_hash):
            return
        self._put_object(local_path, key, progress)

    def download(
        self,
        content_hash: str,
        local_path: Path,
        *,
        progress: Callable[[int], None] | None = None,
    ) -> None:
        """一時ファイル経由でリモートオブジェクトをローカルパスへダウンロードする."""
        self.download_many([(content_hash, local_path)], progress=progress)

    def download_many(
        self,
        downloads: list[tuple[str, Path]],
        *,
        progress: Callable[[int], None] | None = None,
        on_start: Callable[[Path], None] | None = None,
    ) -> None:
        """全ファイルで転送枠を共有し、複数ファイルを並列にダウンロードする."""
        if not downloads:
            return
        paths = [path.resolve() for _, path in downloads]
        if len(set(paths)) != len(paths):
            msg = "duplicate download destination"
            raise RemoteError(msg)
        workers = min(self._transfer.max_concurrency, len(downloads))
        remaining = iter(downloads)
        # 例外時は転送を中断してから、ファイル単位のワーカーを終了する。
        with (
            ThreadPoolExecutor(max_workers=workers) as executor,
            S3Transfer(client=self._client, config=self._transfer) as transfer,
        ):

            def submit(download: tuple[str, Path]) -> Future[None]:
                return executor.submit(
                    self._download_file,
                    transfer,
                    *download,
                    progress=progress,
                    on_start=on_start,
                )

            pending: set[Future[None]] = set()
            try:
                pending.update(submit(item) for item in islice(remaining, workers))
                while pending:
                    done, pending = wait(pending, return_when=FIRST_COMPLETED)
                    for future in done:
                        future.result()
                    pending.update(submit(item) for item in islice(remaining, len(done)))
            finally:
                for future in pending:
                    future.cancel()

    def _download_file(
        self,
        transfer: S3Transfer,
        content_hash: str,
        local_path: Path,
        *,
        progress: Callable[[int], None] | None,
        on_start: Callable[[Path], None] | None,
    ) -> None:
        if on_start is not None:
            on_start(local_path)
        key = self.object_key(content_hash)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            prefix=f".{local_path.name}.",
            suffix=".ditdownload",
            dir=local_path.parent,
            delete=False,
        ) as temporary:
            tmp = Path(temporary.name)
        try:
            transfer.download_file(self.remote.bucket, key, str(tmp), callback=progress)
            tmp.replace(local_path)
        except (BotoCoreError, ClientError, RetriesExceededError) as exc:
            msg = f"failed to download s3://{self.remote.bucket}/{key} to {local_path}: {exc}"
            raise RemoteError(msg) from exc
        finally:
            tmp.unlink(missing_ok=True)

    def _put_object(
        self,
        local_path: Path,
        key: str,
        progress: Callable[[int], None] | None,
    ) -> None:
        try:
            self._client.upload_file(
                Filename=str(local_path),
                Bucket=self.remote.bucket,
                Key=key,
                Config=self._transfer,
                **_callback_kw(progress),
            )
        except ClientError as exc:
            msg = f"failed to upload {local_path} to s3://{self.remote.bucket}/{key}: {exc}"
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


def _callback_kw(progress: Callable[[int], None] | None) -> dict[str, Callable[[int], None]]:
    if progress is None:
        return {}
    return {"Callback": progress}


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
