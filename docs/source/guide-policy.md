# User Guide生成方針

このファイルは、LLMがUser Guide全体を再生成するときの編集上の正本である。

## 読者

- Gitの基本操作を理解している利用者を対象とする。
- DVC、S3 API、ditのPython内部実装に関する知識は前提にしない。
- 日本語で、簡潔かつ具体的に説明する。

## 製品方針

- 日常操作には `dit sync` を推奨する。
- `dit push` と `dit pull` は、必要な場合にだけ使う低レベル操作として説明する。
- scopeは「このマシンで実体を置くディレクトリ」と定義する。
- scope外の実体には触れないことを明記する。
- `--prune-remote` は明示的に選ぶ保守操作として扱い、通常操作として推奨しない。
- ポインタはGitに保存する `*.dit` メタデータ、実体はGitに保存しない大容量ファイル本体と呼ぶ。

## 執筆規則

- コード、テスト、CLI Referenceで確認できない挙動を推測しない。
- Python APIや内部クラスのReferenceを作らない。
- CLIのオプション一覧をGuideに複製せず、CLI Referenceへリンクする。
- 初回利用者が実行順を判断できる例を含める。
- コマンド例にはプロンプトとして `$` を付け、秘密情報の実値を含めない。
- ページ間リンクは相対リンクを使う。

## ページ構成

- `getting-started.md`: インストールから最初の同期まで。
- `concepts.md`: 実体、ポインタ、remote、scopeの関係。
- `daily-workflow.md`: 日常的なstatus、commit、syncの流れ。
- `scopes.md`: scopeの追加、削除、複数マシンでの考え方。
- `troubleshooting.md`: 初期化、認証、状態記号、競合時の確認方法。
