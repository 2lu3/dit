"""pre-commit 設定の更新."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from dit.core.githook import (
    hook_status as legacy_hook_status,
    remove_managed_hooks as remove_legacy_hooks,
)

if TYPE_CHECKING:
    from pathlib import Path

CONFIG_NAME = ".pre-commit-config.yaml"
HOOK_ID = "dit"
HOOK_MARKER = "# managed by dit"


def config_path(repo_root: Path) -> Path:
    """pre-commit 設定ファイルのパスを返す."""
    return repo_root / CONFIG_NAME


def install_hook(repo_root: Path) -> Path:
    """pre-commit 設定に dit hook を追加する."""
    path = config_path(repo_root)
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    if _has_dit_hook(text):
        _remove_legacy_hook(repo_root)
        return path

    block = _render_hook_block(text)
    repos_line = _repos_line(text)
    if repos_line is None:
        prefix = text
        if prefix and not prefix.endswith("\n"):
            prefix += "\n"
        if prefix:
            prefix += "\n"
        text = f"{prefix}repos:\n{block}"
    else:
        end = _repos_end(text, repos_line)
        prefix = text[:end]
        if prefix and not prefix.endswith("\n"):
            prefix += "\n"
        text = f"{prefix}{block}{text[end:]}"
    path.write_text(text, encoding="utf-8")
    _remove_legacy_hook(repo_root)
    return path


def uninstall_hook(repo_root: Path) -> bool:
    """pre-commit 設定から dit hook と旧 Git hook を削除する."""
    removed = False
    path = config_path(repo_root)
    if path.exists():
        text = path.read_text(encoding="utf-8")
        marker = _marker_line(text)
        if marker is not None:
            lines = text.splitlines(keepends=True)
            del lines[marker : marker + len(_render_hook_block(text).splitlines(keepends=True))]
            remaining = "".join(lines)
            if remaining.strip() == "repos:":
                path.unlink()
            else:
                path.write_text(remaining, encoding="utf-8")
            removed = True
    return remove_legacy_hooks(repo_root) or removed


def hook_status(repo_root: Path) -> str:
    """pre-commit hook の状態を返す."""
    path = config_path(repo_root)
    if path.exists():
        text = path.read_text(encoding="utf-8")
        if HOOK_MARKER in text:
            return "installed"
        if _has_dit_hook(text):
            return "unmanaged"
    return "installed" if legacy_hook_status(repo_root) == "installed" else "missing"


def _remove_legacy_hook(repo_root: Path) -> None:
    if legacy_hook_status(repo_root) == "installed":
        remove_legacy_hooks(repo_root)


def _has_dit_hook(text: str) -> bool:
    return bool(
        re.search(rf"^[ \t]*-?[ \t]*id:[ \t]*{re.escape(HOOK_ID)}[ \t]*$", text, re.MULTILINE)
    )


def _marker_line(text: str) -> int | None:
    for index, line in enumerate(text.splitlines()):
        if line.strip() == HOOK_MARKER:
            return index
    return None


def _repos_line(text: str) -> int | None:
    for index, line in enumerate(text.splitlines(keepends=True)):
        if line.strip() == "repos:" and not line[:1].isspace():
            return index
    return None


def _repos_end(text: str, repos_line: int) -> int:
    lines = text.splitlines(keepends=True)
    offset = sum(len(line) for line in lines[: repos_line + 1])
    for line in lines[repos_line + 1 :]:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and not line[:1].isspace():
            break
        offset += len(line)
    return offset


def _render_hook_block(text: str) -> str:
    indent = "  "
    repos_line = _repos_line(text)
    if repos_line is not None:
        lines = text.splitlines(keepends=True)
        for line in lines[repos_line + 1 :]:
            if line.strip() and not line.lstrip().startswith("#"):
                indent = line[: len(line) - len(line.lstrip())]
                break
    nested = indent + "  "
    deep = nested + "  "
    return (
        f"{indent}{HOOK_MARKER}\n"
        f"{indent}- repo: local\n"
        f"{nested}hooks:\n"
        f"{deep}- id: {HOOK_ID}\n"
        f"{deep}  name: dit add\n"
        f"{deep}  entry: dit add --quiet\n"
        f"{deep}  language: system\n"
        f"{deep}  pass_filenames: false\n"
        f"{deep}  always_run: true\n"
    )
