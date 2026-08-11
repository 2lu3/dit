# `dit sync`

Scope 内だけリモートと同期する.

```console
$ dit sync [OPTIONS]
```

## Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---:|---|---|
| `--dry-run` | boolean | no | false | 実行せずに予定だけ表示する |
| `--prune-remote` | boolean | no | false | git fetch --all --prune のあと、参照されないリモートオブジェクトを削除する |
| `--help` | boolean | no | false | Show this message and exit. |
