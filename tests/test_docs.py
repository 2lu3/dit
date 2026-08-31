from __future__ import annotations

import json
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest

from dit.docs.guide import GUIDE_TITLES, request_guide, validate_guide_payload
from dit.docs.reference import render_reference
from dit.docs.validate import validate_docs
from dit.main import create_cli

if TYPE_CHECKING:
    from pathlib import Path


def _guide_payload() -> dict[str, str]:
    return {
        name.removesuffix(".md").replace("-", "_"): f"{title}\n\n本文"
        for name, title in GUIDE_TITLES.items()
    }


def test_create_cli_returns_complete_independent_groups() -> None:
    first = create_cli()
    second = create_cli()
    expected = {"init", "add", "status", "push", "pull", "sync", "scope", "hook"}
    assert set(first.commands) == expected
    assert set(second.commands) == expected
    assert first is not second


def test_reference_contains_commands_arguments_and_options() -> None:
    pages = render_reference(create_cli())
    assert set(pages) == {
        "index.md",
        "init.md",
        "add.md",
        "status.md",
        "push.md",
        "pull.md",
        "sync.md",
        "scope.md",
        "hook.md",
    }
    assert "`--bucket`" in pages["init.md"]
    assert "yes" in pages["init.md"]
    assert "`directory`" in pages["scope.md"]
    assert "## `dit scope add`" in pages["scope.md"]
    assert "`--prune-remote`" in pages["sync.md"]


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (lambda value: value.pop("scopes"), "exactly the five"),
        (lambda value: value.update(extra="# Extra"), "exactly the five"),
        (lambda value: value.update(scopes=""), "non-empty Markdown"),
        (lambda value: value.update(scopes="# Wrong\n"), "must start"),
    ],
)
def test_guide_payload_rejects_invalid_output(mutate: Any, match: str) -> None:
    payload = _guide_payload()
    mutate(payload)
    with pytest.raises(ValueError, match=match):
        validate_guide_payload(payload)


def test_request_guide_uses_one_structured_response(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    class Responses:
        def create(self, **kwargs: Any) -> SimpleNamespace:
            calls.append(kwargs)
            return SimpleNamespace(output_text=json.dumps(_guide_payload()))

    client = SimpleNamespace(responses=Responses())
    monkeypatch.setattr("dit.docs.guide.collect_sources", lambda: "sources")
    result = request_guide(client)
    assert len(calls) == 1
    assert calls[0]["model"] == "gpt-5.6-terra"
    assert calls[0]["text"]["format"]["strict"] is True
    assert set(result) == set(GUIDE_TITLES)


def test_request_guide_rejects_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    client = SimpleNamespace(
        responses=SimpleNamespace(create=lambda **kwargs: SimpleNamespace(output_text="not json"))
    )
    monkeypatch.setattr("dit.docs.guide.collect_sources", lambda: "sources")
    with pytest.raises(ValueError, match="valid structured JSON"):
        request_guide(client)


def test_validate_docs_rejects_broken_link(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    (docs / "source").mkdir(parents=True)
    (docs / "guide").mkdir()
    (docs / "reference").mkdir()
    (docs / "index.md").write_text("# Home\n\n[bad](missing.md)\n", encoding="utf-8")
    (docs / "source" / "guide-policy.md").write_text("# Policy\n", encoding="utf-8")
    for name, title in GUIDE_TITLES.items():
        (docs / "guide" / name).write_text(f"{title}\n", encoding="utf-8")
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
