# scope

scopeは、このマシンで大容量ファイルの実体を保持するディレクトリを表します。ディレクトリを指定しない場合はリポジトリ全体が対象です。`dit add` と `dit push` はscope外の実体も対象にします。`dit pull` はscope内だけを取得します。

## 追加する

既存のディレクトリを指定します。

```console
$ dit scope add data/production
```

リポジトリ全体を scope にする場合は、リポジトリのルートで `dit scope add .` を実行します。

## 確認する

```console
$ dit scope list
```

## 削除する

```console
$ dit scope remove data/production
```

scopeから外しても、その操作自体は実体を削除しません。その後の `dit sync` は、ポインタと一致し同じ内容がremoteに存在する実体を削除します。未登録、変更済み、未push、またはremoteを確認できない実体は保持し、理由を表示します。ポインタは残ります。`dit sync --dry-run` で事前に確認できます。正確な引数は[`dit scope` Reference](../reference/scope.md)を参照してください。

## 複数マシン

計算マシンでは計算対象のディレクトリをscopeにし、閲覧だけ行うマシンでは必要なディレクトリだけをscopeにできます。ポインタはGitで共有し、scopeは各マシンで管理します。
