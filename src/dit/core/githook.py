"""旧 Git hook の移行補助."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

HOOK_MARKER = "# managed by dit"
HOOK_NAME = "pre-commit"


def hooks_dir(repo_root: Path) -> Path:
    """リポジトリの git hooks ディレクトリを返す."""
    git = shutil.which("git")
    if git is not None:
        try:
            result = subprocess.run(  # noqa: S603  # fixed argv: absolute git + fixed args
                [git, "rev-parse", "--git-path", "hooks"],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
        else:
            value = result.stdout.strip()
            if result.returncode == 0 and value:
                path = Path(value)
                return path if path.is_absolute() else repo_root / path
    return repo_root / ".git" / "hooks"


def hook_path(repo_root: Path) -> Path:
    """旧 dit 管理の pre-commit hook のパスを返す."""
    return hooks_dir(repo_root) / HOOK_NAME


def legacy_hook_paths(repo_root: Path) -> tuple[Path, Path]:
    """旧 hook と pre-commit の退避 hook のパスを返す."""
    path = hook_path(repo_root)
    return path, path.with_name(f"{HOOK_NAME}.legacy")


def remove_managed_hooks(repo_root: Path) -> bool:
    """旧 dit 管理の hook だけを削除する."""
    removed = False
    for path in legacy_hook_paths(repo_root):
        if path.exists() and HOOK_MARKER in path.read_text(encoding="utf-8"):
            path.unlink()
            removed = True
    return removed


def hook_status(repo_root: Path) -> str:
    """旧 hook の状態（missing / installed / unmanaged）を返す."""
    unmanaged = False
    for path in legacy_hook_paths(repo_root):
        if not path.exists():
            continue
        if HOOK_MARKER in path.read_text(encoding="utf-8"):
            return "installed"
        unmanaged = True
    return "unmanaged" if unmanaged else "missing"
