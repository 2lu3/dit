from __future__ import annotations

from typing import TYPE_CHECKING

import boto3
import pytest
from moto import mock_aws

from dit.core.config import DitConfig, RemoteConfig, default_init_config
from dit.core.hasher import hash_file
from dit.core.index import IndexEntry, StatIndex, file_stat_tuple, stats_match
from dit.core.pointer import Pointer, read_pointer, write_pointer
from dit.core.remote.s3 import S3Remote
from dit.core.repo import Repo
from dit.core.scope import Scope
from dit.core.tracker import build_track_spec, is_tracked_path, iter_tracked_files

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def git_repo(tmp_path: Path) -> Repo:
    root = tmp_path / "proj"
    root.mkdir()
    (root / ".git").mkdir()
    (root / ".dit").mkdir()
    config = default_init_config(
        remote_url="s3://test-bucket/md",
        endpoint_url=None,
    )
    config.save(root / "dit.toml")
    return Repo(root=root)


def test_hash_file_stable(tmp_path: Path) -> None:
    path = tmp_path / "a.dcd"
    path.write_bytes(b"abc" * 1000)
    assert hash_file(path) == hash_file(path)
    assert hash_file(path).startswith("blake3:")


def test_stat_index_skips_rehash(tmp_path: Path) -> None:
    db = tmp_path / "index.db"
    path = tmp_path / "f.dcd"
    path.write_bytes(b"data")
    size, mtime_ns, inode = file_stat_tuple(path)
    with StatIndex(db) as index:
        index.upsert(IndexEntry("f.dcd", size, mtime_ns, inode, "blake3:dead", None))
        entry = index.get("f.dcd")
        assert entry is not None
        assert stats_match(entry, size, mtime_ns, inode)


def test_track_patterns_extension_and_dir() -> None:
    spec = build_track_spec(["*.dcd", "data/**/out/", "!data/00_scratch/"])
    assert is_tracked_path("foo.dcd", is_dir=False, track_spec=spec)
    assert is_tracked_path("data/01/out/a.bin", is_dir=False, track_spec=spec)
    assert not is_tracked_path("data/00_scratch/x.dcd", is_dir=False, track_spec=spec)


def test_iter_tracked_files(git_repo: Repo) -> None:
    (git_repo.root / "traj.dcd").write_bytes(b"1")
    (git_repo.root / "note.txt").write_text("x", encoding="utf-8")
    out = git_repo.root / "data" / "01" / "out"
    out.mkdir(parents=True)
    (out / "x.bin").write_bytes(b"2")
    config = DitConfig.load(git_repo.dit_toml)
    config = DitConfig(
        remote=config.remote,
        track_patterns=["*.dcd", "data/**/out/", "!data/00_scratch/"],
    )
    files = [git_repo.rel(p) for p in iter_tracked_files(git_repo, config)]
    assert "traj.dcd" in files
    assert "data/01/out/x.bin" in files
    assert "note.txt" not in files


def test_pointer_roundtrip(git_repo: Repo) -> None:
    pointer = Pointer(path="traj.dcd", hash="blake3:abc", size=3)
    path = write_pointer(git_repo.root, pointer)
    loaded = read_pointer(path)
    assert loaded == pointer


def test_scope_contains(git_repo: Repo) -> None:
    target = git_repo.root / "data" / "07_production"
    target.mkdir(parents=True)
    scope = Scope(git_repo)
    scope.add(target)
    assert scope.contains("data/07_production/a.dcd")
    assert not scope.contains("data/01_min/a.dcd")


@mock_aws
def test_s3_remote_upload_download(tmp_path: Path) -> None:
    bucket = "test-bucket"
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket=bucket)
    remote = S3Remote(RemoteConfig(url="s3://test-bucket/md"))
    local = tmp_path / "a.dcd"
    local.write_bytes(b"hello-md")
    digest = hash_file(local)
    assert not remote.exists(digest)
    remote.upload(local, digest)
    assert remote.exists(digest)
    out = tmp_path / "b.dcd"
    remote.download(digest, out)
    assert out.read_bytes() == b"hello-md"
    assert digest in remote.list_hashes()
