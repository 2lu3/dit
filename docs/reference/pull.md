# `dit pull`

欠落しているオブジェクトを scope 内からダウンロードする.

複数ファイルを同時にダウンロードする。大容量ファイル内の分割転送と合わせ、既定で最大16並列とする。並列数は `DIT_TRANSFER_CONCURRENCY` で変更できる。

転送計画中はポインタ一覧の作成中にスピナーを表示し、各ポインタの確認数を進捗表示する。対象確定後の転送中はバイト量を Kbyte / Mbyte / Gbyte の N/N で表示する.

```console
$ dit pull [OPTIONS]
```

## Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---:|---|---|
| `--dry-run` | boolean | no | false | 実行せずに予定だけ表示する |
| `--help` | boolean | no | false | Show this message and exit. |
