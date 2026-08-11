# 日常のワークフロー

## 作業前

Gitの変更を取得したあと、状態を確認して同期します。

```console
$ git pull
$ dit status
$ dit sync --dry-run
$ dit sync
```

`--dry-run` は予定された処理だけを表示します。内容を確認してから通常の `dit sync` を実行できます。

## ファイルを変更したあと

インストールされたpre-commitフックは、Gitのcommit時に `dit add` を実行してscope内のポインタを更新します。

```console
$ git add dit.toml path/to/file.dit
$ git commit
$ dit sync
```

実際にstageされるファイルは作業内容に合わせて確認してください。`dit status` の表示は[`dit status` Reference](../reference/status.md)で確認できます。

## 低レベル転送

`dit push` と `dit pull` は転送方向を明示したい場合の低レベル操作です。通常は一致確認を含む `dit sync` を使います。remoteの孤児を削除する `dit sync --prune-remote` は通常の同期には必要ありません。
