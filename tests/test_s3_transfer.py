from __future__ import annotations

import threading
from typing import TYPE_CHECKING

import boto3
import pytest
from botocore.exceptions import ClientError, EndpointConnectionError
from moto import mock_aws

from dit.core.config import RemoteConfig
from dit.core.errors import ConfigError, RemoteError
from dit.core.hasher import hash_file
from dit.core.remote.s3 import S3Remote

if TYPE_CHECKING:
    from pathlib import Path

MIB = 1024 * 1024


@pytest.fixture(autouse=True)
def dit_remote_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIT_ACCESS_KEY", "testing")
    monkeypatch.setenv("DIT_SECRET_KEY", "testing")
    monkeypatch.setenv("DIT_ENDPOINT_URL", "https://s3.amazonaws.com")
    monkeypatch.delenv("DIT_TRANSFER_CONCURRENCY", raising=False)


class _RequestsInFlight:
    def __init__(self, expected: int) -> None:
        self.expected = expected
        self.active = 0
        self.peak = 0
        self.count = 0
        self.lock = threading.Lock()
        self.ready = threading.Event()

    def before(self, **kwargs) -> None:
        with self.lock:
            self.active += 1
            self.count += 1
            self.peak = max(self.peak, self.active)
            if self.active >= self.expected:
                self.ready.set()
        assert self.ready.wait(timeout=5), "transfer did not start requests concurrently"

    def after(self, **kwargs) -> None:
        with self.lock:
            self.active -= 1


@mock_aws
@pytest.mark.parametrize("concurrency", [None, 1, 2])
def test_multipart_roundtrip_respects_concurrency_and_reports_bytes(
    tmp_path: Path, monkeypatch, concurrency
) -> None:
    if concurrency is not None:
        monkeypatch.setenv("DIT_TRANSFER_CONCURRENCY", str(concurrency))
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")
    remote = S3Remote(RemoteConfig(bucket="test-bucket", prefix="md"))
    local = tmp_path / "source.dcd"
    # Six distinct parts, including a short final part, expose range/assembly errors.
    payload = b"".join(bytes([i]) * (8 * MIB) for i in range(5)) + b"last part"
    local.write_bytes(payload)
    digest = hash_file(local)
    expected = concurrency if concurrency is not None else 6
    uploads = _RequestsInFlight(expected)
    downloads = _RequestsInFlight(expected)
    for operation, capture in (("UploadPart", uploads), ("GetObject", downloads)):
        remote._client.meta.events.register(f"before-call.s3.{operation}", capture.before)
        remote._client.meta.events.register(f"after-call.s3.{operation}", capture.after)
    uploaded: list[int] = []
    downloaded: list[int] = []

    remote.upload(local, digest, progress=uploaded.append)
    target = tmp_path / "nested" / "target.dcd"
    remote.download(digest, target, progress=downloaded.append)

    assert target.read_bytes() == payload
    assert sum(uploaded) == sum(downloaded) == len(payload)
    assert uploads.count == downloads.count == 6
    assert uploads.peak == downloads.peak == expected
    assert uploads.active == downloads.active == 0
    assert not target.with_suffix(".dcd.ditdownload").exists()

    # A repeated upload must still skip an object that already exists.
    remote.upload(local, digest, progress=uploaded.append)
    assert uploads.count == 6
    assert sum(uploaded) == len(payload)


@mock_aws
@pytest.mark.parametrize("size", [0, 8 * MIB - 1, 8 * MIB, 8 * MIB + 1])
def test_roundtrip_at_multipart_boundary(tmp_path: Path, size: int) -> None:
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")
    remote = S3Remote(RemoteConfig(bucket="test-bucket", prefix="md"))
    source = tmp_path / "source.dcd"
    source.write_bytes(b"x" * size)
    digest = hash_file(source)
    uploaded: list[int] = []
    downloaded: list[int] = []

    remote.upload(source, digest, progress=uploaded.append)
    target = tmp_path / "target.dcd"
    remote.download(digest, target, progress=downloaded.append)

    assert target.read_bytes() == source.read_bytes()
    assert sum(uploaded) == sum(downloaded) == size


@pytest.mark.parametrize("value", ["", "0", "-1", "1.5", "many"])
def test_invalid_concurrency_rejected_before_creating_client(monkeypatch, value: str) -> None:
    monkeypatch.setenv("DIT_TRANSFER_CONCURRENCY", value)

    def unexpected_client(*args, **kwargs):
        pytest.fail("invalid transfer settings must fail before opening the S3 client")

    monkeypatch.setattr(boto3, "client", unexpected_client)
    with pytest.raises(ConfigError, match="DIT_TRANSFER_CONCURRENCY must be a positive integer"):
        S3Remote(RemoteConfig(bucket="test-bucket", prefix="md"))


@mock_aws
def test_failed_multipart_download_preserves_existing_file(tmp_path: Path) -> None:
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket="test-bucket")
    remote = S3Remote(RemoteConfig(bucket="test-bucket", prefix="md"))
    client.put_object(
        Bucket="test-bucket", Key=remote.object_key("blake3:abc"), Body=b"x" * (9 * MIB)
    )

    def fail_get(**kwargs) -> None:
        raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "missing"}}, "GetObject")

    remote._client.meta.events.register("before-call.s3.GetObject", fail_get)
    target = tmp_path / "target.dcd"
    target.write_bytes(b"existing data")

    with pytest.raises(RemoteError, match="failed to download"):
        remote.download("blake3:abc", target)

    assert target.read_bytes() == b"existing data"
    assert not target.with_suffix(".dcd.ditdownload").exists()


@mock_aws
@pytest.mark.parametrize(("concurrency", "size"), [(None, MIB), (1, MIB), (2, MIB), (3, 9 * MIB)])
def test_parallel_downloads_share_request_limit(tmp_path: Path, monkeypatch, concurrency, size):
    if concurrency is not None:
        monkeypatch.setenv("DIT_TRANSFER_CONCURRENCY", str(concurrency))
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket="test-bucket")
    remote = S3Remote(RemoteConfig(bucket="test-bucket", prefix="md"))
    downloads = []
    payloads = []
    for i in range(4):
        content_hash = f"blake3:{i:064x}"
        payload = bytes([i]) * size
        client.put_object(Bucket="test-bucket", Key=remote.object_key(content_hash), Body=payload)
        downloads.append((content_hash, tmp_path / "nested" / f"{i}.dcd"))
        payloads.append(payload)
    expected = concurrency or len(downloads)
    capture = _RequestsInFlight(expected)
    remote._client.meta.events.register("before-call.s3.GetObject", capture.before)
    remote._client.meta.events.register("after-call.s3.GetObject", capture.after)
    amounts = []
    started = []

    remote.download_many(downloads, progress=amounts.append, on_start=started.append)

    assert [path.read_bytes() for _, path in downloads] == payloads
    assert set(started) == {path for _, path in downloads}
    assert sum(amounts) == sum(map(len, payloads))
    assert capture.peak == expected
    assert capture.active == 0
    assert not list(tmp_path.rglob("*.ditdownload*"))


@mock_aws
def test_parallel_downloads_stop_after_error(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DIT_TRANSFER_CONCURRENCY", "2")
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket="test-bucket")
    remote = S3Remote(RemoteConfig(bucket="test-bucket", prefix="md"))
    downloads = []
    for i in range(6):
        content_hash = f"blake3:{i:064x}"
        client.put_object(Bucket="test-bucket", Key=remote.object_key(content_hash), Body=b"new")
        downloads.append((content_hash, tmp_path / f"{i}.dcd"))
    existing = downloads[0][1]
    existing.write_bytes(b"existing data")

    def fail_get(**kwargs) -> None:
        raise ClientError({"Error": {"Code": "AccessDenied", "Message": "denied"}}, "GetObject")

    remote._client.meta.events.register("before-call.s3.GetObject", fail_get)
    started = []
    amounts = []

    with pytest.raises(RemoteError, match="failed to download"):
        remote.download_many(downloads, progress=amounts.append, on_start=started.append)

    assert len(started) <= 2
    assert existing.read_bytes() == b"existing data"
    assert not any(path.exists() for _, path in downloads[1:])
    assert not list(tmp_path.rglob("*.ditdownload*"))
    assert amounts == []


@mock_aws
def test_parallel_downloads_reject_duplicate_destinations(tmp_path: Path):
    remote = S3Remote(RemoteConfig(bucket="test-bucket", prefix="md"))
    target = tmp_path / "existing.dcd"
    target.write_bytes(b"existing data")
    started = []

    with pytest.raises(RemoteError, match="duplicate download destination"):
        remote.download_many(
            [("blake3:aaa", target), ("blake3:bbb", target)], on_start=started.append
        )

    assert target.read_bytes() == b"existing data"
    assert started == []


@mock_aws
def test_download_staging_does_not_overwrite_another_destination(tmp_path: Path):
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket="test-bucket")
    remote = S3Remote(RemoteConfig(bucket="test-bucket", prefix="md"))
    client.put_object(Bucket="test-bucket", Key=remote.object_key("blake3:aaa"), Body=b"first")
    client.put_object(Bucket="test-bucket", Key=remote.object_key("blake3:bbb"), Body=b"second")
    target = tmp_path / "target.dcd"
    similar = tmp_path / "target.dcd.ditdownload"
    similar.write_bytes(b"existing data")
    remote.download("blake3:aaa", target)
    assert target.read_bytes() == b"first"
    assert similar.read_bytes() == b"existing data"

    remote.download_many([("blake3:aaa", target), ("blake3:bbb", similar)])

    assert target.read_bytes() == b"first"
    assert similar.read_bytes() == b"second"
    assert set(tmp_path.iterdir()) == {target, similar}


@mock_aws
@pytest.mark.parametrize("concurrency", [None, 1, 2])
def test_parallel_exists_checks_deduplicate_and_report_present_and_missing(
    monkeypatch, concurrency
):
    if concurrency is not None:
        monkeypatch.setenv("DIT_TRANSFER_CONCURRENCY", str(concurrency))
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket="test-bucket")
    remote = S3Remote(RemoteConfig(bucket="test-bucket", prefix="md"))
    hashes = [f"blake3:{i:064x}" for i in range(4)]
    for content_hash in hashes[:2]:
        client.put_object(Bucket="test-bucket", Key=remote.object_key(content_hash), Body=b"data")
    capture = _RequestsInFlight(concurrency or len(hashes))
    remote._client.meta.events.register("before-call.s3.HeadObject", capture.before)
    remote._client.meta.events.register("after-call.s3.HeadObject", capture.after)
    checked = []
    main_thread = threading.get_ident()

    def report(content_hash):
        assert threading.get_ident() == main_thread
        checked.append(content_hash)

    results = remote.exists_many([*hashes, *hashes], on_checked=report)

    assert results == dict(zip(hashes, [True, True, False, False], strict=True))
    assert capture.count == len(hashes)
    assert capture.peak == (concurrency or len(hashes))
    assert sorted(checked) == hashes

    client.delete_object(Bucket="test-bucket", Key=remote.object_key(hashes[0]))
    assert remote.exists_many([hashes[0]]) == {hashes[0]: False}
    assert capture.count == len(hashes) + 1


@pytest.mark.parametrize("error", ["permission", "connection"])
def test_parallel_exists_checks_propagate_errors_and_stop_queuing(monkeypatch, error):
    monkeypatch.setenv("DIT_TRANSFER_CONCURRENCY", "2")
    remote = S3Remote(RemoteConfig(bucket="test-bucket", prefix="md"))
    barrier = threading.Barrier(2)
    calls = []

    def fail_head(**kwargs):
        calls.append(kwargs["Key"])
        barrier.wait(timeout=5)
        if error == "connection":
            raise EndpointConnectionError(endpoint_url="https://storage.invalid")
        raise ClientError({"Error": {"Code": "AccessDenied", "Message": "denied"}}, "HeadObject")

    monkeypatch.setattr(remote._client, "head_object", fail_head)
    with pytest.raises(RemoteError, match="failed to head"):
        remote.exists_many([f"blake3:{i:064x}" for i in range(10)])

    assert len(calls) == 2


def test_empty_exists_check_does_not_request_remote(monkeypatch):
    remote = S3Remote(RemoteConfig(bucket="test-bucket", prefix="md"))

    def unexpected_head(**kwargs):
        pytest.fail("empty input must not query S3")

    monkeypatch.setattr(remote._client, "head_object", unexpected_head)
    assert remote.exists_many([]) == {}
