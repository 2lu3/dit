# Dit

MD 計算向けの大容量ファイル版管理ツール（DVC 非依存）。

## コンセプト

- 管理対象はリポジトリルートの `dit.toml` で宣言する（`.gitignore` と同じ書式）
- `git commit` 時の pre-commit フックが `dit add` を自動実行し、ポインタ `*.dit` をステージする
- ローカルキャッシュは持たない。ワークツリーの実体 + リモートが真実
- 日常操作は `dit sync`（scope 内だけ一致確認と置く/pull。scope 外は触らない）

## セットアップ

```bash
pip install git+https://github.com/2lu3/dit.git
# or: cd dit && uv sync

cd /path/to/your-md-project
dit init --bucket my-bucket --prefix md-project
```

`dit.toml` 例:

```toml
[remote]
bucket = "my-bucket"
prefix = "md-project"

[track]
patterns = [
  "*.dcd",
  "*.dvl",
  "*.rst",
  "data/**/out/",
  "!data/00_scratch/",
]
```

認証と endpoint は環境変数で指定する（未設定だとエラー）。

```bash
export DIT_ACCESS_KEY=...
export DIT_SECRET_KEY=...
export DIT_ENDPOINT_URL=https://minio.example.com
```

`dit init` では `--bucket` と `--prefix` が必須。

## コマンド

| コマンド | 役割 |
|---------|------|
| `dit init` | `dit.toml` / `.dit/` / pre-commit フックを作成 |
| `dit add` | scope 内で `dit.toml` に一致するファイルのポインタを更新（通常はフックから） |
| `dit status` | 変更・未追跡・要 pull などを表示 |
| `dit push` / `dit pull` | scope 内の低レベル転送 |
| `dit sync` | 日常の同期（scope 内のみ）。`--dry-run` / `--prune-remote` |
| `dit scope add\|remove\|list` | このマシンで実体を持つディレクトリ |
| `dit hook install\|uninstall\|status` | pre-commit フック管理 |

## sync の方針

1. scope 内で `.dcd` と `.dit` が両方ある場合は一致確認。不一致なら mtime で新しい方を採用し、必要なら push / pull。`.dit` も合わせる
2. scope 内ならローカルに実体を置く（欠落時は pull）。scope 外は無視する（削除もアップロードもしない）

孤児リモート削除は `dit sync --prune-remote` のときだけ。実行前に `git fetch --all --prune` を自動実行する。

## ドキュメント開発

CLI ReferenceはClick定義から生成する。

```bash
uv run docs-reference
uv run docs-validate
uv run zensical serve
```

User Guideを含む全生成にはOpenAI APIキーが必要。

```bash
OPENAI_API_KEY=... uv run docs-generate
```

CLI関連のpull requestではGitHub Actionsが全生成し、生成結果を同じブランチへコミットする。リポジトリには `OPENAI_API_KEY` と、対象リポジトリのContentsにwrite権限を持つfine-grained token `DOCS_BOT_TOKEN` をActions secretとして設定する。これらのsecretを利用できるのは、信頼された同一リポジトリ内のブランチに限定する。GitHub PagesのSourceはGitHub Actionsに設定する。
