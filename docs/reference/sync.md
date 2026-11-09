# `dit sync`

Scope 内だけリモートと同期する.

ダウンロードは複数ファイルを並列に取得する。大容量ファイル内の分割転送と合わせ、既定で最大16並列とする。並列数は `DIT_TRANSFER_CONCURRENCY` で変更できる。

同期計画中は対象一覧の作成中にスピナーを表示し、その後は確認済みファイル数を表示する。各ファイルの確認には、ローカルのハッシュ確認とリモートでの存在確認が含まれる。転送中はバイト量を Kbyte / Mbyte / Gbyte の N/N で表示する.

リモートでの存在確認も `DIT_TRANSFER_CONCURRENCY` の値を上限に並列で行い、同じハッシュへの確認は1回にまとめる。進捗の確認数はファイル数で数える。

```console
$ dit sync [OPTIONS]
```

## Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---:|---|---|
| `--dry-run` | boolean | no | false | 実行せずに予定だけ表示する |
| `--prune-remote` | boolean | no | false | git fetch --all --prune のあと、参照されないリモートオブジェクトを削除する |
| `--help` | boolean | no | false | Show this message and exit. |
