# docs: dit --help に scope / ポインタ / 実体の分類説明を追加

Issue: https://github.com/2lu3/dit/issues/10

## Goal

`dit --help` だけで、scope・ポインタの有無・実体の有無の分類と `sync` の動きが読めるようにする。

## Decisions

| Item | Choice |
|------|--------|
| 言語 | 日本語 |
| 掲載場所 | ルート `dit --help` のみ |
| 用語 | 実体（大容量ファイル本体）。ポインタは `*.dit`、scope はこのマシンで実体を置くディレクトリ |
| 実装箇所 | `src/dit/main.py` の Click グループ docstring（`\b` で整形） |
| サブコマンド help | 変更しない（`status` の記号説明は既存のまま） |

## Classification (source of truth for help text)

| ポインタ | 実体 | scope | sync の動き |
|---------|------|-------|-------------|
| あり | あり | 内 | 一致確認。必要なら push / pull |
| あり | あり | 外 | 一致確認のあと、リモートにあれば実体を削除 |
| あり | なし | 内 | リモートから pull |
| あり | なし | 外 | そのまま（ローカルに実体なし） |
| なし | あり | — | 警告（ポインタ未作成） |
| なし | なし | — | 対象外（help には省略可） |

## Implementation steps

1. `src/dit/main.py` の `cli` docstring に用語と分類表を追加
2. `uv run dit --help` で表示を確認
3. `uv run ruff check` / `uv run pytest` で回帰確認
