# fix: Increment Version の push 403 を解消する

## Goal

リポジトリの default workflow permissions が `read` のため、`GITHUB_TOKEN` で version bump を push できず 403 になる。ジョブに `permissions.contents: write` を明示して push 可能にする。

## Decisions

- リポジトリ全体の default を write に変えず、この workflow だけ `contents: write` を付与する
- `environment: production` は維持する（Discord webhook 用）

## Implementation steps

1. `.github/workflows/increment_version.yml` の `increment_version` ジョブに `permissions: contents: write` を追加

## Evidence

- https://github.com/2lu3/dit/actions/runs/30779635873/job/91581604501
- Issue: https://github.com/2lu3/dit/issues/4
