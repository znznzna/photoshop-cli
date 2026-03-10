import logging
import os

import click

from cli.output import OutputFormatter


def resolve_output_format(output: str | None) -> str:
    if output is not None:
        return output
    # TTY でなければ json、TTY なら text
    import sys
    return "json" if not sys.stdout.isatty() else "text"


def resolve_timeout(timeout: float | None) -> float:
    return timeout if timeout is not None else 30.0


@click.group()
@click.version_option(version="0.1.0", prog_name="psd")
@click.option(
    "--output",
    "-o",
    type=click.Choice(["json", "text", "table"]),
    default=None,
    help="Output format (default: json for non-TTY, text for TTY)",
)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.option(
    "--timeout",
    "-t",
    type=float,
    default=None,
    help="Default command timeout in seconds",
)
@click.pass_context
def cli(ctx, output, verbose, timeout):
    """Adobe Photoshop CLI - control Photoshop from the command line."""
    ctx.ensure_object(dict)
    ctx.obj["output"] = resolve_output_format(output)
    ctx.obj["verbose"] = verbose or bool(os.environ.get("PS_VERBOSE"))
    ctx.obj["timeout"] = resolve_timeout(timeout)

    if ctx.obj["verbose"]:
        logging.basicConfig(level=logging.DEBUG, force=True)
    elif ctx.obj["output"] == "json":
        logging.basicConfig(level=logging.ERROR, force=True)
    else:
        logging.basicConfig(level=logging.WARNING, force=True)


# コマンドグループの登録
from cli.commands.file import file_cmd  # noqa: E402

cli.add_command(file_cmd)
