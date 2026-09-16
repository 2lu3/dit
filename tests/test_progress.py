from __future__ import annotations

import io
import re
from typing import TYPE_CHECKING

import boto3
import pytest
from moto import mock_aws

from dit.command.progress import ByteTransferBar
from dit.core.add_service import run_add
from dit.core.config import RemoteConfig, init_config
from dit.core.hasher import hash_file
from dit.core.remote.s3 import S3Remote
from dit.core.repo import Repo
from dit.core.scope import Scope
from dit.core.sync_service import collect_sync_jobs, plan_pull, plan_push, plan_sync, run_push

if TYPE_CHECKING:
    from pathlib import Path

KIBIBYTE = 1024
MEBIBYTE = 1024 * 1024
GIBIBYTE = 1024 * 1024 * 1024
ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def _visible(buf: io.StringIO) -> str:
    return ANSI_ESCAPE.sub("", buf.getvalue())


@pytest.fixture(autouse=True)
def dit_remote_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIT_ACCESS_KEY", "testing")
    monkeypatch.setenv("DIT_SECRET_KEY", "testing")
    monkeypatch.setenv("DIT_ENDPOINT_URL", "https://s3.amazonaws.com")


def test_byte_transfer_bar_monitor_uses_kmg_byte_units() -> None:
    buf = io.StringIO()
    with ByteTransferBar(2 * GIBIBYTE, "push", stream=buf) as bar:
        bar.add_bytes(MEBIBYTE)
        assert bar.current == MEBIBYTE
    assert "1.0Mbyte/2Gbyte" in _visible(buf)


def test_byte_transfer_bar_monitor_uses_kbyte_for_small_totals() -> None:
    buf = io.StringIO()
    with ByteTransferBar(2 * KIBIBYTE, "pull", stream=buf) as bar:
        bar.add_bytes(KIBIBYTE + KIBIBYTE // 2)
        assert bar.current == KIBIBYTE + KIBIBYTE // 2
    assert "1.5Kbyte/2Kbyte" in _visible(buf)


def test_byte_transfer_bar_ignores_non_positive_deltas() -> None:
    buf = io.StringIO()
    with ByteTransferBar(MEBIBYTE, "push", stream=buf) as bar:
        bar.add_bytes(0)
        bar.add_bytes(-1)
        assert bar.current == 0
    assert "0.0byte/1Mbyte" in _visible(buf)


@mock_aws
def test_s3_upload_and_download_report_transferred_bytes(tmp_path: Path) -> None:
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")
    remote = S3Remote(RemoteConfig(bucket="test-bucket", prefix="md"))
    local = tmp_path / "a.dcd"
    payload = b"hello-md-bytes"
    local.write_bytes(payload)
    digest = hash_file(local)
    uploaded: list[int] = []
    downloaded: list[int] = []

    remote.upload(local, digest, progress=uploaded.append)
    out = tmp_path / "b.dcd"
    remote.download(digest, out, progress=downloaded.append)

    assert sum(uploaded) == len(payload)
    assert sum(downloaded) == len(payload)
    assert out.read_bytes() == payload


@mock_aws
def test_plan_push_and_pull_use_file_and_pointer_sizes(tmp_path: Path) -> None:
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")
    root = tmp_path / "proj"
    root.mkdir()
    (root / ".git").mkdir()
    (root / ".dit").mkdir()
    config = init_config(bucket="test-bucket", prefix="md")
    config.save(root / "dit.toml")
    repo = Repo(root=root)
    keep = root / "keep"
    keep.mkdir()
    target = keep / "a.dcd"
    target.write_bytes(b"payload-size")
    Scope(repo).add(keep)
    run_add(repo, quiet=True)
    push_jobs = plan_push(repo)
    assert [job.size for job in push_jobs] == [len(b"payload-size")]
    assert [job.path for job in push_jobs] == ["keep/a.dcd"]

    run_push(repo, dry_run=False)
    target.unlink()
    pull_jobs = plan_pull(repo)
    assert [job.size for job in pull_jobs] == [len(b"payload-size")]
    assert [job.path for job in pull_jobs] == ["keep/a.dcd"]


@mock_aws
def test_plan_sync_jobs_use_file_and_pointer_sizes(tmp_path: Path) -> None:
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")
    root = tmp_path / "proj"
    root.mkdir()
    (root / ".git").mkdir()
    (root / ".dit").mkdir()
    config = init_config(bucket="test-bucket", prefix="md")
    config.save(root / "dit.toml")
    repo = Repo(root=root)
    keep = root / "keep"
    keep.mkdir()
    target = keep / "a.dcd"
    payload = b"sync-size"
    target.write_bytes(payload)
    Scope(repo).add(keep)
    run_add(repo, quiet=True)
    push_jobs = collect_sync_jobs(plan_sync(repo))
    assert [job.size for job in push_jobs] == [len(payload)]
    assert [job.path for job in push_jobs] == ["keep/a.dcd"]

    run_push(repo, dry_run=False)
    assert collect_sync_jobs(plan_sync(repo)) == []
    target.unlink()
    pull_jobs = collect_sync_jobs(plan_sync(repo))
    assert [job.size for job in pull_jobs] == [len(payload)]
    assert [job.path for job in pull_jobs] == ["keep/a.dcd"]
