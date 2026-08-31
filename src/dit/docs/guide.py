"""Generate the complete Japanese user guide with the OpenAI Responses API."""

from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI

from dit.docs.common import GUIDE_FILES, project_root, replace_markdown_directory

MODEL = "gpt-5.6-terra"
GUIDE_TITLES = {
    "getting-started.md": "# はじめる",
    "concepts.md": "# 基本概念",
    "daily-workflow.md": "# 日常のワークフロー",
    "scopes.md": "# scope",
    "troubleshooting.md": "# トラブルシューティング",
}


class GuideGenerationError(ValueError):
    """Raised when a generated guide is incomplete or malformed."""


def guide_schema() -> dict[str, Any]:
    """Return the strict JSON schema accepted from the model."""
    properties = {
        name.removesuffix(".md").replace("-", "_"): {"type": "string"} for name in GUIDE_FILES
    }
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def validate_guide_payload(payload: object) -> dict[str, str]:
    """Validate and map the structured model response to exact filenames."""
    if not isinstance(payload, dict):
        message = "guide response must be a JSON object"
        raise TypeError(message)
    expected_keys = {name.removesuffix(".md").replace("-", "_") for name in GUIDE_FILES}
    if set(payload) != expected_keys:
        message = "guide response must contain exactly the five configured pages"
        raise GuideGenerationError(message)
    files: dict[str, str] = {}
    for name in GUIDE_FILES:
        key = name.removesuffix(".md").replace("-", "_")
        content = payload[key]
        if not isinstance(content, str) or not content.strip():
            message = f"{name} must contain non-empty Markdown"
            raise GuideGenerationError(message)
        if not content.lstrip().startswith(GUIDE_TITLES[name]):
            message = f"{name} must start with {GUIDE_TITLES[name]!r}"
            raise GuideGenerationError(message)
        files[name] = content
    return files


def collect_sources() -> str:
    """Collect only current, reviewable sources of truth for guide generation."""
    root = project_root()
    paths = [
        root / "README.md",
        root / "pyproject.toml",
        root / "docs" / "source" / "guide-policy.md",
    ]
    paths.extend(sorted((root / "src" / "dit").rglob("*.py")))
    paths.extend(sorted((root / "tests").rglob("*.py")))
    paths.extend(sorted((root / "docs" / "reference").glob("*.md")))
    chunks = []
    for path in paths:
        relative = path.relative_to(root)
        chunks.append(f"\n===== {relative} =====\n{path.read_text(encoding='utf-8')}")
    return "".join(chunks)


def _prompt(sources: str) -> str:
    return f"""次の資料だけを事実根拠として、ditのUser Guide全5ページを日本語で書き直してください。

必須条件:
- コードにない挙動を推測しない。
- 通常操作は dit sync を推奨し、push と pull は低レベル操作として扱う。
- scope外の実体を変更しないことを明記する。
- Python APIや内部実装のリファレンスを書かない。
- 各フィールドには完成したMarkdownを入れ、指定されたH1から開始する。
- ページ間リンクは相対リンクを使う。

資料:
{sources}
"""


def request_guide(client: OpenAI) -> dict[str, str]:
    """Request and validate all guide pages in one Responses API call."""
    response = client.responses.create(
        model=MODEL,
        reasoning={"effort": "medium"},
        input=_prompt(collect_sources()),
        text={
            "format": {
                "type": "json_schema",
                "name": "dit_user_guide",
                "strict": True,
                "schema": guide_schema(),
            }
        },
    )
    try:
        payload = json.loads(response.output_text)
    except (AttributeError, json.JSONDecodeError) as exc:
        message = "OpenAI response did not contain valid structured JSON"
        raise GuideGenerationError(message) from exc
    return validate_guide_payload(payload)


def generate_guide(client: OpenAI | None = None) -> None:
    """Generate, validate, and replace the complete user guide."""
    if not os.environ.get("OPENAI_API_KEY") and client is None:
        message = "OPENAI_API_KEY is required to generate the user guide"
        raise RuntimeError(message)
    if client is None:
        client = OpenAI()
    replace_markdown_directory(project_root() / "docs" / "guide", request_guide(client))


def main() -> None:
    """CLI entry point for user guide generation."""
    generate_guide()
