"""公開前に生成ドキュメントを検証する."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from dit.docs.common import GUIDE_FILES, project_root

if TYPE_CHECKING:
    from pathlib import Path

LINK = re.compile(r"\[[^]]+\]\(([^)]+)\)")


class DocsValidationError(ValueError):
    """生成ドキュメントが不完全または不正なときに送出する."""


def validate_docs(root: Path | None = None) -> None:
    """必須ページ・見出し・ローカル Markdown リンクを検証する."""
    root = root or project_root()
    docs = root / "docs"
    required = [docs / "index.md", docs / "source" / "guide-policy.md"]
    required.extend(docs / "guide" / name for name in GUIDE_FILES)
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
    required.extend(docs / "reference" / name for name in reference_pages)
    missing = [str(path.relative_to(root)) for path in required if not path.is_file()]
    if missing:
        message = f"missing documentation pages: {', '.join(missing)}"
        raise DocsValidationError(message)

    for path in docs.rglob("*.md"):
        content = path.read_text(encoding="utf-8")
        if not content.lstrip().startswith("#"):
            message = f"{path.relative_to(root)} must start with a heading"
            raise DocsValidationError(message)
        if "Python API Reference" in content:
            message = f"{path.relative_to(root)} must not document the Python API"
            raise DocsValidationError(message)
        for raw_target in LINK.findall(content):
            target = raw_target.split("#", 1)[0]
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            candidate = (path.parent / target).resolve()
            if candidate.suffix == "":
                candidate = candidate / "index.md"
            if not candidate.is_file():
                message = f"broken link in {path.relative_to(root)}: {target}"
                raise DocsValidationError(message)


def main() -> None:
    """ドキュメント検証の CLI エントリポイント."""
    validate_docs()
