"""dit init command."""

from __future__ import annotations

import click

from dit.core.config import default_init_config
from dit.core.errors import RepoError
from dit.core.githook import install_hook
from dit.core.repo import DIT_DIR_NAME, find_repo


@click.command("init")
@click.option("--remote-url", default=None, help="s3://bucket/prefix")
@click.option("--endpoint-url", default=None, help="S3-compatible endpoint URL")
@click.option("--force-hook", is_flag=True, help="overwrite unmanaged pre-commit hook")
def init_cmd(
    remote_url: str | None,
    endpoint_url: str | None,
    *,
    force_hook: bool,
) -> None:
    """Initialize dit.toml, .dit/, and the pre-commit hook."""
    repo = find_repo()
    if not (repo.root / ".git").exists():
        msg = f"not a git repository: {repo.root}"
        raise RepoError(msg)

    if repo.dit_toml.exists():
        click.echo(f"already initialized: {repo.dit_toml}")
    else:
        config = default_init_config(remote_url=remote_url, endpoint_url=endpoint_url)
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
