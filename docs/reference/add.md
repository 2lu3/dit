# `dit add`

scope に関係なく追跡パスのポインタを作成・更新する.

シンボリックリンクはリンク先の実体の隣の `.dit` を確認・更新します。同じ実体を指すリンクが複数あっても、処理は1回です。実体の内容とサイズが `.dit` の記録に一致すれば、書き直しや `git add` は行いません。

```console
$ dit add [OPTIONS]
```

## Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---:|---|---|
| `--quiet`, `-q` | boolean | no | false | 詳細出力を抑える |
| `--prune` | boolean | no | false | scope 内の不要ポインタを削除する |
| `--help` | boolean | no | false | Show this message and exit. |
