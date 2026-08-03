# fix: Discord notify で production environment を指定する

## Goal

`DISCORD_WEBHOOK` は GitHub Environments の `production` secret にあるが、workflow ジョブで environment 未指定のため参照できない。`environment: production` を追加する。

## Decisions

- ジョブ全体に `environment: production` を付ける（Notify ステップだけに environment は付けられないため）
- secret 名 `DISCORD_WEBHOOK` はそのまま

## Implementation steps

1. `.github/workflows/increment_version.yml` の `increment_version` ジョブに `environment: production` を追加
