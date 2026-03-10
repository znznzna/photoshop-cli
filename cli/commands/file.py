"""psd file サブコマンド群（open / close / save / info / list）"""

import asyncio
import logging

import click

from cli.output import OutputFormatter
from photoshop_sdk.client import PhotoshopClient
from photoshop_sdk.exceptions import (
    ConnectionError as PSConnectionError,
    PhotoshopSDKError,
    TimeoutError as PSTimeoutError,
    ValidationError as PSValidationError,
)
from photoshop_sdk.validators import validate_file_path

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
    if isinstance(e, PSValidationError):
        click.echo(
            OutputFormatter.format_error(str(e), fmt, code="VALIDATION_ERROR"),
            err=True,
        )
        ctx.exit(4)
    elif isinstance(e, PSConnectionError):
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


@click.group(name="file")
def file_cmd():
    """File operations (open, close, save, info, list)"""
    pass


@file_cmd.command("list")
@click.pass_context
def file_list(ctx):
    """List all open Photoshop documents"""
    fmt = ctx.obj.get("output", "text") if ctx.obj else "text"
    timeout = ctx.obj.get("timeout", 30.0) if ctx.obj else 30.0

    async def _run():
        client = PhotoshopClient()
        try:
            await client.start()
            docs = await client.file_list(timeout=timeout)
            data = [doc.model_dump() for doc in docs]
            click.echo(OutputFormatter.format(data, fmt))
        except Exception as e:
            _handle_client_error(ctx, e, fmt)
        finally:
            await client.stop()

    _run_async(_run())


@file_cmd.command("info")
@click.option("--doc-id", required=True, type=int, help="Document ID")
@click.pass_context
def file_info(ctx, doc_id: int):
    """Get info for a specific document"""
    fmt = ctx.obj.get("output", "text") if ctx.obj else "text"
    timeout = ctx.obj.get("timeout", 30.0) if ctx.obj else 30.0

    async def _run():
        client = PhotoshopClient()
        try:
            await client.start()
            doc = await client.file_info(doc_id=doc_id, timeout=timeout)
            click.echo(OutputFormatter.format(doc.model_dump(), fmt))
        except Exception as e:
            _handle_client_error(ctx, e, fmt)
        finally:
            await client.stop()

    _run_async(_run())


@file_cmd.command("open")
@click.argument("path")
@click.pass_context
def file_open(ctx, path: str):
    """Open a PSD file in Photoshop"""
    fmt = ctx.obj.get("output", "text") if ctx.obj else "text"
    timeout = ctx.obj.get("timeout", 30.0) if ctx.obj else 30.0

    # ローカルバリデーション（Photoshop に送信する前に検証）
    try:
        resolved = validate_file_path(path)
        path = str(resolved)
    except PSValidationError as e:
        click.echo(
            OutputFormatter.format_error(str(e), fmt, code=e.code or "VALIDATION_ERROR"),
            err=True,
        )
        ctx.exit(4)
        return

    async def _run():
        client = PhotoshopClient()
        try:
            await client.start()
            result = await client.file_open(path=path, timeout=timeout)
            click.echo(OutputFormatter.format(result, fmt))
        except Exception as e:
            _handle_client_error(ctx, e, fmt)
        finally:
            await client.stop()

    _run_async(_run())


@file_cmd.command("close")
@click.option("--doc-id", required=True, type=int, help="Document ID to close")
@click.option("--save", is_flag=True, default=False, help="Save before closing")
@click.pass_context
def file_close(ctx, doc_id: int, save: bool):
    """Close a document"""
    fmt = ctx.obj.get("output", "text") if ctx.obj else "text"
    timeout = ctx.obj.get("timeout", 30.0) if ctx.obj else 30.0

    async def _run():
        client = PhotoshopClient()
        try:
            await client.start()
            result = await client.file_close(doc_id=doc_id, save=save, timeout=timeout)
            click.echo(OutputFormatter.format(result, fmt))
        except Exception as e:
            _handle_client_error(ctx, e, fmt)
        finally:
            await client.stop()

    _run_async(_run())


@file_cmd.command("save")
@click.option("--doc-id", required=True, type=int, help="Document ID to save")
@click.pass_context
def file_save(ctx, doc_id: int):
    """Save a document"""
    fmt = ctx.obj.get("output", "text") if ctx.obj else "text"
    timeout = ctx.obj.get("timeout", 30.0) if ctx.obj else 30.0

    async def _run():
        client = PhotoshopClient()
        try:
            await client.start()
            result = await client.file_save(doc_id=doc_id, timeout=timeout)
            click.echo(OutputFormatter.format(result, fmt))
        except Exception as e:
            _handle_client_error(ctx, e, fmt)
        finally:
            await client.stop()

    _run_async(_run())
