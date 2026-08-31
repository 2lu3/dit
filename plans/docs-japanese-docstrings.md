# docs: ソースコードの docstring を日本語化

Issue: https://github.com/2lu3/dit/issues/16

## Goal

`src/dit/` 配下のモジュール・クラス・関数 docstring を日本語化する。

## Decisions

| Item | Choice |
|------|--------|
| 対象 | `src/dit/` 配下すべての Python docstring |
| 既存の日本語 CLI help | 維持（再翻訳しない） |
| 句点 | ruff D415 のため ASCII `.` で終える（既存 CLI help に合わせる） |
| 先頭語 | ruff D403 のため `Scope` / `Dit` などラテン先頭語は大文字 |
| 実行時メッセージ | 対象外 |
| テスト | 現状 docstring なしのため対象外 |
| SQL など非 docstring の三連クォート | 変更しない |
| README | docstring のみの変更のため更新不要 |
| 参照ドキュメント再生成 | Click help 文言は既に日本語のため不要 |

## Implementation steps

1. 英語 docstring を抽出して一覧化
2. `main.py` / `command/` / `core/` / `docs/` / `hooks/` を日本語化
3. `uv run ruff check` / `uv run pytest` で確認
4. README に仕様変更がないか確認（docstring のみなら更新不要）
