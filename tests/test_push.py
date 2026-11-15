from __future__ import annotations

import os
import sqlite3
import threading
import time
from typing import TYPE_CHECKING
from unittest.mock import Mock

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from dit.core.config import RemoteConfig, init_config
from dit.core.content import resolve_content_hash
from dit.core.errors import RemoteError, RepoError
from dit.core.hasher import hash_file
from dit.core.index import StatIndex, file_stat_tuple
from dit.core.pointer import Pointer, write_pointer
from dit.core.remote.s3 import S3Remote
from dit.core.repo import Repo
from dit.core.scope import Scope
from dit.core.sync_service import plan_push, run_push

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def dit_remote_env(monkeypatch):
    monkeypatch.setenv("DIT_ACCESS_KEY", "testing")
    monkeypatch.setenv("DIT_SECRET_KEY", "testing")
    monkeypatch.setenv("DIT_ENDPOINT_URL", "https://s3.amazonaws.com")
    monkeypatch.setenv("DIT_TRANSFER_CONCURRENCY", "2")


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    (tmp_path / ".git").mkdir()
    (tmp_path / ".dit").mkdir()
    init_config(bucket="test-bucket", prefix="md").save(tmp_path / "dit.toml")
    return Repo(root=tmp_path)


def _file(repo, name="a.dcd", payload=b"original", *, cache=True):
    path = repo.root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    with StatIndex(repo.index_db) as index:
        digest = resolve_content_hash(repo, index, path) if cache else hash_file(path)
    write_pointer(repo.root, Pointer(path=name, hash=digest, size=len(payload)))
    return path, digest


def test_legacy_index_migrates_and_rehashes_once(repo, monkeypatch):
    path = repo.root / "a.dcd"
    path.write_bytes(b"original")
    size, mtime_ns, inode, ctime_ns = file_stat_tuple(path)
    with sqlite3.connect(repo.index_db) as conn:
        conn.execute(
            "CREATE TABLE entries (path TEXT PRIMARY KEY, size INTEGER NOT NULL, "
            "mtime_ns INTEGER NOT NULL, inode INTEGER NOT NULL, hash TEXT NOT NULL, "
            "pushed_at TEXT)"
        )
        conn.execute(
            "INSERT INTO entries VALUES (?, ?, ?, ?, ?, ?)",
            ("a.dcd", size, mtime_ns, inode, hash_file(path), "previous-push"),
        )
    hashing = Mock(wraps=hash_file)
    monkeypatch.setattr("dit.core.content.hash_file", hashing)

    with StatIndex(repo.index_db) as index:
        assert index.get("a.dcd").ctime_ns is None
        assert index.get("a.dcd").pushed_at == "previous-push"
        assert resolve_content_hash(repo, index, path) == hash_file(path)
        assert index.get("a.dcd").ctime_ns == ctime_ns
        assert index.get("a.dcd").pushed_at == "previous-push"
    with StatIndex(repo.index_db) as index:
        assert resolve_content_hash(repo, index, path) == hash_file(path)
        assert index.all_entries()[0].ctime_ns == ctime_ns
    hashing.assert_called_once_with(path)


def test_hash_cache_detects_overwrite_with_preserved_mtime_and_size(repo):
    path, original = _file(repo)
    before = path.stat()
    time.sleep(0.01)
    path.write_bytes(b"modified")
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    after = path.stat()
    assert (after.st_size, after.st_ino, after.st_mtime_ns) == (
        before.st_size,
        before.st_ino,
        before.st_mtime_ns,
    )
    assert after.st_ctime_ns != before.st_ctime_ns

    with StatIndex(repo.index_db) as index:
        index.mark_pushed("a.dcd", "previous-push")
        changed = resolve_content_hash(repo, index, path)
        assert changed != original
        assert changed == hash_file(path)
        assert index.get("a.dcd").pushed_at is None


def test_file_changed_during_hash_is_not_cached(repo, monkeypatch):
    path, _ = _file(repo, cache=False)

    def changing_hash(path):
        digest = hash_file(path)
        path.write_bytes(b"modified while hashing")
        return digest

    monkeypatch.setattr("dit.core.content.hash_file", changing_hash)
    with StatIndex(repo.index_db) as index:
        with pytest.raises(RepoError, match="changed while hashing"):
            resolve_content_hash(repo, index, path)
        assert index.get("a.dcd") is None


@mock_aws
@pytest.mark.parametrize("cache", [False, True])
def test_push_reuses_hash_across_planning_upload_and_repeated_push(repo, monkeypatch, cache):
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket="test-bucket")
    path, digest = _file(repo, cache=cache)
    hashing = Mock(wraps=hash_file)
    monkeypatch.setattr("dit.core.content.hash_file", hashing)
    remote = S3Remote(RemoteConfig(bucket="test-bucket", prefix="md"))
    monkeypatch.setattr("dit.core.sync_service.require_remote", lambda config: remote)
    head = Mock(side_effect=AssertionError("push must use LIST instead of HEAD"))
    monkeypatch.setattr(remote._client, "head_object", head)

    jobs = plan_push(repo)
    assert [job.path for job in jobs] == ["a.dcd"]
    run_push(repo, jobs=jobs)
    assert run_push(repo) == []

    assert hashing.call_count == (0 if cache else 1)
    body = client.get_object(Bucket="test-bucket", Key=remote.object_key(digest))["Body"]
    assert body.read() == path.read_bytes()
    head.assert_not_called()
    with StatIndex(repo.index_db) as index:
        assert index.get("a.dcd").pushed_at is not None


@mock_aws
@pytest.mark.parametrize("after_plan", [False, True])
def test_push_rejects_changed_content_even_with_restored_mtime(repo, monkeypatch, after_plan):
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")
    path, _ = _file(repo)
    jobs = plan_push(repo) if after_plan else None
    before = path.stat()
    time.sleep(0.01)
    path.write_bytes(b"modified")
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    remote = S3Remote(RemoteConfig(bucket="test-bucket", prefix="md"))
    monkeypatch.setattr("dit.core.sync_service.require_remote", lambda config: remote)

    with pytest.raises(RepoError, match="differs from pointer"):
        run_push(repo, jobs=jobs)

    assert remote.list_hashes() == []
    with StatIndex(repo.index_db) as index:
        assert index.get("a.dcd").pushed_at is None


@mock_aws
def test_push_uploads_files_concurrently_including_outside_scope(repo, monkeypatch):
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket="test-bucket")
    _file(repo, "keep/a.dcd", b"aaa")
    _file(repo, "other/b.dcd", b"bbb")
    Scope(repo).add(repo.root / "keep")
    remote = S3Remote(RemoteConfig(bucket="test-bucket", prefix="md"))
    monkeypatch.setattr("dit.core.sync_service.require_remote", lambda config: remote)
    barrier = threading.Barrier(2)

    def wait_for_other_file(**kwargs):
        barrier.wait(timeout=5)

    remote._client.meta.events.register("before-call.s3.PutObject", wait_for_other_file)

    results = run_push(repo)

    assert [result.path for result in results] == ["keep/a.dcd", "other/b.dcd"]
    with StatIndex(repo.index_db) as index:
        assert all(entry.pushed_at is not None for entry in index.all_entries())
    assert len(remote.list_hashes()) == 2


@mock_aws
def test_push_deduplicates_content_after_validating_every_path(repo, monkeypatch):
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")
    _file(repo, "a.dcd", b"same")
    other, _ = _file(repo, "b.dcd", b"same")
    remote = S3Remote(RemoteConfig(bucket="test-bucket", prefix="md"))
    monkeypatch.setattr("dit.core.sync_service.require_remote", lambda config: remote)
    requests = []

    def record_put(**kwargs):
        requests.append(kwargs)

    remote._client.meta.events.register("before-call.s3.PutObject", record_put)

    jobs = plan_push(repo)
    assert len(jobs) == 1
    assert sum(job.size for job in jobs) == 4
    run_push(repo, jobs=jobs)
    assert len(requests) == 1

    other.write_bytes(b"changed duplicate")
    with pytest.raises(RepoError, match=r"b\.dcd: local content differs"):
        plan_push(repo)


@mock_aws
def test_push_dry_run_does_not_upload_or_mark_pushed(repo, monkeypatch):
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")
    _file(repo)
    remote = S3Remote(RemoteConfig(bucket="test-bucket", prefix="md"))
    monkeypatch.setattr("dit.core.sync_service.require_remote", lambda config: remote)
    upload = Mock(side_effect=AssertionError("dry-run must not upload"))
    monkeypatch.setattr(remote, "upload_many", upload)

    assert len(run_push(repo, dry_run=True)) == 1
    upload.assert_not_called()
    with StatIndex(repo.index_db) as index:
        assert index.get("a.dcd").pushed_at is None


@mock_aws
def test_failed_listing_prevents_upload(repo, monkeypatch):
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")
    _file(repo)
    remote = S3Remote(RemoteConfig(bucket="test-bucket", prefix="md"))
    monkeypatch.setattr("dit.core.sync_service.require_remote", lambda config: remote)

    def fail_list(**kwargs):
        raise ClientError({"Error": {"Code": "AccessDenied"}}, "ListObjectsV2")

    monkeypatch.setattr(remote._client, "list_objects_v2", fail_list)
    upload = Mock()
    monkeypatch.setattr(remote, "upload_many", upload)

    with pytest.raises(RemoteError, match="failed to list"):
        run_push(repo)
    upload.assert_not_called()


@mock_aws
def test_push_retry_skips_successful_objects_after_partial_failure(repo, monkeypatch):
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket="test-bucket")
    _, first_hash = _file(repo, "a.dcd", b"aaa")
    _, second_hash = _file(repo, "b.dcd", b"bbb")
    remote = S3Remote(RemoteConfig(bucket="test-bucket", prefix="md"))
    monkeypatch.setattr("dit.core.sync_service.require_remote", lambda config: remote)
    first_uploaded = threading.Event()
    original_put = remote._client.put_object

    def put_with_partial_failure(**kwargs):
        if kwargs["Key"] == remote.object_key(first_hash):
            response = original_put(**kwargs)
            first_uploaded.set()
            return response
        assert first_uploaded.wait(timeout=5)
        raise ClientError({"Error": {"Code": "AccessDenied"}}, "PutObject")

    with monkeypatch.context() as patch:
        patch.setattr(remote._client, "put_object", put_with_partial_failure)
        with pytest.raises(RemoteError, match="failed to upload"):
            run_push(repo)

    assert remote.list_hashes() == [first_hash]
    with StatIndex(repo.index_db) as index:
        assert index.get("b.dcd").pushed_at is None

    put = Mock(wraps=original_put)
    monkeypatch.setattr(remote._client, "put_object", put)
    results = run_push(repo)

    assert [result.path for result in results] == ["b.dcd"]
    put.assert_called_once()
    assert set(remote.list_hashes()) == {first_hash, second_hash}


@mock_aws
def test_push_does_not_hold_index_write_lock_while_uploading(repo, monkeypatch):
    monkeypatch.setenv("DIT_TRANSFER_CONCURRENCY", "1")
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")
    _file(repo, "a.dcd", b"aaa")
    _file(repo, "b.dcd", b"bbb")
    remote = S3Remote(RemoteConfig(bucket="test-bucket", prefix="md"))
    monkeypatch.setattr("dit.core.sync_service.require_remote", lambda config: remote)
    calls = []

    def concurrent_index_writer(**kwargs):
        calls.append(kwargs)
        if len(calls) == 2:
            # 1件目の完了記録が、2件目の通信中に DB をロックしていないこと。
            with sqlite3.connect(repo.index_db, timeout=0) as conn:
                conn.execute("UPDATE entries SET pushed_at = NULL WHERE path = 'a.dcd'")

    remote._client.meta.events.register("before-call.s3.PutObject", concurrent_index_writer)

    assert len(run_push(repo)) == 2
    assert len(calls) == 2
    with StatIndex(repo.index_db) as index:
        assert all(entry.pushed_at is not None for entry in index.all_entries())
