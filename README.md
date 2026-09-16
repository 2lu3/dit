# Dit

MD 計算向けの大容量ファイル版管理ツール（DVC 非依存）。

## コンセプト

- 管理対象はリポジトリルートの `dit.toml` で宣言する（`.gitignore` と同じ書式）
- `git commit` 時の pre-commit フックが `uv run dit add` を自動実行し、ポインタ `*.dit` をステージする
- ローカルキャッシュは持たない。ワークツリーの実体 + リモートが真実
- 日常操作は `dit sync`（scope 内だけ一致確認と置く/pull。scope 外は触らない）

## セットアップ

```bash
pip install git+https://github.com/2lu3/dit.git
# or: cd dit && uv sync

cd /path/to/your-md-project
dit init --bucket my-bucket --prefix md-project
```

## 開発

```bash
uv sync --group dev
uv run ruff check src tests
uv run ruff format --check src tests
uv run pytest
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

認証と endpoint は環境変数、または操作対象の Git リポジトリ直下の `.env` で指定する（未設定だとエラー）。

```dotenv
DIT_ACCESS_KEY=...
DIT_SECRET_KEY=...
DIT_ENDPOINT_URL=https://minio.example.com
```

サブディレクトリから実行しても、リポジトリ直下の `.env` を読み込む。worktree では各 worktree 直下が対象。既存の環境変数を優先し、`.env` がなくても環境変数だけで利用できる。秘密情報を含む `.env` は `.gitignore` に追加し、コミットしない。

新規リポジトリでは `dit init` に `--bucket` と `--prefix` を指定する。clone 済みで `dit.toml` がある場合は、引数なしの `dit init` で設定を読み込んで `.dit/` と hook を作成する。

## 使い方

### 新しいリポジトリで使う

```bash
cd /path/to/your-md-project
dit init --bucket my-bucket --prefix md-project
```

`dit init` は `dit.toml`、`.dit/`、Git の pre-commit hook を作成します。`dit.toml` の `[track].patterns` に管理対象を記述してください。

### clone したリポジトリで使う

`dit.toml` は Git で共有されるため、clone 後は bucket と prefix を指定せずに初期化できます。

```bash
git clone <repository-url>
cd <repository-directory>
dit init
```

これで、この作業ツリーに `.dit/` と pre-commit hook が作成されます。worktree から実行する場合も同じです。

### 同期するディレクトリを登録する

実体をこのマシンに置くディレクトリだけを scope に登録します。

```bash
dit scope add data
dit scope list
```

scope 外のファイルは `dit add`、`dit push`、`dit pull`、`dit sync` の対象になりません。

### 日常の操作

```bash
dit status
dit sync --dry-run
dit sync
```

`dit sync` は scope 内の実体とポインタ（`*.dit`）を確認し、必要に応じて remote へ push または remote から pull します。Git commit 時には pre-commit hook が `uv run dit add` を実行してポインタを更新・stageします。

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
