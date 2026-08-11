# トラブルシューティング

## 初期化されていないと表示される

Gitリポジトリのルートで `dit init --bucket ... --prefix ...` を実行し、`dit.toml` が存在することを確認します。

## remoteへ接続できない

`DIT_ACCESS_KEY`、`DIT_SECRET_KEY`、`DIT_ENDPOINT_URL` が設定されていることと、`dit.toml` のbucketとprefixを確認します。秘密情報は `dit.toml` やGitへ保存しません。

## statusの記号

- `?`: scope内に実体があるがポインタがない
- `↓`: scope内で実体が欠落している
- `.`: ポインタはあるがscope外である
- `M`: scope内で実体とポインタのハッシュが異なる
- `S`: 実体はあるがscope外である
- 空白: scope内で実体とポインタが一致している

詳細は[`dit status` Reference](../reference/status.md)を参照してください。

## 同期前に処理を確認したい

```console
$ dit sync --dry-run
```

エラーが出る場合は、`dit status`、scope、認証環境変数、remote設定の順に確認します。`--prune-remote` は孤児remoteを削除する明示的な保守操作なので、問題調査のために安易に使用しないでください。
