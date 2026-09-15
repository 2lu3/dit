# Global Cursor Settings

> Keywords: **MUST** / **NEVER** = mandatory. **SHOULD** = recommended unless there is a clear reason not to. **MAY** = optional.

詳細ルールは以下に分割されています。各文書の frontmatter の `applies_to` は適用用途を示します。
`all` は全用途共通です。用途別文書は対象コードがその用途の場合に適用します。

- [General Workflow](.agents/rules/general-workflow.md): 全体方針、汎用ワークフロー、デバッグ、PR作成前後の運用方針
- [タスクの状態管理](.agents/rules/task-management.md): 担当タスクの状態更新とトラッカーの確認
- [Git 運用](.agents/rules/git.md): Git 操作の権限ルール
- [Flow スキル](.agents/skills/flow/SKILL.md): plan / do / check / auto のライフサイクル手順
- [Python](.agents/rules/python.md): Python 依存管理・実行規約
- [本番運用コード](.agents/rules/production-code.md): 利用者との契約、境界でのエラー処理、運用の方針

適用用途: `production`。`all` と `production` の文書をインストール済みです。
