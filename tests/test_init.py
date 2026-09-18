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
    config = worktree / ".pre-commit-config.yaml"
    assert config.is_file()
    assert "repo: local" in config.read_text(encoding="utf-8")
    assert "id: dit" in config.read_text(encoding="utf-8")


def test_init_preserves_existing_pre_commit_config(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    init_config(bucket="bucket", prefix="prefix").save(repo / "dit.toml")
    config = repo / ".pre-commit-config.yaml"
    existing = (
        "repos:\n"
        "  - repo: https://github.com/pre-commit/pre-commit-hooks\n"
        "    rev: v5.0.0\n"
        "    hooks:\n"
        "      - id: trailing-whitespace\n"
    )
    config.write_text(existing, encoding="utf-8")
    monkeypatch.chdir(repo)

    result = CliRunner().invoke(init_cmd, [], catch_exceptions=False)

    assert result.exit_code == 0
    updated = config.read_text(encoding="utf-8")
    assert updated.startswith(existing)
    assert updated.count("id: dit\n") == 1

    result = CliRunner().invoke(init_cmd, [], catch_exceptions=False)

    assert result.exit_code == 0
    assert config.read_text(encoding="utf-8") == updated


def test_init_removes_legacy_dit_hook(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    init_config(bucket="bucket", prefix="prefix").save(repo / "dit.toml")
    legacy = hook_path(repo)
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text("#!/bin/sh\n# managed by dit\n", encoding="utf-8")
    monkeypatch.chdir(repo)

    result = CliRunner().invoke(init_cmd, [], catch_exceptions=False)

    assert result.exit_code == 0
    assert not legacy.exists()


def test_init_removes_legacy_dit_hook_saved_by_pre_commit(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    init_config(bucket="bucket", prefix="prefix").save(repo / "dit.toml")
    current = hook_path(repo)
    current.parent.mkdir(parents=True, exist_ok=True)
    current.write_text("#!/bin/sh\n# managed by pre-commit\n", encoding="utf-8")
    legacy = current.with_name("pre-commit.legacy")
    legacy.write_text("#!/bin/sh\n# managed by dit\n", encoding="utf-8")
    monkeypatch.chdir(repo)

    result = CliRunner().invoke(init_cmd, [], catch_exceptions=False)

    assert result.exit_code == 0
    assert current.exists()
    assert not legacy.exists()
