"""psd schema サブコマンド"""

import click

from cli.output import OutputFormatter
from cli.schema_gen import generate_command_schema, list_available_commands


@click.command("schema")
@click.argument("command_path", required=False)
@click.pass_context
def schema_cmd(ctx, command_path: str | None):
    """Show JSON schema for a command. Use 'psd schema' to list all commands."""
    fmt = ctx.obj.get("output", "text") if ctx.obj else "text"
    fields = ctx.obj.get("fields") if ctx.obj else None

    root = ctx.find_root().command

    if command_path is None:
        commands = list_available_commands(root)
        data = {"available_commands": commands}
        click.echo(OutputFormatter.format(data, fmt, fields=fields))
        return

    schema = generate_command_schema(command_path, root)
    if schema is None:
        click.echo(
            OutputFormatter.format_error(
                f"Unknown command: {command_path}",
                fmt,
                code="UNKNOWN_COMMAND",
                suggestions=list_available_commands(root),
            ),
            err=True,
        )
        ctx.exit(1)
        return

    click.echo(OutputFormatter.format(schema, fmt, fields=fields))
