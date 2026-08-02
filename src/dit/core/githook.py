"""Git hook install and status helpers."""

from __future__ import annotations

import shutil
import stat
import subprocess
from importlib import resources
from pathlib import Path

from dit.core.errors import HookError

HOOK_MARKER = "# managed by dit"
HOOK_NAME = "pre-commit"


def hooks_dir(repo_root: Path) -> Path:
    """Return the git hooks directory for a repository."""
    configured = _git_config_value(repo_root, "core.hooksPath")
    if configured:
        path = Path(configured)
        if not path.is_absolute():
            path = repo_root / path
        return path
    return repo_root / ".git" / "hooks"


def hook_path(repo_root: Path) -> Path:
    """Return the path of the dit-managed pre-commit hook."""
    return hooks_dir(repo_root) / HOOK_NAME


def render_hook_script() -> str:
    """Return the pre-commit hook script body."""
    try:
        template = resources.files("dit.hooks").joinpath(HOOK_NAME).read_text(encoding="utf-8")
    except (FileNotFoundError, TypeError, AttributeError):
        return (
            "#!/bin/sh\n"
            f"{HOOK_MARKER}\n"
            'command -v dit >/dev/null 2>&1 || { echo "dit: not found in PATH" >&2; exit 1; }\n'
            "exec dit add --quiet\n"
        )
    else:
        return template


def install_hook(repo_root: Path, *, force: bool = False) -> Path:
    """Install the dit-managed pre-commit hook."""
    path = hook_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        content = path.read_text(encoding="utf-8")
        if HOOK_MARKER not in content:
            msg = (
                f"existing hook at {path} is not managed by dit; "
                "merge manually or re-run with --force"
            )
            raise HookError(msg)
    path.write_text(render_hook_script(), encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def uninstall_hook(repo_root: Path) -> bool:
    """Remove the dit-managed pre-commit hook if present."""
    path = hook_path(repo_root)
    if not path.exists():
        return False
    content = path.read_text(encoding="utf-8")
    if HOOK_MARKER not in content:
        msg = f"refusing to remove unmanaged hook: {path}"
        raise HookError(msg)
    path.unlink()
    return True


def hook_status(repo_root: Path) -> str:
    """Return hook status: missing, installed, or unmanaged."""
    path = hook_path(repo_root)
    if not path.exists():
        return "missing"
    content = path.read_text(encoding="utf-8")
    if HOOK_MARKER in content:
        return "installed"
    return "unmanaged"


def _git_config_value(repo_root: Path, key: str) -> str | None:
    git = shutil.which("git")
    if git is None:
        return None
    try:
        result = subprocess.run(  # noqa: S603  # fixed argv: absolute git + config get
            [git, "config", "--get", key],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    value = result.stdout.strip()
    return value or None
