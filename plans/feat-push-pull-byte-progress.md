# feat: dit push / pull の進捗をバイト単位の N/N 表示にする

Issue: https://github.com/2lu3/dit/issues/24

## Goal

`dit push` と `dit pull` の alive-progress を、ファイル件数ではなく転送バイト量の N/N にする。単位は Kbyte / Mbyte / Gbyte。

## Decisions

| Item | Choice |
|------|--------|
| 分子 / 分母 | 転送済みバイト / 今回の対象ファイルの合計バイト |
| 単位 | alive-progress `unit="byte"`, `scale="SI2"`（1024 進、K/M/Gbyte） |
| 表示 | `{count}/{total}`（例: `1.0Mbyte/2.0Gbyte`） |
| 更新タイミング | boto3 `Callback`（転送中）。multipart のため加算は lock で直列化 |
| 対象コマンド | `dit push` / `dit pull` のみ（`dit sync` は変更しない） |
| 総量 0 | バーを出さず転送だけ行う（alive-progress は total=0 を unknown 扱いするため） |

## Implementation steps

1. Remote の upload/download にバイト増分 callback を渡す
2. push/pull を計画（対象と size）と実行に分ける
3. CLI で合計バイトを渡した alive_bar を開始し、Callback で加算する
4. README / User Guide / CLI 説明を更新する
5. バー表示・Callback・push/pull 経路のテストを追加する
