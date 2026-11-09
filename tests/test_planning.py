from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING

import boto3
import pytest
from blake3 import blake3
from moto import mock_aws

from dit.core.config import RemoteConfig, init_config
from dit.core.pointer import Pointer, write_pointer
from dit.core.remote.s3 import S3Remote
from dit.core.repo import Repo
from dit.core.scope import Scope
from dit.core.sync_service import plan_push, plan_sync

if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class _Progress:
    total: int = 0
    completed: int = 0

    def set_total(self, total_files):
        self.total = total_files

    def advance(self):
        self.completed += 1


@pytest.fixture(autouse=True)
def dit_remote_env(monkeypatch):
    monkeypatch.setenv("DIT_ACCESS_KEY", "testing")
    monkeypatch.setenv("DIT_SECRET_KEY", "testing")
    monkeypatch.setenv("DIT_ENDPOINT_URL", "https://s3.amazonaws.com")
    monkeypatch.setenv("DIT_TRANSFER_CONCURRENCY", "2")


def _pointer(repo, name, *, local_payload, pointer_payload, local_newer=False):
    path = repo.root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if local_payload is not None:
        path.write_bytes(local_payload)
        os.utime(path, ns=(1_000_000_000, 1_000_000_000))
    digest = f"blake3:{blake3(pointer_payload).hexdigest()}"
    pointer = write_pointer(repo.root, Pointer(path=name, hash=digest, size=len(pointer_payload)))
    os.utime(pointer, ns=(2_000_000_000, 2_000_000_000))
    if local_newer:
        os.utime(path, ns=(3_000_000_000, 3_000_000_000))
    return digest


@mock_aws
@pytest.mark.parametrize("local_newer_remote_exists", [False, True])
@pytest.mark.parametrize("pointer_newer_remote_exists", [False, True])
def test_sync_plan_preserves_decisions_with_parallel_checks(
    tmp_path: Path, monkeypatch, local_newer_remote_exists, pointer_newer_remote_exists
):
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket="test-bucket")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".dit").mkdir()
    init_config(bucket="test-bucket", prefix="md").save(tmp_path / "dit.toml")
    repo = Repo(root=tmp_path)
    remote = S3Remote(RemoteConfig(bucket="test-bucket", prefix="md"))
    monkeypatch.setattr("dit.core.sync_service.require_remote", lambda config: remote)
    matched = _pointer(repo, "keep/a.dcd", local_payload=b"same", pointer_payload=b"same")
    to_push = _pointer(repo, "keep/b.dcd", local_payload=b"push", pointer_payload=b"push")
    to_pull = _pointer(repo, "keep/c.dcd", local_payload=None, pointer_payload=b"pull")
    missing = _pointer(repo, "keep/d.dcd", local_payload=None, pointer_payload=b"missing")
    _pointer(
        repo, "keep/e.dcd", local_payload=b"new local", pointer_payload=b"stale", local_newer=True
    )
    new_local = f"blake3:{blake3(b'new local').hexdigest()}"
    new_pointer = _pointer(repo, "keep/f.dcd", local_payload=b"old", pointer_payload=b"new remote")
    (tmp_path / "keep/g.dcd").write_bytes(b"no pointer")
    _pointer(repo, "keep/h.dcd", local_payload=None, pointer_payload=b"same")
    _pointer(repo, "outside/i.dcd", local_payload=b"out", pointer_payload=b"out")
    Scope(repo).add(tmp_path / "keep")
    present = [matched, to_pull]
    if local_newer_remote_exists:
        present.append(new_local)
    if pointer_newer_remote_exists:
        present.append(new_pointer)
    for digest in present:
        client.put_object(Bucket="test-bucket", Key=remote.object_key(digest), Body=b"object")
    original_exists = remote.exists
    checked = []

    def exists(digest):
        checked.append(digest)
        return original_exists(digest)

    monkeypatch.setattr(remote, "exists", exists)
    before = {p: p.read_bytes() for p in tmp_path.rglob("*.dcd*")}
    progress = _Progress()

    steps = plan_sync(repo, progress=progress)

    expected = [("a", "ok"), ("b", "push"), ("c", "pull"), ("d", "error"), ("e", "update_pointer")]
    if not local_newer_remote_exists:
        expected.append(("e", "push"))
    expected.extend(
        [("f", "pull" if pointer_newer_remote_exists else "error"), ("g", "warning"), ("h", "pull")]
    )
    assert [(step.result.path, step.result.action) for step in steps] == [
        (f"keep/{name}.dcd", action) for name, action in expected
    ]
    assert set(checked) == {matched, to_push, to_pull, missing, new_local, new_pointer}
    assert len(checked) == 6
    assert (progress.total, progress.completed) == (9, 9)
    assert {p: p.read_bytes() for p in tmp_path.rglob("*.dcd*")} == before


@mock_aws
@pytest.mark.parametrize("plan", [plan_push, plan_sync])
def test_plan_checks_distinct_hashes_concurrently_and_counts_duplicate_paths(
    tmp_path: Path, monkeypatch, plan
):
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket="test-bucket")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".dit").mkdir()
    init_config(bucket="test-bucket", prefix="md").save(tmp_path / "dit.toml")
    repo = Repo(root=tmp_path)
    for name, payload in [("a", b"one"), ("b", b"two"), ("c", b"one")]:
        _pointer(repo, f"{name}.dcd", local_payload=payload, pointer_payload=payload)
    remote = S3Remote(RemoteConfig(bucket="test-bucket", prefix="md"))
    monkeypatch.setattr("dit.core.sync_service.require_remote", lambda config: remote)
    barrier = threading.Barrier(2)
    checked = []

    def before_head(**kwargs):
        checked.append(kwargs["params"]["url_path"])
        barrier.wait(timeout=5)

    remote._client.meta.events.register("before-call.s3.HeadObject", before_head)
    progress = _Progress()

    planned = plan(repo, progress=progress)

    assert len(planned) == 3
    assert len(checked) == 2
    assert (progress.total, progress.completed) == (3, 3)
