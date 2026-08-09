from __future__ import annotations

from typing import TYPE_CHECKING

import boto3
import pytest
from moto import mock_aws

from dit.core.add_service import run_add
from dit.core.config import init_config
from dit.core.pointer import Pointer, read_pointer, write_pointer
from dit.core.repo import Repo
from dit.core.scope import Scope
from dit.core.sync_service import SyncAction, run_push, run_sync

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def dit_remote_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIT_ACCESS_KEY", "testing")
    monkeypatch.setenv("DIT_SECRET_KEY", "testing")
    monkeypatch.setenv("DIT_ENDPOINT_URL", "https://s3.amazonaws.com")


def _init_repo(tmp_path: Path) -> Repo:
    root = tmp_path / "proj"
    root.mkdir()
    (root / ".git").mkdir()
    (root / ".dit").mkdir()
    (root / ".dit" / ".gitignore").write_text("*\n", encoding="utf-8")
    config = init_config(bucket="test-bucket", prefix="md")
    config.save(root / "dit.toml")
    return Repo(root=root)


def _write_tracked(repo: Repo, rel_dir: str, name: str, payload: bytes) -> Path:
    directory = repo.root / rel_dir
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / name
    target.write_bytes(payload)
    return target


@mock_aws
def test_sync_pushes_in_scope(tmp_path: Path) -> None:
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")
    repo = _init_repo(tmp_path)
    target = _write_tracked(repo, "keep", "a.dcd", b"payload")
    Scope(repo).add(repo.root / "keep")
    assert run_add(repo, quiet=True) == 1

    results = run_sync(repo, dry_run=False, prune_remote=False)
    actions = {r.action for r in results}
    assert SyncAction.PUSH in actions or SyncAction.OK in actions
    assert target.is_file()
    assert (repo.root / "keep" / "a.dcd.dit").is_file()


@mock_aws
def test_sync_ignores_out_of_scope(tmp_path: Path) -> None:
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")
    repo = _init_repo(tmp_path)
    target = _write_tracked(repo, "other", "a.dcd", b"payload")
    write_pointer(
        repo.root,
        Pointer(path="other/a.dcd", hash="0" * 64, size=len(b"payload")),
    )

    results = run_sync(repo, dry_run=False, prune_remote=False)
    assert results == []
    assert target.is_file()
    assert run_push(repo, dry_run=False) == []


def test_add_only_updates_in_scope(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    in_scope = _write_tracked(repo, "keep", "a.dcd", b"in")
    out_scope = _write_tracked(repo, "other", "b.dcd", b"out")
    Scope(repo).add(repo.root / "keep")

    assert run_add(repo, quiet=True) == 1
    assert (in_scope.parent / "a.dcd.dit").is_file()
    assert not (out_scope.parent / "b.dcd.dit").is_file()


@mock_aws
def test_push_skips_out_of_scope(tmp_path: Path) -> None:
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")
    repo = _init_repo(tmp_path)
    target = _write_tracked(repo, "keep", "a.dcd", b"payload")
    Scope(repo).add(repo.root / "keep")
    run_add(repo, quiet=True)
    Scope(repo).remove(repo.root / "keep")

    assert run_push(repo, dry_run=False) == []
    assert target.is_file()
    assert read_pointer(repo.root / "keep" / "a.dcd.dit").path == "keep/a.dcd"
