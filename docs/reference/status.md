# `dit status`

ポインタと scope に対する追跡ファイルの状態を表示する.

状態記号:


  ?  実体はあるがポインタがない（未登録、scope 内）
  ↓  実体がなく、scope 内（要 pull）
  .  実体がなく、scope 外
  M  実体のハッシュがポインタと不一致（変更あり、scope 内）
  S  実体はあるが scope 外（触らない）
     問題なし（ポインタと一致し、scope 内）

```console
$ dit status [OPTIONS]
```

## Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---:|---|---|
| `--help` | boolean | no | false | Show this message and exit. |
