from __future__ import annotations

import subprocess
import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from unittest.mock import Mock

import boto3
import pytest
from click.testing import CliRunner
from moto import mock_aws

from dit.core.add_service import _git_add as real_git_add, run_add
from dit.core.config import DitConfig, RemoteConfig, init_config
from dit.core.errors import RemoteError
from dit.core.hasher import hash_file
from dit.core.pointer import Pointer, read_pointer, write_pointer
from dit.core.remote.s3 import S3Remote
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
    monkeypatch.delenv("DIT_TRANSFER_CONCURRENCY", raising=False)


def _init_repo(tmp_path: Path) -> Repo:
    root = tmp_path / "proj"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)  # noqa: S603, S607
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


@pytest.mark.parametrize("command", ["push", "pull", "sync"])
@pytest.mark.parametrize("existing_env", [None, "8"])
def test_transfer_concurrency_loads_root_dotenv(
    tmp_path: Path, monkeypatch, command, existing_env
) -> None:
    repo = _init_repo(tmp_path)
    (repo.root / ".env").write_text("DIT_TRANSFER_CONCURRENCY=24\n", encoding="utf-8")
    if existing_env is not None:
        monkeypatch.setenv("DIT_TRANSFER_CONCURRENCY", existing_env)
    monkeypatch.chdir(repo.root)
    client = Mock()
    monkeypatch.setattr(boto3, "client", client)

    result = CliRunner().invoke(cli, [command, "--dry-run"], catch_exceptions=False)

    assert result.exit_code == 0
    client.assert_called()
    for call in client.call_args_list:
        assert call.kwargs["config"].max_pool_connections == int(existing_env or "24")


@pytest.mark.parametrize("command", ["push", "pull", "sync"])
def test_transfer_rejects_invalid_concurrency(tmp_path: Path, monkeypatch, command) -> None:
    repo = _init_repo(tmp_path)
    monkeypatch.chdir(repo.root)
    monkeypatch.setenv("DIT_TRANSFER_CONCURRENCY", "0")

    result = CliRunner().invoke(cli, [command], catch_exceptions=False)

    assert result.exit_code == 1
    assert "Error: DIT_TRANSFER_CONCURRENCY must be a positive integer" in result.output


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
    (repo.root / "keep").mkdir()
    Scope(repo).add(repo.root / "keep")
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


@pytest.mark.parametrize("prune", [False, True])
def test_add_symlink_reuses_target_pointer(tmp_path: Path, monkeypatch, *, prune: bool) -> None:
    repo = _init_repo(tmp_path)
    target = _write_tracked(repo, "fitted_string_20ps", "image_1.rst", b"restart")
    assert run_add(repo, quiet=True) == 1
    pointer_path = target.parent / "image_1.rst.dit"
    pointer_bytes = pointer_path.read_bytes()
    pointer_mtime = pointer_path.stat().st_mtime_ns
    starting = repo.root / "starting"
    starting.mkdir()
    link = starting / "image_1.rst"
    link.symlink_to("../fitted_string_20ps/image_1.rst")
    git_add = Mock()
    monkeypatch.setattr("dit.core.add_service._git_add", git_add)

    assert run_add(repo, quiet=True, prune=prune) == 0
    assert run_add(repo, quiet=True, prune=prune) == 0

    git_add.assert_not_called()
    assert pointer_path.read_bytes() == pointer_bytes
    assert pointer_path.stat().st_mtime_ns == pointer_mtime
    assert link.is_symlink()
    assert not (starting / "image_1.rst.dit").exists()
    assert not (starting / ".gitignore").exists()


@pytest.mark.parametrize("patterns", [["*.rst"], ["starting/*.rst"]])
def test_add_symlinks_create_and_update_target_once(tmp_path: Path, monkeypatch, patterns) -> None:
    repo = _init_repo(tmp_path)
    DitConfig(track_patterns=patterns).save(repo.dit_toml)
    target = _write_tracked(repo, "fitted_string_20ps", "image_1.rst", b"restart")
    starting = repo.root / "starting"
    starting.mkdir()
    links = [starting / name for name in ("absolute.rst", "relative.rst", "chained.rst")]
    links[0].symlink_to(target)
    links[1].symlink_to("../fitted_string_20ps/image_1.rst")
    links[2].symlink_to(links[1].name)
    pointer_path = target.parent / "image_1.rst.dit"
    git_add = Mock(wraps=real_git_add)
    monkeypatch.setattr("dit.core.add_service._git_add", git_add)

    for payload in (b"restart", b"updated restart"):
        target.write_bytes(payload)
        git_add.reset_mock()

        assert run_add(repo, quiet=True, prune=True) == 1
        assert run_add(repo, quiet=True, prune=True) == 0

        git_add.assert_called_once_with(repo, [pointer_path])
        assert read_pointer(pointer_path) == Pointer(
            path="fitted_string_20ps/image_1.rst", hash=hash_file(target), size=len(payload)
        )
        assert all(link.is_symlink() and link.read_bytes() == payload for link in links)

    assert (target.parent / ".gitignore").read_text(encoding="utf-8") == "image_1.rst\n"
    assert not (starting / ".gitignore").exists()
    assert list(starting.glob("*.dit")) == []


@mock_aws
def test_push_skips_out_of_scope(tmp_path: Path) -> None:
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")
    repo = _init_repo(tmp_path)
    target = _write_tracked(repo, "keep", "a.dcd", b"payload")
    Scope(repo).add(repo.root / "keep")
    run_add(repo, quiet=True)
    Scope(repo).remove(repo.root / "keep")
    (repo.root / "other").mkdir()
    Scope(repo).add(repo.root / "other")

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


@mock_aws
@pytest.mark.parametrize("run", [run_pull, run_sync])
def test_downloads_run_concurrently_in_scope(tmp_path: Path, monkeypatch, run) -> None:
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket="test-bucket")
    repo = _init_repo(tmp_path)
    (repo.root / "keep").mkdir()
    Scope(repo).add(repo.root / "keep")
    remote = S3Remote(RemoteConfig(bucket="test-bucket", prefix="md"))
    monkeypatch.setattr("dit.core.sync_service.require_remote", lambda config: remote)
    paths = ["keep/a.dcd", "keep/b.dcd", "other/c.dcd"]
    for i, path in enumerate(paths):
        content_hash = f"blake3:{i:064x}"
        payload = bytes([i]) * 1024
        client.put_object(Bucket="test-bucket", Key=remote.object_key(content_hash), Body=payload)
        write_pointer(repo.root, Pointer(path=path, hash=content_hash, size=len(payload)))
    barrier = threading.Barrier(2)

    def wait_for_other_file(**kwargs):
        barrier.wait(timeout=5)

    remote._client.meta.events.register("before-call.s3.GetObject", wait_for_other_file)
    progress = _ProgressCapture()

    results = run(repo, progress=progress)

    assert [result.path for result in results] == paths[:2]
    assert all(result.action == SyncAction.PULL for result in results)
    assert sorted(progress.paths) == paths[:2]
    assert sum(progress.amounts) == 2048
    assert (repo.root / paths[0]).read_bytes() == b"\0" * 1024
    assert (repo.root / paths[1]).read_bytes() == b"\1" * 1024
    assert not (repo.root / paths[2]).exists()


@mock_aws
@pytest.mark.parametrize("run", [run_pull, run_sync])
def test_download_dry_run_does_not_start_transfers(tmp_path: Path, monkeypatch, run):
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket="test-bucket")
    repo = _init_repo(tmp_path)
    remote = S3Remote(RemoteConfig(bucket="test-bucket", prefix="md"))
    monkeypatch.setattr("dit.core.sync_service.require_remote", lambda config: remote)
    for i in range(2):
        content_hash = f"blake3:{i:064x}"
        client.put_object(Bucket="test-bucket", Key=remote.object_key(content_hash), Body=b"data")
        write_pointer(repo.root, Pointer(path=f"{i}.dcd", hash=content_hash, size=4))
    download_many = Mock(side_effect=AssertionError("dry-run must not download"))
    monkeypatch.setattr(remote, "download_many", download_many)

    results = run(repo, dry_run=True)

    assert [result.path for result in results] == ["0.dcd", "1.dcd"]
    assert not list(repo.root.glob("*.dcd"))
    download_many.assert_not_called()


@mock_aws
def test_sync_waits_for_downloads_before_later_push(tmp_path: Path, monkeypatch):
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket="test-bucket")
    repo = _init_repo(tmp_path)
    remote = S3Remote(RemoteConfig(bucket="test-bucket", prefix="md"))
    monkeypatch.setattr("dit.core.sync_service.require_remote", lambda config: remote)
    client.put_object(Bucket="test-bucket", Key=remote.object_key("blake3:aaa"), Body=b"pull")
    write_pointer(repo.root, Pointer(path="a.dcd", hash="blake3:aaa", size=4))
    _write_tracked(repo, "", "b.dcd", b"push")
    run_add(repo, quiet=True)
    downloads = Mock(side_effect=RemoteError("download failed"))
    uploads = Mock()
    monkeypatch.setattr(remote, "download_many", downloads)
    monkeypatch.setattr(remote, "upload", uploads)

    with pytest.raises(RemoteError, match="download failed"):
        run_sync(repo)

    downloads.assert_called_once()
    uploads.assert_not_called()
