# feat: dit sync の進捗をバイト単位の N/N 表示にする

## Goal

`dit sync` でも、先に対象ファイルを計画し、転送バイト量を Kbyte / Mbyte / Gbyte の N/N で表示する。残り時間が読み取れるようにする。

## Decisions

| Item | Choice |
|------|--------|
| 計画 | 一致確認のあと、push / pull 対象と size を先に確定する |
| 分子 / 分母 | 転送済みバイト / 今回の push+pull 合計バイト |
| 単位 | push / pull と同じ `unit="byte"`, `scale="SI2"` |
| 更新 | boto3 Callback。バー title は `sync` |
| 対象外 | ハッシュ確認、ポインタ更新、`--prune-remote`、`--dry-run`、合計 0 バイト |
| 基盤 | `feat/push-pull-byte-progress` の `ByteTransferBar` を再利用する |

## Implementation steps

1. `run_sync` を計画（`SyncStep`）と実行に分ける
2. CLI で合計バイトのバーを出してから転送する
3. README / User Guide / CLI 説明を更新する
4. 計画サイズと push/pull 進捗のテストを追加する
