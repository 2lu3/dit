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
def test_bulk_exists_checks_deduplicate_and_refresh_present_and_missing():
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket="test-bucket")
    remote = S3Remote(RemoteConfig(bucket="test-bucket", prefix="md"))
    hashes = [f"blake3:{i:064x}" for i in range(4)]
    for content_hash in hashes[:2]:
        client.put_object(Bucket="test-bucket", Key=remote.object_key(content_hash), Body=b"data")
    requests = []

    def before_list(**kwargs):
        requests.append(kwargs["params"]["query_string"])

    def unexpected_head(**kwargs):
        pytest.fail("bulk checks must not issue HEAD requests")

    remote._client.meta.events.register("before-call.s3.ListObjectsV2", before_list)
    remote._client.meta.events.register("before-call.s3.HeadObject", unexpected_head)
    checked = []
    main_thread = threading.get_ident()

    def report(content_hash):
        assert threading.get_ident() == main_thread
        checked.append(content_hash)

    results = remote.exists_many([*hashes, *hashes], on_checked=report)

    assert results == dict(zip(hashes, [True, True, False, False], strict=True))
    assert len(requests) == 1
    assert requests[0]["prefix"] == "md/files/blake3/"
    assert sorted(checked) == hashes

    client.delete_object(Bucket="test-bucket", Key=remote.object_key(hashes[0]))
    assert remote.exists_many([hashes[0]]) == {hashes[0]: False}
    assert len(requests) == 2


@pytest.mark.parametrize("error", ["permission", "connection"])
def test_bulk_exists_checks_propagate_errors(monkeypatch, error):
    remote = S3Remote(RemoteConfig(bucket="test-bucket", prefix="md"))
    calls = []

    def fail_list(**kwargs):
        calls.append(kwargs["Prefix"])
        if error == "connection":
            raise EndpointConnectionError(endpoint_url="https://storage.invalid")
        raise ClientError({"Error": {"Code": "AccessDenied", "Message": "denied"}}, "ListObjectsV2")

    monkeypatch.setattr(remote._client, "list_objects_v2", fail_list)
    checked = []
    with pytest.raises(RemoteError, match="failed to list"):
        remote.exists_many([f"blake3:{i:064x}" for i in range(10)], on_checked=checked.append)

    assert len(calls) == 1
    assert checked == []


def test_empty_exists_check_does_not_request_remote(monkeypatch):
    remote = S3Remote(RemoteConfig(bucket="test-bucket", prefix="md"))

    def unexpected_request(**kwargs):
        pytest.fail("empty input must not query S3")

    monkeypatch.setattr(remote._client, "head_object", unexpected_request)
    monkeypatch.setattr(remote._client, "list_objects_v2", unexpected_request)
    assert remote.exists_many([]) == {}


@mock_aws
def test_bulk_exists_checks_all_pages_within_prefix(monkeypatch):
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket="test-bucket")
    remote = S3Remote(RemoteConfig(bucket="test-bucket", prefix="md"))
    hashes = [f"blake3:{i:064x}" for i in range(5)]
    for content_hash in hashes[:4]:
        client.put_object(Bucket="test-bucket", Key=remote.object_key(content_hash), Body=b"x")
    client.put_object(
        Bucket="test-bucket", Key="other/" + remote.object_key(hashes[4]), Body=b"other project"
    )
    # ハッシュ文字列が同じでも、キーの分割位置が違えば実体の保存先ではない。
    digest = hashes[4].removeprefix("blake3:")
    client.put_object(
        Bucket="test-bucket", Key=f"md/files/blake3/{digest[:1]}/{digest[1:]}", Body=b"wrong key"
    )
    original_list = remote._client.list_objects_v2
    calls = []

    def small_pages(**kwargs):
        calls.append(kwargs.copy())
        return original_list(**(kwargs | {"MaxKeys": 2}))

    monkeypatch.setattr(remote._client, "list_objects_v2", small_pages)

    assert remote.exists_many(hashes) == dict.fromkeys(hashes[:4], True) | {hashes[4]: False}
    assert len(calls) == 3
    assert "ContinuationToken" not in calls[0]
    assert calls[1]["ContinuationToken"]
    assert all(call["Prefix"] == "md/files/blake3/" for call in calls)


@pytest.mark.parametrize("failure", ["missing_token", "repeated_token", "second_page"])
def test_bulk_exists_checks_do_not_accept_incomplete_listing(monkeypatch, failure):
    remote = S3Remote(RemoteConfig(bucket="test-bucket", prefix="md"))
    calls = []
    checked = []

    def incomplete_page(**kwargs):
        calls.append(kwargs)
        if failure == "second_page" and len(calls) == 2:
            raise EndpointConnectionError(endpoint_url="https://storage.invalid")
        page = {"IsTruncated": True, "Contents": [{"Key": remote.object_key("blake3:abc")}]}
        if failure != "missing_token":
            page["NextContinuationToken"] = "same-token"
        return page

    monkeypatch.setattr(remote._client, "list_objects_v2", incomplete_page)

    with pytest.raises(RemoteError):
        remote.exists_many(["blake3:abc", "blake3:def"], on_checked=checked.append)

    assert checked == []
    assert len(calls) <= 2


@mock_aws
@pytest.mark.parametrize(
    ("concurrency", "size"), [(None, MIB), (1, MIB), (2, MIB), (3, 9 * MIB), (2, None)]
)
def test_parallel_uploads_share_request_limit(tmp_path: Path, monkeypatch, concurrency, size):
    if concurrency is not None:
        monkeypatch.setenv("DIT_TRANSFER_CONCURRENCY", str(concurrency))
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket="test-bucket")
    remote = S3Remote(RemoteConfig(bucket="test-bucket", prefix="md"))
    uploads = []
    for i in range(4):
        path = tmp_path / f"{i}.dcd"
        file_size = size if size is not None else [0, 1, 9 * MIB, MIB][i]
        path.write_bytes(bytes([i]) * file_size)
        uploads.append((hash_file(path), path))
    capture = _RequestsInFlight(concurrency or len(uploads))
    for operation in ("PutObject", "UploadPart"):
        remote._client.meta.events.register(f"before-call.s3.{operation}", capture.before)
        remote._client.meta.events.register(f"after-call.s3.{operation}", capture.after)

    def unexpected_head(**kwargs):
        pytest.fail("planned uploads must not repeat HEAD checks")

    remote._client.meta.events.register("before-call.s3.HeadObject", unexpected_head)
    main_thread = threading.get_ident()
    started = []
    completed = []
    amounts = []

    def iter_uploads():
        for item in uploads:
            assert threading.get_ident() == main_thread
            yield item

    def uploaded(path):
        assert threading.get_ident() == main_thread
        completed.append(path)

    remote.upload_many(
        iter_uploads(), progress=amounts.append, on_start=started.append, on_uploaded=uploaded
    )

    for content_hash, path in uploads:
        body = client.get_object(Bucket="test-bucket", Key=remote.object_key(content_hash))["Body"]
        assert body.read() == path.read_bytes()
    assert set(started) == set(completed) == {path for _, path in uploads}
    assert sum(amounts) == sum(path.stat().st_size for _, path in uploads)
    assert capture.peak == (concurrency or len(uploads))
    assert capture.active == 0


@mock_aws
def test_parallel_uploads_stop_after_error(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("DIT_TRANSFER_CONCURRENCY", "2")
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket="test-bucket")
    remote = S3Remote(RemoteConfig(bucket="test-bucket", prefix="md"))
    uploads = []
    for i in range(6):
        path = tmp_path / f"{i}.dcd"
        path.write_bytes(bytes([i]))
        uploads.append((hash_file(path), path))
    barrier = threading.Barrier(2)

    def fail_put(**kwargs):
        barrier.wait(timeout=5)
        raise ClientError({"Error": {"Code": "AccessDenied", "Message": "denied"}}, "PutObject")

    remote._client.meta.events.register("before-call.s3.PutObject", fail_put)
    started = []
    completed = []
    with pytest.raises(RemoteError, match="failed to upload"):
        remote.upload_many(uploads, on_start=started.append, on_uploaded=completed.append)

    assert len(started) == 2
    assert completed == []
    assert remote.list_hashes() == []
