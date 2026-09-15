from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

from click.testing import CliRunner

from dit.command.init import init_cmd
from dit.core.config import init_config
from dit.core.githook import hook_path

if TYPE_CHECKING:
    from pathlib import Path


def _git(directory: Path, *args: str) -> None:
    subprocess.run(  # noqa: S603  # fixed git executable and test-only arguments
        ["git", "-C", str(directory), *args],  # noqa: S607
        check=True,
        capture_output=True,
    )


def test_init_reads_committed_config_in_worktree(tmp_path: Path, monkeypatch) -> None:
    main = tmp_path / "main"
    main.mkdir()
    _git(main, "init", "-q")
    _git(main, "config", "user.email", "test@example.com")
    _git(main, "config", "user.name", "Test")
    init_config(bucket="bucket", prefix="prefix").save(main / "dit.toml")
    _git(main, "add", "dit.toml")
    _git(main, "commit", "-qm", "config")

    worktree = tmp_path / "worktree"
    _git(main, "worktree", "add", "-q", str(worktree))
    monkeypatch.chdir(worktree)

    result = CliRunner().invoke(init_cmd, [], catch_exceptions=False)

    assert result.exit_code == 0
    assert (worktree / ".dit" / ".gitignore").is_file()
    assert hook_path(worktree).is_file()
