# `dit push`

scope に関係なくポインタが指すローカルオブジェクトをアップロードする。実体とポインタが異なる場合は `dit add` が必要です。

転送計画中はポインタ一覧の作成中にスピナーを表示し、各ポインタの確認数を進捗表示する。対象確定後の転送中はバイト量を Kbyte / Mbyte / Gbyte の N/N で表示する.

リモートでの存在確認は、`DIT_TRANSFER_CONCURRENCY` の値を上限に並列で行う。同じハッシュへの確認は1回にまとめる。

```console
$ dit push [OPTIONS]
```

## Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---:|---|---|
| `--dry-run` | boolean | no | false | 実行せずに予定だけ表示する |
| `--help` | boolean | no | false | Show this message and exit. |
