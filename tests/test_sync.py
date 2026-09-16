from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from unittest.mock import Mock

import boto3
import pytest
from click.testing import CliRunner
from moto import mock_aws

from dit.core.add_service import run_add
from dit.core.config import init_config
from dit.core.pointer import Pointer, read_pointer, write_pointer
from dit.core.repo import Repo
from dit.core.scope import Scope
from dit.core.sync_service import SyncAction, run_pull, run_push, run_sync
from dit.main import cli

if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class _ProgressCapture:
    amounts: list[int] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)

    def add_bytes(self, amount: int) -> None:
        self.amounts.append(amount)

    def set_path(self, path: str) -> None:
        self.paths.append(path)


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


@pytest.mark.parametrize("command", ["push", "pull", "sync"])
@pytest.mark.parametrize("existing_env", [False, True])
def test_transfer_loads_root_dotenv(tmp_path: Path, monkeypatch, command, existing_env) -> None:
    repo = _init_repo(tmp_path)
    (repo.root / ".env").write_text(
        'export DIT_ACCESS_KEY="file-access"\n'
        "DIT_SECRET_KEY='file-secret # literal'\n"
        "DIT_ENDPOINT_URL=https://storage.example.com # endpoint\n",
        encoding="utf-8",
    )
    nested = repo.root / "nested"
    nested.mkdir()
    (nested / ".env").write_text("DIT_ACCESS_KEY=wrong-directory\n", encoding="utf-8")
    monkeypatch.chdir(nested)
    monkeypatch.delenv("DIT_SECRET_KEY")
    monkeypatch.delenv("DIT_ENDPOINT_URL")
    if not existing_env:
        monkeypatch.delenv("DIT_ACCESS_KEY")
    client = Mock()
    monkeypatch.setattr(boto3, "client", client)

    result = CliRunner().invoke(cli, [command, "--dry-run"], catch_exceptions=False)

    assert result.exit_code == 0
    client.assert_called()
    for call in client.call_args_list:
        assert call.args == ("s3",)
        kwargs = call.kwargs
        assert kwargs["aws_access_key_id"] == ("testing" if existing_env else "file-access")
        assert kwargs["aws_secret_access_key"] == "file-secret # literal"  # noqa: S105 — test credential
        assert kwargs["endpoint_url"] == "https://storage.example.com"


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


@mock_aws
def test_pull_downloads_missing_in_scope(tmp_path: Path) -> None:
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")
    repo = _init_repo(tmp_path)
    target = _write_tracked(repo, "keep", "a.dcd", b"payload")
    Scope(repo).add(repo.root / "keep")
    run_add(repo, quiet=True)
    run_push(repo, dry_run=False)
    target.unlink()
    progress = _ProgressCapture()

    results = run_pull(repo, progress=progress)

    assert [result.action for result in results] == [SyncAction.PULL]
    assert target.read_bytes() == b"payload"
    assert progress.paths == ["keep/a.dcd"]
    assert sum(progress.amounts) == len(b"payload")


@mock_aws
def test_push_reports_completed_uploads(tmp_path: Path) -> None:
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")
    repo = _init_repo(tmp_path)
    _write_tracked(repo, "keep", "a.dcd", b"payload")
    Scope(repo).add(repo.root / "keep")
    run_add(repo, quiet=True)
    progress = _ProgressCapture()

    run_push(repo, progress=progress)

    assert progress.paths == ["keep/a.dcd"]
    assert sum(progress.amounts) == len(b"payload")


@mock_aws
def test_sync_reports_push_progress(tmp_path: Path) -> None:
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")
    repo = _init_repo(tmp_path)
    _write_tracked(repo, "keep", "a.dcd", b"payload")
    Scope(repo).add(repo.root / "keep")
    run_add(repo, quiet=True)
    progress = _ProgressCapture()

    results = run_sync(repo, progress=progress)

    assert SyncAction.PUSH in {result.action for result in results}
    assert progress.paths == ["keep/a.dcd"]
    assert sum(progress.amounts) == len(b"payload")


@mock_aws
def test_sync_reports_pull_progress(tmp_path: Path) -> None:
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")
    repo = _init_repo(tmp_path)
    target = _write_tracked(repo, "keep", "a.dcd", b"payload")
    Scope(repo).add(repo.root / "keep")
    run_add(repo, quiet=True)
    run_push(repo, dry_run=False)
    target.unlink()
    progress = _ProgressCapture()

    results = run_sync(repo, progress=progress)

    assert [result.action for result in results] == [SyncAction.PULL]
    assert target.read_bytes() == b"payload"
    assert progress.paths == ["keep/a.dcd"]
    assert sum(progress.amounts) == len(b"payload")


@mock_aws
def test_sync_reports_combined_push_and_pull_progress(tmp_path: Path) -> None:
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")
    repo = _init_repo(tmp_path)
    existing = _write_tracked(repo, "keep", "a.dcd", b"aaa-payload")
    Scope(repo).add(repo.root / "keep")
    run_add(repo, quiet=True)
    run_push(repo, dry_run=False)
    existing.unlink()
    _write_tracked(repo, "keep", "b.dcd", b"bbb-payload")
    run_add(repo, quiet=True)
    progress = _ProgressCapture()

    results = run_sync(repo, progress=progress)

    actions = {result.action for result in results}
    assert SyncAction.PULL in actions
    assert SyncAction.PUSH in actions
    assert sorted(progress.paths) == ["keep/a.dcd", "keep/b.dcd"]
    assert sum(progress.amounts) == len(b"aaa-payload") + len(b"bbb-payload")
