# ci: run tests and lint on PRs and main

Issue: https://github.com/2lu3/dit/issues/8

## Goal

PR と `main` への push で lint（ruff）と pytest を実行し、結果を Discord に通知する。

## Decisions

| Item | Choice |
|------|--------|
| Trigger | `pull_request` + `push` to `main` |
| Python | 3.12 単一 |
| Lint | `ruff check` + `ruff format --check`（既存 `ruff.toml` に合わせる） |
| Test | `uv run pytest` |
| Discord | `environment: production` + `DISCORD_WEBHOOK`（version bump と同パターン） |
| CPY001 | ignore（著作権ヘッダは現状なし。CI を緑にするため） |
| black | 依存は残すが CI では使わない（ruff format と衝突するため） |

## Implementation steps

1. `dev` 依存に `ruff` を追加
2. `ruff.toml` で `CPY001` を ignore
3. ruff format が指摘する箇所を修正（現状 1 ファイル）
4. `.github/workflows/ci.yml` を追加
5. README にローカルでの lint / test 手順を追記
