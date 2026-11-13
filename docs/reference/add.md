# `dit add`

Scope 内の追跡パスのポインタを作成・更新する.

シンボリックリンクはリンク先の実体を基準に scope を判定し、その隣の `.dit` を確認・更新します。同じ実体を指すリンクが複数あっても、処理は1回です。実体の内容とサイズが `.dit` の記録に一致すれば書き直しません。未ステージのポインタは再実行時にも Git にステージします。

ファイル情報のキャッシュは処理の最後にまとめて保存します。失敗や中断の際は、ポインタの作成・削除や Git のステージが途中まで残ることがあります。`dit add` を再実行すると、キャッシュとポインタの状態を確認して処理をやり直します。`--prune` の処理を再開する場合は、同じオプションを指定してください。

```console
$ dit add [OPTIONS]
```

## Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---:|---|---|
| `--quiet`, `-q` | boolean | no | false | 詳細出力を抑える |
| `--prune` | boolean | no | false | scope 内の不要ポインタを削除する |
| `--help` | boolean | no | false | Show this message and exit. |
