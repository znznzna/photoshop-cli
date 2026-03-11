"""CLI コマンド自動生成機構

CommandSchema から Click CLI コマンドを自動生成する。
手動で各コマンドを書く代わりに、スキーマ定義だけで CLI コマンドを構築可能にする。
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

import click

from cli.output import OutputFormatter
from photoshop_sdk.schema import COMMAND_SCHEMAS, CommandSchema

logger = logging.getLogger(__name__)

# エラーカテゴリ → exit code マッピング
_EXIT_CODE_MAP = {
    "connection": 2,
    "timeout": 3,
    "validation": 4,
    "not_found": 5,
}

# バリデーター名 → 関数の遅延解決マップ
_VALIDATOR_MAP = {
    "validate_file_path": "photoshop_sdk.validators.validate_file_path",
}


def _get_connection_manager():
    """ConnectionManager をレイジーインポートして生成する"""
    from mcp_server.connection import ConnectionManager

    return ConnectionManager()


def _run_async(coro):
    """CLI から async 関数を同期的に実行するヘルパー"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _resolve_validator(validator_name: str | None):
    """バリデーター名から関数を解決する"""
    if validator_name is None:
        return None
    dotted = _VALIDATOR_MAP.get(validator_name)
    if dotted is None:
        logger.warning("Unknown validator: %s", validator_name)
        return None
    module_path, func_name = dotted.rsplit(".", 1)
    import importlib

    mod = importlib.import_module(module_path)
    return getattr(mod, func_name)


def _parse_json_option(value: str | None, param_name: str) -> Any:
    """JSON 文字列をパースする。エラー時は位置情報付きのメッセージを返す。

    Args:
        value: JSON 文字列。None または空文字列の場合は None を返す。
        param_name: エラーメッセージ用のパラメータ名。

    Returns:
        パースされた Python オブジェクト、または None。

    Raises:
        click.BadParameter: JSON パースエラー時。
    """
    if value is None or value == "":
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError as e:
        raise click.BadParameter(
            f"Invalid JSON for '{param_name}': {e.msg} (line {e.lineno}, column {e.colno}). "
            f"Hint: Ensure the JSON is properly quoted and escaped.",
            param_hint=f"--{param_name.replace('_', '-')}",
        )


def _resolve_json_file_params(params: dict[str, Any]) -> dict[str, Any]:
    """*_file パラメータを解決し、ファイル内容で対応するパラメータを上書きする。

    例: params に {"style_file": "/path/to/style.json"} がある場合、
    ファイルを読み込んで params["style"] にセットし、"style_file" キーを削除する。

    Args:
        params: Click から受け取ったパラメータ辞書。

    Returns:
        解決済みのパラメータ辞書。

    Raises:
        click.BadParameter: ファイルが見つからない、または JSON パースエラー時。
    """
    result = dict(params)
    file_keys = [k for k in result if k.endswith("_file")]

    for file_key in file_keys:
        file_path = result.pop(file_key, None)
        if file_path is None:
            continue

        base_key = file_key[: -len("_file")]  # "style_file" → "style"
        path = Path(file_path)

        if not path.exists():
            raise click.BadParameter(
                f"File not found: {file_path}",
                param_hint=f"--{file_key.replace('_', '-')}",
            )

        try:
            content = path.read_text(encoding="utf-8")
            parsed = json.loads(content)
        except json.JSONDecodeError as e:
            raise click.BadParameter(
                f"Invalid JSON in file '{file_path}': {e.msg} (line {e.lineno}, column {e.colno})",
                param_hint=f"--{file_key.replace('_', '-')}",
            )

        result[base_key] = parsed

    return result


def _build_sdk_params(schema: CommandSchema, cli_params: dict[str, Any]) -> dict[str, Any]:
    """CLI パラメータを SDK パラメータに変換する。

    - effective_sdk_name でキー名を変換
    - required=False かつデフォルト値と同じ場合は除外
    - dict/list 型は JSON 文字列をパースする
    """
    sdk_params: dict[str, Any] = {}

    for p_schema in schema.params:
        value = cli_params.get(p_schema.name)

        # dict/list パラメータは JSON 文字列をパース
        if p_schema.type in (dict, list) and isinstance(value, str):
            value = _parse_json_option(value, p_schema.name)

        # required=False かつ値がデフォルトと同じ場合はスキップ
        if not p_schema.required and value == p_schema.default:
            continue

        # None のパラメータはスキップ（未指定）
        if value is None and not p_schema.required:
            continue

        sdk_params[p_schema.effective_sdk_name] = value

    return sdk_params


def _determine_exit_code(error: dict[str, Any]) -> int:
    """エラー応答から exit code を決定する"""
    category = error.get("category", "")
    return _EXIT_CODE_MAP.get(category, 1)


def build_click_command(schema: CommandSchema) -> click.Command:
    """CommandSchema から click.Command を生成する。

    Args:
        schema: コマンドスキーマ定義。

    Returns:
        生成された click.Command インスタンス。
    """
    # コマンド名は "file.list" → "list"
    cmd_name = schema.command.split(".")[-1]

    # Click パラメータを構築
    click_params: list[click.Parameter] = []

    for p in schema.params:
        if p.type is bool:
            # bool → --foo/--no-foo フラグパターン
            opt_name = p.name.replace("_", "-")
            click_params.append(
                click.Option(
                    [f"--{opt_name}/--no-{opt_name}"],
                    default=p.default if not p.required else None,
                    required=p.required,
                    help=p.description,
                    is_flag=True,
                )
            )
        elif p.type in (dict, list):
            # dict/list → --param (JSON string) + --param-file (file path)
            opt_name = p.name.replace("_", "-")
            click_params.append(
                click.Option(
                    [f"--{opt_name}"],
                    type=str,
                    default=None,
                    required=False,  # file でも渡せるので required=False
                    help=f"{p.description} (JSON string)",
                )
            )
            click_params.append(
                click.Option(
                    [f"--{opt_name}-file"],
                    type=str,
                    default=None,
                    required=False,
                    help=f"{p.description} (path to JSON file)",
                )
            )
        else:
            # str, int, float → 通常の --option
            opt_name = p.name.replace("_", "-")
            click_type = p.type
            click_params.append(
                click.Option(
                    [f"--{opt_name}"],
                    type=click_type,
                    default=p.default if not p.required else None,
                    required=p.required,
                    help=p.description,
                )
            )

    def command_callback(**kwargs):
        ctx = click.get_current_context()
        ctx.ensure_object(dict)

        fmt = ctx.obj.get("output", "text")
        fields = ctx.obj.get("fields")
        dry_run = ctx.obj.get("dry_run", False)
        cli_timeout = ctx.obj.get("timeout")

        # --param-file の解決
        try:
            kwargs = _resolve_json_file_params(kwargs)
        except click.BadParameter as e:
            click.echo(
                OutputFormatter.format_error(str(e), fmt, code="VALIDATION_ERROR"),
                err=True,
            )
            ctx.exit(4)
            return

        # バリデーター実行
        if schema.validator:
            validator_fn = _resolve_validator(schema.validator)
            if validator_fn:
                # バリデーターに渡すパラメータを特定（バリデーター名からヒント）
                for p in schema.params:
                    val = kwargs.get(p.name)
                    if val is not None:
                        try:
                            validated = validator_fn(val)
                            # バリデーターが値を変換した場合は更新
                            if validated is not None:
                                kwargs[p.name] = str(validated) if p.type is str else validated
                        except Exception as e:
                            from photoshop_sdk.exceptions import ValidationError as PSValidationError

                            if isinstance(e, PSValidationError):
                                click.echo(
                                    OutputFormatter.format_error(
                                        str(e), fmt, code=e.code or "VALIDATION_ERROR"
                                    ),
                                    err=True,
                                )
                                ctx.exit(4)
                                return
                            raise

        # SDK パラメータ構築
        sdk_params = _build_sdk_params(schema, kwargs)

        # タイムアウト: CLI 指定 > スキーマ定義
        timeout = cli_timeout if cli_timeout and cli_timeout != 30.0 else schema.timeout

        # dry-run チェック
        if dry_run and schema.supports_dry_run:
            dry_run_output = {
                "dry_run": True,
                "command": schema.command,
                "params": sdk_params,
                "timeout": timeout,
                "message": f"Validation passed. This command would execute '{schema.command}'.",
            }
            click.echo(OutputFormatter.format(dry_run_output, fmt, fields=fields))
            return

        # 実行
        cm = _get_connection_manager()

        async def _execute():
            return await cm.execute(schema.command, sdk_params, timeout=timeout)

        result = _run_async(_execute())

        if result.get("success"):
            click.echo(OutputFormatter.format(result, fmt, fields=fields))
        else:
            error = result.get("error", {})
            exit_code = _determine_exit_code(error)
            click.echo(
                OutputFormatter.format_error(
                    error.get("message", "Unknown error"),
                    fmt,
                    code=error.get("code", "ERROR"),
                    command=schema.command,
                ),
                err=True,
            )
            ctx.exit(exit_code)

    cmd = click.Command(
        name=cmd_name,
        callback=command_callback,
        params=click_params,
        help=schema.description,
    )
    # click.pass_context 相当の設定（callback が ctx を使うため）
    # click.get_current_context() で取得するので不要

    return cmd


def register_group_commands(
    group: click.Group,
    group_name: str,
    schemas: list[CommandSchema] | None = None,
) -> None:
    """指定グループに属するコマンドを Click グループに登録する。

    Args:
        group: Click グループインスタンス。
        group_name: グループ名（例: "file"）。コマンド名の "file.list" のドット前部分でフィルタ。
        schemas: コマンドスキーマリスト。None の場合は COMMAND_SCHEMAS を使用。
    """
    if schemas is None:
        schemas = COMMAND_SCHEMAS

    for schema in schemas:
        prefix = schema.command.split(".")[0]
        if prefix == group_name:
            cmd = build_click_command(schema)
            group.add_command(cmd)
