"""Generate the public CLI reference directly from Click command objects."""

from __future__ import annotations

import inspect

import click

from dit.docs.common import project_root, replace_markdown_directory
from dit.main import create_cli


def _text(value: str | None) -> str:
    if not value:
        return ""
    return inspect.cleandoc(value).replace("\b", "").strip()


def _cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def _parameter_name(parameter: click.Parameter) -> str:
    if isinstance(parameter, click.Option):
        return ", ".join(f"`{name}`" for name in (*parameter.opts, *parameter.secondary_opts))
    return f"`{parameter.name}`"


def _parameter_default(parameter: click.Parameter, context: click.Context) -> str:
    default = parameter.get_default(context)
    if default is None or (
        default.__class__.__module__ == "click._utils" and getattr(default, "name", None) == "UNSET"
    ):
        return "—"
    if isinstance(default, bool):
        return "true" if default else "false"
    return _cell(default)


def _parameters(command: click.Command, context: click.Context) -> list[str]:
    parameters = command.get_params(context)
    if not parameters:
        return []
    rows = [
        "| Parameter | Type | Required | Default | Description |",
        "|---|---|---:|---|---|",
    ]
    rows.extend(
        (
            "| "
            + " | ".join(
                (
                    _parameter_name(parameter),
                    _cell(parameter.type.name),
                    "yes" if parameter.required else "no",
                    _parameter_default(parameter, context),
                    _cell(getattr(parameter, "help", None) or "—"),
                )
            )
            + " |"
        )
        for parameter in parameters
    )
    return rows


def _usage(command: click.Command, context: click.Context) -> str:
    pieces = command.collect_usage_pieces(context)
    return " ".join((context.command_path, *pieces))


def _section(command: click.Command, path: tuple[str, ...], level: int) -> list[str]:
    info_name = path[-1]
    parent = None
    if len(path) > 1:
        parent = click.Context(create_cli(), info_name="dit")
    context = click.Context(command, info_name=info_name, parent=parent)
    if len(path) > 2:  # noqa: PLR2004
        context.parent = click.Context(click.Command(path[-2]), info_name=path[-2], parent=parent)

    lines = [f"{'#' * level} `{' '.join(path)}`", ""]
    description = _text(command.help)
    if description:
        lines.extend((description, ""))
    lines.extend(("```console", f"$ {_usage(command, context)}", "```", ""))
    parameter_lines = _parameters(command, context)
    if parameter_lines:
        lines.extend((f"{'#' * (level + 1)} Parameters", "", *parameter_lines, ""))
    return lines


def render_reference(cli: click.Group) -> dict[str, str]:
    """Render one index and one page per top-level command."""
    names = cli.list_commands(click.Context(cli, info_name="dit"))
    index = [
        "# CLI Reference",
        "",
        "`dit` の公開インターフェースです。このページ群はClick定義から自動生成されています。",
        "",
        "| Command | Description |",
        "|---|---|",
    ]
    pages: dict[str, str] = {}
    for name in names:
        command = cli.get_command(click.Context(cli, info_name="dit"), name)
        if command is None:
            continue
        description = command.short_help or _text(command.help).splitlines()[0]
        index.append(f"| [`dit {name}`]({name}.md) | {_cell(description)} |")
        lines = _section(command, ("dit", name), 1)
        if isinstance(command, click.Group):
            sub_context = click.Context(command, info_name=name)
            for sub_name in command.list_commands(sub_context):
                subcommand = command.get_command(sub_context, sub_name)
                if subcommand is not None:
                    lines.extend(_section(subcommand, ("dit", name, sub_name), 2))
        pages[f"{name}.md"] = "\n".join(lines)
    pages["index.md"] = "\n".join(index) + "\n"
    return pages


def generate_reference() -> None:
    """Generate the complete CLI reference directory."""
    replace_markdown_directory(
        project_root() / "docs" / "reference", render_reference(create_cli())
    )


def main() -> None:
    """CLI entry point for reference generation."""
    generate_reference()
