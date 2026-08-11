# docs: dit --help の scope 内外分岐を畳む

Issue: https://github.com/2lu3/dit/issues/14

## Goal

`dit --help` で scope 外がすべて「無視」であることを1行にまとめ、ポインタ/実体の分類は scope 内前提だけにする。

## Decisions

| Item | Choice |
|------|--------|
| 掲載場所 | ルート `dit --help`（`src/dit/main.py` docstring）のみ |
| scope 外 | 「scope 外は無視（触らない）」の1行 |
| 残りの行 | scope 内前提（見出しは付けない） |
| 挙動 | 変更しない |

## Help text (source of truth)

```text
scope 外は無視（触らない）

ポインタ+実体   一致確認。必要なら push / pull
ポインタのみ    リモートから pull
実体のみ        警告（ポインタ未作成）
```

## Implementation steps

1. `src/dit/main.py` の分類表を上記に差し替え（空行で段落が分かれるため `\b` を2つ使う）
2. `uv run dit --help` で表示確認
