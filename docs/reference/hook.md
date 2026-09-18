# `dit hook`

`.pre-commit-config.yaml` の dit hook を管理する.

```console
$ dit hook [OPTIONS] COMMAND [ARGS]...
```

## Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---:|---|---|
| `--help` | boolean | no | false | Show this message and exit. |

## `dit hook install`

pre-commit 設定に dit hook を追加する.

```console
$ dit hook install
```

### Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---:|---|---|
| `--help` | boolean | no | false | Show this message and exit. |

## `dit hook status`

pre-commit 設定内の dit hook の状態を表示する.

```console
$ dit hook status [OPTIONS]
```

### Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---:|---|---|
| `--help` | boolean | no | false | Show this message and exit. |

## `dit hook uninstall`

pre-commit 設定から dit hook を削除する.

```console
$ dit hook uninstall [OPTIONS]
```

### Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---:|---|---|
| `--help` | boolean | no | false | Show this message and exit. |
