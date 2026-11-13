from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING
from unittest.mock import patch

from click.testing import CliRunner

from dit.core.add_service import run_add
from dit.core.config import init_config
from dit.core.repo import Repo
from dit.main import cli

if TYPE_CHECKING:
    from pathlib import Path


def git(root: Path, *args: str) -> bytes:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True).stdout  # noqa: S603, S607


def test_add_stages_only_changed_pointers_in_one_git_call(tmp_path: Path) -> None:
    git(tmp_path, "init", "-q")
    (tmp_path / ".dit").mkdir()
    init_config(bucket="test", prefix="test").save(tmp_path / "dit.toml")
    repo = Repo(root=tmp_path)
    names = ["old.dcd", "change.dcd", "space name.dcd", "line\nbreak.dcd", ":(glob)*.dcd"]
    for name in names[:2]:
        (tmp_path / name).write_bytes(b"original")
    assert run_add(repo, quiet=True) == 2
    git(
        tmp_path,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.com",
        "commit",
        "-qm",
        "initial",
    )
    (tmp_path / names[0]).unlink()
    (tmp_path / names[1]).write_bytes(b"updated content")
    for name in names[2:]:
        (tmp_path / name).write_bytes(b"new")
    (tmp_path / "staged.txt").write_text("staged")
    git(tmp_path, "add", "staged.txt")
    (tmp_path / "staged.txt").write_text("unstaged")
    (tmp_path / "unrelated.txt").write_text("untracked")
    original_run = subprocess.run
    with patch("dit.core.add_service.subprocess.run", wraps=original_run) as invoke:
        assert run_add(repo, quiet=True, prune=True) == len(names)
        assert invoke.call_count == 1
        assert run_add(repo, quiet=True, prune=True) == 0
        assert invoke.call_count == 1
    staged = set(git(tmp_path, "diff", "--cached", "--name-only", "-z").decode().split("\0")) - {""}
    assert staged == {f"{name}.dit" for name in names} | {"staged.txt"}
    assert git(tmp_path, "show", ":staged.txt") == b"staged"
    assert (tmp_path / "staged.txt").read_text() == "unstaged"


def test_add_reports_git_failure(tmp_path: Path, monkeypatch) -> None:
    git(tmp_path, "init", "-q")
    (tmp_path / ".dit").mkdir()
    init_config(bucket="test", prefix="test").save(tmp_path / "dit.toml")
    (tmp_path / "file.dcd").write_bytes(b"payload")
    (tmp_path / ".git" / "index.lock").write_text("locked")
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(cli, ["add", "--quiet"])

    assert result.exit_code != 0
    assert "git add failed" in result.output
    assert "index.lock" in result.output
