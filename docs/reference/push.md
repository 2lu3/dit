# `dit push`

Scope 内ポインタが指すローカルオブジェクトをアップロードする.

転送計画中はポインタ一覧の作成中にスピナーを表示し、各ポインタの確認数を進捗表示する。対象確定後の転送中はバイト量を Kbyte / Mbyte / Gbyte の N/N で表示する.

```console
$ dit push [OPTIONS]
```

## Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---:|---|---|
| `--dry-run` | boolean | no | false | 実行せずに予定だけ表示する |
| `--help` | boolean | no | false | Show this message and exit. |
