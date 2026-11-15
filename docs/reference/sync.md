# `dit sync`

scope 内をリモートと同期し、scope 外の実体はポインタと一致し、同じ内容がリモートに存在すると確認できた場合に削除する。ポインタは残す。未登録、変更済み、未 push、リモートの確認に失敗した実体は保持し、理由を表示する。`--dry-run` では取得・削除の予定と保持する理由を表示する。

scope 内のシンボリックリンクから参照される scope 外の実体も保持する。

ダウンロードは複数ファイルを並列に取得する。大容量ファイル内の分割転送と合わせ、既定で最大16並列とする。並列数は `DIT_TRANSFER_CONCURRENCY` で変更できる。

同期計画中は対象一覧の作成中にスピナーを表示し、その後は確認済みファイル数を表示する。各ファイルの確認には、ローカルのハッシュ確認とリモートでの存在確認が含まれる。転送中はバイト量を Kbyte / Mbyte / Gbyte の N/N で表示する.

scope 内のリモート存在確認は、対象 prefix のオブジェクト一覧を全ページ取得して一括照合する。S3 では `s3:ListBucket` 権限が必要。一覧取得に失敗した場合は転送を開始しない。進捗の確認数はファイル数で数える。scope 外の実体を削除する際の個別確認は維持する。

```console
$ dit sync [OPTIONS]
```

## Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---:|---|---|
| `--dry-run` | boolean | no | false | 実行せずに予定だけ表示する |
| `--prune-remote` | boolean | no | false | git fetch --all --prune のあと、参照されないリモートオブジェクトを削除する |
| `--help` | boolean | no | false | Show this message and exit. |
