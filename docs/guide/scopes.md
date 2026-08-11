# scope

scopeは、このマシンで大容量ファイルの実体を保持するディレクトリを表します。scope外の実体は同期対象にならず、ditは変更しません。

## 追加する

既存のディレクトリを指定します。

```console
$ dit scope add data/production
```

## 確認する

```console
$ dit scope list
```

## 削除する

```console
$ dit scope remove data/production
```

scopeから外しても、その操作自体は実体を削除しません。以後の同期処理がそのディレクトリへ触れなくなります。正確な引数は[`dit scope` Reference](../reference/scope.md)を参照してください。

## 複数マシン

計算マシンでは計算対象のディレクトリをscopeにし、閲覧だけ行うマシンでは必要なディレクトリだけをscopeにできます。ポインタはGitで共有し、scopeは各マシンで管理します。
