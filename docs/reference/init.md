# `dit init`

dit.toml / .dit/ / pre-commit フックを初期化する.

```console
$ dit init [OPTIONS]
```

## Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---:|---|---|
| `--bucket` | text | no | — | S3 バケット名（新規作成時） |
| `--prefix` | text | no | — | バケット内のキープレフィックス（新規作成時） |
| `--force-hook` | boolean | no | false | 管理外の pre-commit フックを上書きする |
| `--help` | boolean | no | false | Show this message and exit. |
