from __future__ import annotations

import sqlite3
import subprocess
from typing import TYPE_CHECKING

import pytest

from dit.core import add_service
from dit.core.config import init_config
from dit.core.errors import RepoError
from dit.core.hasher import hash_file
from dit.core.index import StatIndex
from dit.core.pointer import read_pointer
from dit.core.repo import Repo

if TYPE_CHECKING:
    from pathlib import Path


def _repo(tmp_path: Path) -> Repo:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)  # noqa: S603, S607
    (tmp_path / ".dit").mkdir()
    init_config(bucket="test", prefix="test").save(tmp_path / "dit.toml")
    return Repo(root=tmp_path)


def _assert_consistent(repo: Repo, files: list[Path]) -> None:
    with StatIndex(repo.index_db) as index:
        for path in files:
            pointer = path.with_name(path.name + ".dit")
            entry = index.get(repo.rel(path))
            assert entry is not None
            assert entry.hash == hash_file(path)
            assert read_pointer(pointer).hash == entry.hash
            staged = subprocess.run(  # noqa: S603
                ["git", "show", f":{repo.rel(pointer)}"],  # noqa: S607
                cwd=repo.root,
                check=True,
                capture_output=True,
            ).stdout
            assert staged == pointer.read_bytes()


def test_add_commits_once_after_multiple_updates(tmp_path: Path, monkeypatch) -> None:
    repo = _repo(tmp_path)
    files = [repo.root / f"{i}.dcd" for i in range(3)]
    for path in files:
        path.write_bytes(b"old")
    add_service.run_add(repo, quiet=True)
    for path in files:
        path.write_bytes(b"new content")
    original_connect = sqlite3.connect
    commits = []

    class Connection(sqlite3.Connection):
        def commit(self):
            commits.append(self.in_transaction)
            return super().commit()

    monkeypatch.setattr(
        sqlite3, "connect", lambda *a, **kw: original_connect(*a, factory=Connection, **kw)
    )
    add_service.run_add(repo, quiet=True)
    assert commits == [False, True]  # schema setup, then the batch
    _assert_consistent(repo, files)


@pytest.mark.parametrize("failure", ["stage", "commit"])
def test_add_recovers_after_failure(tmp_path: Path, monkeypatch, failure: str) -> None:
    repo = _repo(tmp_path)
    files = [repo.root / f"{i}.dcd" for i in range(3)]
    for path in files:
        path.write_bytes(b"payload")
    original_connect = sqlite3.connect
    original_git_add = add_service._git_add
    calls = 0

    class Connection(sqlite3.Connection):
        def commit(self):
            if failure == "commit" and self.in_transaction:
                msg = "injected commit failure"
                raise sqlite3.OperationalError(msg)
            return super().commit()

    def fail_stage(repo, path):
        nonlocal calls
        calls += 1
        if failure == "stage" and calls == 2:
            msg = "injected stage failure"
            raise RuntimeError(msg)
        original_git_add(repo, path)

    with monkeypatch.context() as patch:
        patch.setattr(
            sqlite3, "connect", lambda *a, **kw: original_connect(*a, factory=Connection, **kw)
        )
        patch.setattr(add_service, "_git_add", fail_stage)
        with pytest.raises((RuntimeError, sqlite3.OperationalError)):
            add_service.run_add(repo, quiet=True)
    with StatIndex(repo.index_db) as index:
        assert index.all_entries() == []
    add_service.run_add(repo, quiet=True)
    _assert_consistent(repo, files)


def test_add_rolls_back_when_git_fails(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    data = repo.root / "a.dcd"
    data.write_bytes(b"payload")
    lock = repo.root / ".git" / "index.lock"
    lock.touch()
    with pytest.raises(RepoError, match="git add failed"):
        add_service.run_add(repo, quiet=True)
    with StatIndex(repo.index_db) as index:
        assert index.all_entries() == []
    lock.unlink()
    add_service.run_add(repo, quiet=True)
    _assert_consistent(repo, [data])


def test_prune_recovers_if_staging_deletion_fails(tmp_path: Path, monkeypatch) -> None:
    repo = _repo(tmp_path)
    data = repo.root / "a.dcd"
    data.write_bytes(b"payload")
    add_service.run_add(repo, quiet=True)
    data.unlink()
    lock = repo.root / ".git" / "index.lock"
    lock.touch()
    with pytest.raises(RepoError, match="git add failed"):
        add_service.run_add(repo, quiet=True, prune=True)
    lock.unlink()
    add_service.run_add(repo, quiet=True, prune=True)
    result = subprocess.run(
        ["git", "ls-files", "--", "a.dcd.dit"],  # noqa: S607
        cwd=repo.root,
        check=True,
        capture_output=True,
    )
    assert result.stdout == b""


def test_prune_removes_untracked_pointer(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    data = repo.root / "a.dcd"
    data.write_bytes(b"payload")
    add_service.run_add(repo, quiet=True)
    subprocess.run(["git", "rm", "--cached", "-q", "a.dcd.dit"], cwd=repo.root, check=True)  # noqa: S607
    data.unlink()
    assert add_service.run_add(repo, quiet=True, prune=True) == 1
    assert not (repo.root / "a.dcd.dit").exists()
