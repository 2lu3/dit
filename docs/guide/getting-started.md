# はじめる

ditは、大容量ファイルの実体をS3互換ストレージへ置き、その内容を表す小さな `*.dit` ポインタをGitで管理します。

## インストール

```console
$ pip install git+https://github.com/2lu3/dit.git
```

## リポジトリを初期化する

Gitリポジトリでbucketとprefixを指定します。

```console
$ dit init --bucket my-bucket --prefix md-project
```

作成された `dit.toml` の `[track].patterns` に、管理するファイルやディレクトリを `.gitignore` と同じ形式で記述します。

## 認証情報を設定する

```console
$ export DIT_ACCESS_KEY=...
$ export DIT_SECRET_KEY=...
$ export DIT_ENDPOINT_URL=https://minio.example.com
```

## scopeを設定して同期する

このマシンで実体を置くディレクトリをscopeへ追加します。

```console
$ dit scope add data
$ dit status
$ dit sync --dry-run
$ dit sync
```

以後の通常操作には `dit sync` を使います。詳しくは[日常のワークフロー](daily-workflow.md)と[CLI Reference](../reference/index.md)を参照してください。
