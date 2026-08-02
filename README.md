# Dit

MD 計算向けの大容量ファイル版管理ツール（DVC 非依存）。

## コンセプト

- 管理対象はリポジトリルートの `dit.toml` で宣言する（`.gitignore` と同じ書式）
- `git commit` 時の pre-commit フックが `dit add` を自動実行し、ポインタ `*.dit` をステージする
- ローカルキャッシュは持たない。ワークツリーの実体 + リモートが真実
- 日常操作は `dit sync`（① 一致確認と新しい方の採用 ② scope に合わせてローカルを置く/消す）

## セットアップ

```bash
pip install git+https://github.com/2lu3/dit.git
# or: cd dit && uv sync

cd /path/to/your-md-project
dit init --remote-url s3://bucket/prefix --endpoint-url https://minio.example.com
```

`dit.toml` 例:

```toml
[remote]
url = "s3://bucket/prefix"
endpoint_url = "https://minio.example.com"

[track]
patterns = [
  "*.dcd",
  "*.dvl",
  "*.rst",
  "data/**/out/",
  "!data/00_scratch/",
]
```

認証は環境変数 `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`。

## コマンド

| コマンド | 役割 |
|---------|------|
| `dit init` | `dit.toml` / `.dit/` / pre-commit フックを作成 |
| `dit add` | `dit.toml` に一致するファイルのポインタを更新（通常はフックから） |
| `dit status` | 変更・未追跡・要 pull などを表示 |
| `dit push` / `dit pull` | 低レベル転送 |
| `dit sync` | 日常の同期。`--dry-run` / `--prune-remote` |
| `dit scope add\|remove\|list` | このマシンで実体を持つディレクトリ |
| `dit hook install\|uninstall\|status` | pre-commit フック管理 |

## sync の方針

1. `.dcd` と `.dit` が両方ある場合は必ず一致確認。不一致なら mtime で新しい方を採用し、必要なら push / pull。`.dit` も合わせる
2. scope 内ならローカルに実体を置く。scope 外なら（リモート確認後）ローカルを消す

孤児リモート削除は `dit sync --prune-remote` のときだけ。実行前に `git fetch --all --prune` を自動実行する。
