"""dit init コマンド."""

from __future__ import annotations

import click

from dit.core.config import init_config, load_config
from dit.core.errors import RepoError
from dit.core.githook import install_hook
from dit.core.repo import DIT_DIR_NAME, find_repo


@click.command("init")
@click.option("--bucket", help="S3 バケット名（新規作成時）")
@click.option("--prefix", help="バケット内のキープレフィックス（新規作成時）")
@click.option("--force-hook", is_flag=True, help="管理外の pre-commit フックを上書きする")
def init_cmd(
    bucket: str | None,
    prefix: str | None,
    *,
    force_hook: bool,
) -> None:
    """dit.toml / .dit/ / pre-commit フックを初期化する."""
    repo = find_repo()
    if not (repo.root / ".git").exists():
        msg = f"not a git repository: {repo.root}"
        raise RepoError(msg)

    if repo.dit_toml.exists():
        load_config(repo)
        click.echo(f"already initialized: {repo.dit_toml}")
    else:
        if bucket is None or prefix is None:
            msg = "--bucket and --prefix are required when dit.toml is missing"
            raise click.UsageError(msg)
        config = init_config(bucket=bucket, prefix=prefix)
        config.save(repo.dit_toml)
        click.echo(f"wrote {repo.dit_toml}")

    dit_dir = repo.root / DIT_DIR_NAME
    dit_dir.mkdir(parents=True, exist_ok=True)
    gitignore = dit_dir / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("*\n", encoding="utf-8")
        click.echo(f"wrote {gitignore}")

    try:
        hook = install_hook(repo.root, force=force_hook)
        click.echo(f"installed hook: {hook}")
    except FileExistsError as exc:
        raise click.ClickException(str(exc)) from exc
