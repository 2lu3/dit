"""ドキュメント検証用の共有パス."""

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
    """リポジトリルートを返す（テスト・自動化用の上書きあり）."""
    configured = os.environ.get("DIT_DOCS_ROOT")
    if configured:
        return Path(configured).resolve()
    return Path(__file__).resolve().parents[3]
