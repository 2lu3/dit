from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from dit.docs.common import GUIDE_FILES
from dit.docs.validate import validate_docs
from dit.main import create_cli

if TYPE_CHECKING:
    from pathlib import Path


def test_create_cli_returns_complete_independent_groups() -> None:
    first = create_cli()
    second = create_cli()
    expected = {"init", "add", "status", "push", "pull", "sync", "scope", "hook"}
    assert set(first.commands) == expected
    assert set(second.commands) == expected
    assert first is not second


def test_validate_docs_rejects_broken_link(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    (docs / "source").mkdir(parents=True)
    (docs / "guide").mkdir()
    (docs / "reference").mkdir()
    (docs / "index.md").write_text("# Home\n\n[bad](missing.md)\n", encoding="utf-8")
    (docs / "source" / "guide-policy.md").write_text("# Policy\n", encoding="utf-8")
    for name in GUIDE_FILES:
        (docs / "guide" / name).write_text("# Guide\n", encoding="utf-8")
    reference_pages = (
        "index.md",
        "init.md",
        "add.md",
        "status.md",
        "push.md",
        "pull.md",
        "sync.md",
        "scope.md",
        "hook.md",
    )
    for name in reference_pages:
        (docs / "reference" / name).write_text("# Reference\n", encoding="utf-8")
    with pytest.raises(ValueError, match="broken link"):
        validate_docs(tmp_path)
