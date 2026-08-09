# fix: scope 外のファイルを push / sync / add で触らない

Issue: https://github.com/2lu3/dit/issues/12

## Goal

`dit` の転送・同期・ポインタ更新を **scope 内だけ** に制限する。scope 外は hash / push / pull / ポインタ更新 / ローカル削除のいずれも行わない。

## Decisions

| Item | Choice |
|------|--------|
| scope 外の実体 | 無視（残っていても削除しない） |
| `dit add` | scope 内の tracked のみ |
| `dit push` | scope 内のみ（docstring と実装を一致） |
| `dit sync` | scope 外は早期スキップ |
| `dit status` | scope 外は hash せず `S` / `.` 表示のみ |
| 空 scope | すべて no-op（`contains` が常に False） |

## Classification（更新後）

| ポインタ | 実体 | scope | sync の動き |
|---------|------|-------|-------------|
| あり | あり | 内 | 一致確認。必要なら push / pull |
| あり | あり | 外 | 無視（触らない） |
| あり | なし | 内 | リモートから pull |
| あり | なし | 外 | 無視 |
| なし | あり | 内 | 警告（ポインタ未作成） |
| なし | あり | 外 | 無視 |

## Implementation steps

1. `run_push`: `Scope.contains` でフィルタ
2. `_sync_one`: scope 外は空結果で return（`_delete_local_if_safe` 経路を使わない）
3. `run_add` / prune: scope 内のみ
4. `status`: scope 外は hash せず表示のみ
5. README / `dit --help` の分類表を更新
6. テスト: scope 外は push/sync/add しないこと。既存の delete 期待テストを置き換え

## Out of scope

- scope の永続フォーマット変更
- remote prune の挙動変更
