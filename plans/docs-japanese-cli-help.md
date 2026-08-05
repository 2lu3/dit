# docs: dit CLI ヘルプを日本語化

Issue: https://github.com/2lu3/dit/issues/6

## Goal

`dit --help` および各サブコマンドの `--help` を日本語化する。`dit status --help` には状態記号の説明を含める。

## Decisions

| Item | Choice |
|------|--------|
| 対象 | Click のコマンド docstring / option `help=` |
| status 記号 | `?` / `↓` / `.` / `M` / `S` / 空白（問題なし）を日本語で説明 |
| help 未設定オプション | `--dry-run` / `--quiet` / `--force` にも日本語 `help=` を追加 |
| Click 標準文言 | `Options:` / `--help Show this message and exit.` はライブラリ側のため対象外 |
| 実行時メッセージ | 対象外（`added` / sync action など） |

## Implementation steps

1. `src/dit/main.py` と `src/dit/command/*.py` の help 文言を日本語化
2. `status` の docstring に記号一覧を追加（Click の `\b` で整形）
3. `uv run ruff` / `uv run pytest` で確認
4. `dit status --help` などで表示を目視確認
