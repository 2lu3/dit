# `dit scope`

同期対象ディレクトリ（scope）を管理する.

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
