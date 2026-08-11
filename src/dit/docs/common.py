"""Shared paths and atomic file helpers for documentation generation."""

from __future__ import annotations

import os
from pathlib import Path

GUIDE_FILES = (
    "getting-started.md",
    "concepts.md",
    "daily-workflow.md",
    "scopes.md",
    "troubleshooting.md",
)


def project_root() -> Path:
    """Return the repository root, with an override for tests and automation."""
    configured = os.environ.get("DIT_DOCS_ROOT")
    if configured:
        return Path(configured).resolve()
    return Path(__file__).resolve().parents[3]


def replace_markdown_directory(directory: Path, files: dict[str, str]) -> None:
    """Replace generated Markdown files after all content has been validated."""
    directory.mkdir(parents=True, exist_ok=True)
    expected = set(files)
    for path in directory.glob("*.md"):
        if path.name not in expected:
            path.unlink()
    for name, content in files.items():
        temporary = directory / f".{name}.tmp"
        temporary.write_text(content.rstrip() + "\n", encoding="utf-8")
        temporary.replace(directory / name)
