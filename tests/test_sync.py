from __future__ import annotations

from typing import TYPE_CHECKING

import boto3
import pytest
from moto import mock_aws

from dit.core.add_service import run_add
from dit.core.config import init_config
from dit.core.repo import Repo
from dit.core.scope import Scope
from dit.core.sync_service import SyncAction, run_sync

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


@mock_aws
def test_sync_push_and_scope_delete(tmp_path: Path) -> None:
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")
    repo = _init_repo(tmp_path)
    data = repo.root / "keep"
    data.mkdir()
    target = data / "a.dcd"
    target.write_bytes(b"payload")
    run_add(repo, quiet=True)
    Scope(repo).add(data)

    results = run_sync(repo, dry_run=False, prune_remote=False)
    actions = {r.action for r in results}
    assert SyncAction.PUSH in actions or SyncAction.OK in actions

    Scope(repo).remove(data)
    results = run_sync(repo, dry_run=False, prune_remote=False)
    assert any(r.action == SyncAction.DELETE_LOCAL for r in results)
    assert not target.exists()
    assert (repo.root / "keep" / "a.dcd.dit").is_file()
