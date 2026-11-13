# `dit scope`

ローカルに実体を保持するディレクトリ（scope）を管理する。設定変更だけでは実体を削除しない。

```console
$ dit scope [OPTIONS] COMMAND [ARGS]...
```

## Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---:|---|---|
| `--help` | boolean | no | false | Show this message and exit. |

## `dit scope add`

ディレクトリを scope に追加する.

```console
$ dit scope add [OPTIONS] DIRECTORY
```

### Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---:|---|---|
| `directory` | directory | yes | — | — |
| `--help` | boolean | no | false | Show this message and exit. |

## `dit scope list`

現在の scope ディレクトリを一覧表示する.

```console
$ dit scope list [OPTIONS]
```

### Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---:|---|---|
| `--help` | boolean | no | false | Show this message and exit. |

## `dit scope remove`

ディレクトリを scope から削除する.

```console
$ dit scope remove [OPTIONS] DIRECTORY
```

### Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---:|---|---|
| `directory` | text | yes | — | — |
| `--help` | boolean | no | false | Show this message and exit. |
