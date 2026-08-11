# `dit hook`

pre-commit フックを管理する.

```console
$ dit hook [OPTIONS] COMMAND [ARGS]...
```

## Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---:|---|---|
| `--help` | boolean | no | false | Show this message and exit. |

## `dit hook install`

pre-commit フックをインストールする.

```console
$ dit hook install [OPTIONS]
```

### Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---:|---|---|
| `--force` | boolean | no | false | 管理外のフックを上書きする |
| `--help` | boolean | no | false | Show this message and exit. |

## `dit hook status`

pre-commit フックの状態を表示する.

```console
$ dit hook status [OPTIONS]
```

### Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---:|---|---|
| `--help` | boolean | no | false | Show this message and exit. |

## `dit hook uninstall`

pre-commit フックをアンインストールする.

```console
$ dit hook uninstall [OPTIONS]
```

### Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---:|---|---|
| `--help` | boolean | no | false | Show this message and exit. |
