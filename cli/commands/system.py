"""psd system サブコマンド群（ping）"""

import asyncio
import logging

import click

from cli.output import OutputFormatter
from photoshop_sdk.client import PhotoshopClient
from photoshop_sdk.exceptions import (
    ConnectionError as PSConnectionError,
    PhotoshopSDKError,
    TimeoutError as PSTimeoutError,
)

logger = logging.getLogger(__name__)


def _run_async(coro):
    """CLI から async 関数を実行するヘルパー"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _handle_client_error(ctx, e: Exception, fmt: str) -> None:
    """共通エラーハンドリング（exit code 付き）"""
    if isinstance(e, PSConnectionError):
        click.echo(
            OutputFormatter.format_error(str(e), fmt, code="CONNECTION_ERROR"),
            err=True,
        )
        ctx.exit(2)
    elif isinstance(e, PSTimeoutError):
        click.echo(
            OutputFormatter.format_error(str(e), fmt, code="TIMEOUT_ERROR"),
            err=True,
        )
        ctx.exit(3)
    elif isinstance(e, PhotoshopSDKError):
        click.echo(
            OutputFormatter.format_error(str(e), fmt, code=e.code or "SDK_ERROR"),
            err=True,
        )
        ctx.exit(1)
    else:
        click.echo(
            OutputFormatter.format_error(str(e), fmt, code="ERROR"),
            err=True,
        )
        ctx.exit(1)


@click.group(name="system")
def system_cmd():
    """System operations (ping, health check)"""
    pass


@system_cmd.command("ping")
@click.pass_context
def system_ping(ctx):
    """Check connection to Photoshop UXP Plugin"""
    fmt = ctx.obj.get("output", "text") if ctx.obj else "text"
    fields = ctx.obj.get("fields") if ctx.obj else None

    async def _run():
        client = PhotoshopClient()
        try:
            await client.start()
            result = await client.ping()
            click.echo(OutputFormatter.format(result, fmt, fields=fields))
        except Exception as e:
            _handle_client_error(ctx, e, fmt)
        finally:
            await client.stop()

    _run_async(_run())
