# Full Commands Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Photoshop UXP SDK の全 API（~108コマンド）をCLI/MCPコマンドとして実装する
**Architecture:** CommandSchema駆動のCLI自動生成基盤を構築し、11コマンドグループを段階的に実装。UXP Plugin のWebSocketリーク修正も含む。
**Tech Stack:** Python 3.10+, Click 8.x, Pydantic 2.x, websockets 12.x, FastMCP 3.x, TypeScript 5.x
**Design Doc:** `docs/plans/2026-03-11-full-commands-design.md`

---

## Phase Overview

| Phase | 内容 | 見積り |
|---|---|---|
| Phase 1 | 基盤整備（CLI自動生成、WS修正、例外拡張、file→document並行公開） | 2-3日 |
| Phase 2 | Document拡張 + Layer + Selection + Path | 3-4日 |
| Phase 3 | Text | 1-2日 |
| Phase 4 | Filter（typed 15種 + 汎用 apply） | 4-5日 |
| Phase 5 | Channel + Guide + History + Action + App | 3-4日 |
| Phase 6 | 統合テスト + ドキュメント | 1-2日 |

---

## Phase 1: 基盤整備（2-3日）

**目標**: コマンド自動生成基盤の構築、UXP WebSocketリーク修正、例外クラス拡張、file/document 並行公開

---

### Task 1.1: CLI コマンド自動生成機構

**Files:**
- Create: `cli/auto_commands.py`
- Test: `tests/unit/cli/test_auto_commands.py`

**Step 1: 失敗するテストを書く**

```python
# tests/unit/cli/test_auto_commands.py
"""auto_commands: CommandSchema → Click コマンド自動生成のテスト"""

import json
import os
from unittest.mock import AsyncMock, patch

import click
import pytest
from click.testing import CliRunner

from photoshop_sdk.schema import CommandSchema, ParamSchema


class TestBuildClickCommand:
    """build_click_command() のユニットテスト"""

    def test_simple_command_no_params(self):
        """パラメータなしコマンドが生成される"""
        from cli.auto_commands import build_click_command

        schema = CommandSchema(
            command="test.list",
            description="List all items.",
        )
        cmd = build_click_command(schema)
        assert isinstance(cmd, click.Command)
        assert cmd.name == "list"
        assert "List all items." in (cmd.help or "")

    def test_int_param_becomes_click_option(self):
        """int パラメータが --option 形式で生成される"""
        from cli.auto_commands import build_click_command

        schema = CommandSchema(
            command="test.info",
            description="Get info.",
            params=[
                ParamSchema(name="doc_id", type=int, description="Document ID", sdk_name="documentId"),
            ],
        )
        cmd = build_click_command(schema)
        param_names = [p.name for p in cmd.params]
        assert "doc_id" in param_names

    def test_bool_param_becomes_flag_pair(self):
        """bool パラメータが --foo/--no-foo 形式で生成される"""
        from cli.auto_commands import build_click_command

        schema = CommandSchema(
            command="test.close",
            description="Close item.",
            params=[
                ParamSchema(name="doc_id", type=int, description="Document ID"),
                ParamSchema(name="save", type=bool, description="Save before closing", required=False, default=False),
            ],
        )
        cmd = build_click_command(schema)

        # save パラメータが存在すること
        save_param = next((p for p in cmd.params if p.name == "save"), None)
        assert save_param is not None
        # bool フラグはsecondaryが設定される（--save/--no-save）
        assert save_param.secondary is True or isinstance(save_param, click.Option)

    def test_str_param_becomes_click_option(self):
        """str パラメータが --option 形式で生成される"""
        from cli.auto_commands import build_click_command

        schema = CommandSchema(
            command="test.open",
            description="Open item.",
            params=[
                ParamSchema(name="path", type=str, description="File path"),
            ],
        )
        cmd = build_click_command(schema)
        param_names = [p.name for p in cmd.params]
        assert "path" in param_names

    def test_optional_param_has_default(self):
        """required=False のパラメータにデフォルト値が設定される"""
        from cli.auto_commands import build_click_command

        schema = CommandSchema(
            command="test.resize",
            description="Resize item.",
            params=[
                ParamSchema(name="doc_id", type=int, description="Document ID"),
                ParamSchema(name="width", type=int, description="Width", required=False, default=None),
            ],
        )
        cmd = build_click_command(schema)
        width_param = next((p for p in cmd.params if p.name == "width"), None)
        assert width_param is not None
        assert width_param.required is False

    def test_dict_param_generates_json_and_file_options(self):
        """dict パラメータが --param と --param-file の両方を生成する"""
        from cli.auto_commands import build_click_command

        schema = CommandSchema(
            command="test.apply",
            description="Apply filter.",
            params=[
                ParamSchema(name="doc_id", type=int, description="Document ID"),
                ParamSchema(name="params", type=dict, description="Filter parameters", required=False, default=None),
            ],
        )
        cmd = build_click_command(schema)
        param_names = [p.name for p in cmd.params]
        assert "params" in param_names
        assert "params_file" in param_names

    def test_list_param_generates_json_and_file_options(self):
        """list パラメータが --param と --param-file の両方を生成する"""
        from cli.auto_commands import build_click_command

        schema = CommandSchema(
            command="test.batch",
            description="Batch apply.",
            params=[
                ParamSchema(name="filters", type=list, description="Filter list", required=False, default=None),
            ],
        )
        cmd = build_click_command(schema)
        param_names = [p.name for p in cmd.params]
        assert "filters" in param_names
        assert "filters_file" in param_names

    def test_mutating_dry_run_command_has_dry_run_from_context(self):
        """mutating + supports_dry_run のコマンドは ctx から dry_run を取得する"""
        from cli.auto_commands import build_click_command

        schema = CommandSchema(
            command="test.save",
            description="Save item.",
            params=[
                ParamSchema(name="doc_id", type=int, description="Document ID"),
            ],
            mutating=True,
            supports_dry_run=True,
        )
        cmd = build_click_command(schema)
        # dry_run は ctx.obj から取得するのでコマンドパラメータには含まない
        param_names = [p.name for p in cmd.params]
        assert "dry_run" not in param_names


class TestParseJsonOption:
    """_parse_json_option() のテスト"""

    def test_valid_json_string(self):
        """有効なJSON文字列がパースされる"""
        from cli.auto_commands import _parse_json_option

        result = _parse_json_option(None, type("P", (), {"name": "params"})(), '{"radius": 5}')
        assert result == {"radius": 5}

    def test_none_returns_none(self):
        """None が渡されたら None を返す"""
        from cli.auto_commands import _parse_json_option

        result = _parse_json_option(None, type("P", (), {"name": "params"})(), None)
        assert result is None

    def test_invalid_json_raises_bad_parameter(self):
        """無効なJSONが click.BadParameter を発生させる"""
        from cli.auto_commands import _parse_json_option

        with pytest.raises(click.BadParameter) as exc_info:
            _parse_json_option(None, type("P", (), {"name": "params"})(), '{"radius": 5 "amount": 10}')
        assert "Invalid JSON" in str(exc_info.value)
        assert "--params-file" in str(exc_info.value)

    def test_empty_string_raises_bad_parameter(self):
        """空文字列が click.BadParameter を発生させる"""
        from cli.auto_commands import _parse_json_option

        with pytest.raises(click.BadParameter):
            _parse_json_option(None, type("P", (), {"name": "params"})(), "")


class TestResolveJsonFileParams:
    """_resolve_json_file_params() のテスト"""

    def test_no_file_params_passes_through(self):
        """_file パラメータがなければそのまま返す"""
        from cli.auto_commands import _resolve_json_file_params

        kwargs = {"doc_id": 1, "name": "test"}
        result = _resolve_json_file_params(kwargs)
        assert result == {"doc_id": 1, "name": "test"}

    def test_file_param_reads_json_file(self, tmp_path):
        """_file パラメータがあればファイルを読み込む"""
        from cli.auto_commands import _resolve_json_file_params

        json_file = tmp_path / "params.json"
        json_file.write_text('{"radius": 5, "amount": 10}')

        kwargs = {"doc_id": 1, "params": None, "params_file": str(json_file)}
        result = _resolve_json_file_params(kwargs)
        assert result == {"doc_id": 1, "params": {"radius": 5, "amount": 10}}

    def test_file_param_overrides_inline(self, tmp_path):
        """_file パラメータが指定されていれば inline パラメータを上書きする"""
        from cli.auto_commands import _resolve_json_file_params

        json_file = tmp_path / "params.json"
        json_file.write_text('{"radius": 99}')

        kwargs = {"doc_id": 1, "params": {"radius": 5}, "params_file": str(json_file)}
        result = _resolve_json_file_params(kwargs)
        assert result["params"] == {"radius": 99}

    def test_invalid_json_file_raises_bad_parameter(self, tmp_path):
        """無効なJSONファイルが click.BadParameter を発生させる"""
        from cli.auto_commands import _resolve_json_file_params

        bad_file = tmp_path / "bad.json"
        bad_file.write_text("{invalid json")

        with pytest.raises(click.BadParameter) as exc_info:
            _resolve_json_file_params({"params": None, "params_file": str(bad_file)})
        assert "Invalid JSON" in str(exc_info.value)

    def test_nonexistent_file_raises_bad_parameter(self):
        """存在しないファイルが click.BadParameter を発生させる"""
        from cli.auto_commands import _resolve_json_file_params

        with pytest.raises(click.BadParameter) as exc_info:
            _resolve_json_file_params({"params": None, "params_file": "/nonexistent/file.json"})
        assert "Cannot read file" in str(exc_info.value)

    def test_null_file_param_ignored(self):
        """_file パラメータが None の場合は無視される"""
        from cli.auto_commands import _resolve_json_file_params

        kwargs = {"doc_id": 1, "params": {"radius": 5}, "params_file": None}
        result = _resolve_json_file_params(kwargs)
        assert result == {"doc_id": 1, "params": {"radius": 5}}


class TestRegisterGroupCommands:
    """register_group_commands() のテスト"""

    def test_registers_matching_commands(self):
        """指定グループに一致するコマンドのみ登録される"""
        from cli.auto_commands import register_group_commands

        group = click.Group("test_group")
        schemas = [
            CommandSchema(command="document.list", description="List docs"),
            CommandSchema(command="document.info", description="Get doc info",
                          params=[ParamSchema(name="doc_id", type=int, description="Doc ID")]),
            CommandSchema(command="layer.list", description="List layers"),
        ]
        register_group_commands(group, "document", schemas=schemas)

        cmd_names = list(group.commands.keys())
        assert "list" in cmd_names
        assert "info" in cmd_names
        assert len(cmd_names) == 2  # layer.list は登録されない


class TestAutoCommandExecution:
    """自動生成コマンドの実行テスト（Click CliRunner）"""

    def _make_cli_with_auto_command(self, schema):
        """テスト用にスキーマから CLI を構築する"""
        from cli.auto_commands import build_click_command

        @click.group()
        @click.option("--output", "-o", type=click.Choice(["json", "text"]), default="json")
        @click.option("--dry-run", is_flag=True, default=False)
        @click.option("--timeout", type=float, default=30.0)
        @click.option("--fields", type=str, default=None)
        @click.pass_context
        def test_cli(ctx, output, dry_run, timeout, fields):
            ctx.ensure_object(dict)
            ctx.obj["output"] = output
            ctx.obj["dry_run"] = dry_run
            ctx.obj["timeout"] = timeout
            ctx.obj["fields"] = [f.strip() for f in fields.split(",") if f.strip()] if fields else None

        test_group = click.Group("test")
        cmd = build_click_command(schema)
        test_group.add_command(cmd)
        test_cli.add_command(test_group)
        return test_cli

    def test_auto_command_executes_with_mock(self):
        """自動生成コマンドがモッククライアントで実行される"""
        schema = CommandSchema(
            command="test.list",
            description="List items.",
        )
        test_cli = self._make_cli_with_auto_command(schema)
        runner = CliRunner()

        mock_conn_mgr = AsyncMock()
        mock_conn_mgr.execute.return_value = {"items": [{"id": 1}, {"id": 2}]}

        with patch("cli.auto_commands._get_connection_manager", return_value=mock_conn_mgr):
            result = runner.invoke(test_cli, ["--output", "json", "test", "list"])

        assert result.exit_code == 0, f"Exit code: {result.exit_code}, Output: {result.output}"

    def test_auto_command_bool_flag(self):
        """bool パラメータが --save/--no-save で動作する"""
        schema = CommandSchema(
            command="test.close",
            description="Close item.",
            params=[
                ParamSchema(name="doc_id", type=int, description="Document ID"),
                ParamSchema(name="save", type=bool, description="Save", required=False, default=False),
            ],
        )
        test_cli = self._make_cli_with_auto_command(schema)
        runner = CliRunner()

        mock_conn_mgr = AsyncMock()
        mock_conn_mgr.execute.return_value = {"closed": True}

        with patch("cli.auto_commands._get_connection_manager", return_value=mock_conn_mgr):
            result = runner.invoke(test_cli, ["--output", "json", "test", "close", "--doc-id", "1", "--save"])

        assert result.exit_code == 0, f"Output: {result.output}"
        # execute が save=True で呼ばれたことを確認
        call_args = mock_conn_mgr.execute.call_args
        assert call_args is not None

    def test_auto_command_dry_run(self):
        """dry-run モードが動作する"""
        schema = CommandSchema(
            command="test.save",
            description="Save item.",
            params=[
                ParamSchema(name="doc_id", type=int, description="Document ID"),
            ],
            mutating=True,
            supports_dry_run=True,
        )
        test_cli = self._make_cli_with_auto_command(schema)
        runner = CliRunner()

        result = runner.invoke(test_cli, ["--output", "json", "--dry-run", "test", "save", "--doc-id", "1"])

        assert result.exit_code == 0, f"Output: {result.output}"
        data = json.loads(result.output)
        assert data["dry_run"] is True
        assert data["command"] == "test.save"

    def test_auto_command_json_param(self, tmp_path):
        """dict パラメータが JSON 文字列として渡せる"""
        schema = CommandSchema(
            command="test.apply",
            description="Apply filter.",
            params=[
                ParamSchema(name="doc_id", type=int, description="Document ID"),
                ParamSchema(name="params", type=dict, description="Filter params", required=False, default=None),
            ],
        )
        test_cli = self._make_cli_with_auto_command(schema)
        runner = CliRunner()

        mock_conn_mgr = AsyncMock()
        mock_conn_mgr.execute.return_value = {"applied": True}

        with patch("cli.auto_commands._get_connection_manager", return_value=mock_conn_mgr):
            result = runner.invoke(
                test_cli,
                ["--output", "json", "test", "apply", "--doc-id", "1", "--params", '{"radius": 5}'],
            )

        assert result.exit_code == 0, f"Output: {result.output}"

    def test_auto_command_json_file_param(self, tmp_path):
        """dict パラメータが --params-file で渡せる"""
        schema = CommandSchema(
            command="test.apply",
            description="Apply filter.",
            params=[
                ParamSchema(name="doc_id", type=int, description="Document ID"),
                ParamSchema(name="params", type=dict, description="Filter params", required=False, default=None),
            ],
        )
        test_cli = self._make_cli_with_auto_command(schema)
        runner = CliRunner()

        json_file = tmp_path / "params.json"
        json_file.write_text('{"radius": 5}')

        mock_conn_mgr = AsyncMock()
        mock_conn_mgr.execute.return_value = {"applied": True}

        with patch("cli.auto_commands._get_connection_manager", return_value=mock_conn_mgr):
            result = runner.invoke(
                test_cli,
                ["--output", "json", "test", "apply", "--doc-id", "1", "--params-file", str(json_file)],
            )

        assert result.exit_code == 0, f"Output: {result.output}"

    def test_auto_command_invalid_json_param(self):
        """無効な JSON パラメータがエラーになる"""
        schema = CommandSchema(
            command="test.apply",
            description="Apply filter.",
            params=[
                ParamSchema(name="doc_id", type=int, description="Document ID"),
                ParamSchema(name="params", type=dict, description="Filter params", required=False, default=None),
            ],
        )
        test_cli = self._make_cli_with_auto_command(schema)
        runner = CliRunner()

        result = runner.invoke(
            test_cli,
            ["--output", "json", "test", "apply", "--doc-id", "1", "--params", "{invalid json}"],
        )

        assert result.exit_code != 0
```

**Step 2: 失敗を確認**

Run: `python -m pytest tests/unit/cli/test_auto_commands.py -v`
Expected: FAIL (ModuleNotFoundError: No module named 'cli.auto_commands')

**Step 3: 最小限の実装**

```python
# cli/auto_commands.py
"""CommandSchema から Click コマンドを自動生成する

CommandSchema 駆動の Single Source of Truth アーキテクチャ:
  CommandSchema (photoshop_sdk/schema.py)
      ├── CLI (Click) コマンド ... このモジュールで自動生成
      ├── MCP Server ツール ... tool_registry.py で自動生成（既存）
      └── psd schema コマンド ... スキーマ情報の表示
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import click

from cli.output import OutputFormatter
from photoshop_sdk.exceptions import (
    ConnectionError as PSConnectionError,
    PhotoshopSDKError,
    TimeoutError as PSTimeoutError,
    ValidationError as PSValidationError,
)
from photoshop_sdk.schema import COMMAND_SCHEMAS, CommandSchema
from photoshop_sdk.validators import validate_file_path

logger = logging.getLogger(__name__)

_TYPE_MAP = {str: str, int: int, bool: bool, float: float}

_VALIDATORS = {
    "validate_file_path": validate_file_path,
}


def _get_connection_manager():
    """ConnectionManager を遅延取得する（テストでモック可能）"""
    from mcp_server.connection import ConnectionManager

    return ConnectionManager()


def _run_async(coro):
    """CLI から async 関数を実行するヘルパー"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _handle_error(ctx: click.Context, e: Exception, fmt: str) -> None:
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


def _parse_json_option(ctx, param, value):
    """JSON文字列オプションのパーサ。パースエラー時は分かりやすいエラーメッセージを表示"""
    if value is None:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError as e:
        raise click.BadParameter(
            f"Invalid JSON: {e.msg} (position {e.pos})\n"
            f"  Input: {value}\n"
            f"  Hint: Use --{param.name}-file to specify a JSON file instead"
        )


def _resolve_json_file_params(kwargs: dict) -> dict:
    """--param-file が指定されている場合、ファイルの内容で --param を上書き"""
    resolved = {}
    file_keys = [k for k in kwargs if k.endswith("_file")]

    for key, value in kwargs.items():
        if key.endswith("_file"):
            if value is not None:
                base_key = key[:-5]  # "_file" を除去
                try:
                    with open(value, "r") as f:
                        resolved[base_key] = json.load(f)
                except json.JSONDecodeError as e:
                    raise click.BadParameter(
                        f"Invalid JSON in file '{value}': {e.msg} (line {e.lineno})"
                    )
                except OSError as e:
                    raise click.BadParameter(f"Cannot read file '{value}': {e}")
        else:
            # _file が存在し、かつ値が設定されている場合はスキップ（ファイルが優先）
            file_key = f"{key}_file"
            if file_key in kwargs and kwargs[file_key] is not None:
                continue
            resolved[key] = value

    return resolved


def build_click_command(schema: CommandSchema) -> click.Command:
    """CommandSchema を Click Command に変換する"""
    params = []

    for p in schema.params:
        if p.type == bool:
            # bool は --foo/--no-foo 形式で生成
            param_name = p.name.replace("_", "-")
            params.append(
                click.Option(
                    [f"--{param_name}/--no-{param_name}"],
                    default=p.default if not p.required else None,
                    help=p.description,
                    show_default=True if p.default is not None else False,
                )
            )
        elif p.type in (list, dict):
            # JSON型パラメータ: --param と --param-file の両方を生成
            param_name = p.name.replace("_", "-")
            params.append(
                click.Option(
                    [f"--{param_name}"],
                    type=str,
                    required=False,
                    default=None,
                    help=f"{p.description} (JSON string)",
                    callback=_parse_json_option,
                    is_eager=False,
                )
            )
            params.append(
                click.Option(
                    [f"--{param_name}-file"],
                    type=click.Path(exists=True),
                    required=False,
                    default=None,
                    help=f"{p.description} (JSON file path)",
                )
            )
        else:
            param_name = p.name.replace("_", "-")
            params.append(
                click.Option(
                    [f"--{param_name}"],
                    type=_TYPE_MAP.get(p.type, p.type),
                    required=p.required,
                    default=p.default if not p.required else None,
                    help=p.description,
                    show_default=True if p.default is not None else False,
                )
            )

    _schema = schema

    @click.pass_context
    def callback(ctx, **kwargs):
        fmt = ctx.obj.get("output", "text") if ctx.obj else "text"
        timeout = ctx.obj.get("timeout", _schema.timeout) if ctx.obj else _schema.timeout
        fields = ctx.obj.get("fields") if ctx.obj else None
        dry_run = ctx.obj.get("dry_run", False) if ctx.obj else False

        # JSON file パラメータの解決
        try:
            kwargs = _resolve_json_file_params(kwargs)
        except click.BadParameter as e:
            click.echo(
                OutputFormatter.format_error(str(e), fmt, code="VALIDATION_ERROR"),
                err=True,
            )
            ctx.exit(4)
            return

        # バリデータの実行
        if _schema.validator and _schema.validator in _VALIDATORS:
            try:
                validator_fn = _VALIDATORS[_schema.validator]
                for p in _schema.params:
                    if p.name in kwargs and kwargs[p.name] is not None and p.required:
                        validated = validator_fn(kwargs[p.name])
                        kwargs[p.name] = str(validated)
                        break
            except PSValidationError as e:
                click.echo(
                    OutputFormatter.format_error(str(e), fmt, code=e.code or "VALIDATION_ERROR"),
                    err=True,
                )
                ctx.exit(4)
                return

        # SDK パラメータ名への変換
        sdk_params = {}
        for p in _schema.params:
            if p.name in kwargs and kwargs[p.name] is not None:
                sdk_params[p.effective_sdk_name] = kwargs[p.name]

        # dry-run チェック
        if dry_run and _schema.mutating and _schema.supports_dry_run:
            dry_run_output = {
                "dry_run": True,
                "command": _schema.command,
                "params": sdk_params,
                "timeout": timeout,
                "message": f"Validation passed. Would execute: {_schema.command}",
            }
            click.echo(OutputFormatter.format(dry_run_output, fmt, fields=fields))
            return

        # 実行
        async def _run():
            conn_mgr = _get_connection_manager()
            try:
                result = await conn_mgr.execute(_schema.command, sdk_params, timeout=timeout)
                click.echo(OutputFormatter.format(result, fmt, fields=fields))
            except Exception as e:
                _handle_error(ctx, e, fmt)

        _run_async(_run())

    action_name = schema.command.split(".")[-1]

    return click.Command(
        name=action_name,
        params=params,
        callback=callback,
        help=schema.description,
    )


def register_group_commands(
    group: click.Group,
    group_name: str,
    schemas: list[CommandSchema] | None = None,
) -> None:
    """指定グループのコマンドを一括登録する

    Args:
        group: Click Group に登録する
        group_name: コマンドグループ名（例: "document"）
        schemas: 使用する CommandSchema リスト（デフォルト: COMMAND_SCHEMAS）
    """
    if schemas is None:
        schemas = COMMAND_SCHEMAS

    for schema in schemas:
        if schema.command.startswith(f"{group_name}."):
            cmd = build_click_command(schema)
            group.add_command(cmd)
```

**Step 4: 通過を確認**

Run: `python -m pytest tests/unit/cli/test_auto_commands.py -v`
Expected: PASS

**Step 5: コミット**

```
git add cli/auto_commands.py tests/unit/cli/test_auto_commands.py
git commit -m "feat: add CLI auto-generation from CommandSchema (Phase 1.1)"
```

---

### Task 1.2: UXP dispatcher のモジュール化

**Files:**
- Modify: `uxp-plugin/src/dispatcher.ts`
- Modify: `uxp-plugin/src/handlers/file.ts`

**Step 1: 失敗するテストを書く**

UXP Plugin は TypeScript でテストフレームワーク未導入のため、この段階では手動検証と型チェックで確認する。
ディスパッチャのリファクタリングは後方互換を維持する。

**Step 3: 最小限の実装**

```typescript
// uxp-plugin/src/handlers/file.ts
// - 既存の個別 export を維持しつつ HANDLERS マップを追加
// - document.* と file.* の両方に対応（エイリアス）

/**
 * file.ts - Photoshop ファイル/ドキュメント操作ハンドラ
 *
 * コマンド: file.open, file.close, file.save, file.info, file.list
 *         + document.* エイリアス（内部同一ハンドラ）
 * ドキュメント変更系操作は executeAsModal で囲む。
 */

const photoshop = require("photoshop");
const app = photoshop.app;
const { executeAsModal } = photoshop.core;
const fs = require("uxp").storage.localFileSystem;

type Handler = (params: Record<string, unknown>) => Promise<unknown>;

interface DocumentParams {
  documentId?: number;
  path?: string;
  save?: boolean;
}

function serializeDocument(doc: any): Record<string, unknown> {
  return {
    documentId: doc.id,
    name: doc.name,
    path: doc.path || null,
    width: doc.width,
    height: doc.height,
    colorMode: doc.mode?.toString() ?? null,
    resolution: doc.resolution ?? null,
    hasUnsavedChanges: doc.saved === false,
  };
}

function findDocument(documentId: number): any {
  const doc = app.documents.find((d: any) => d.id === documentId);
  if (!doc) {
    const err = new Error(`Document with ID '${documentId}' not found`);
    (err as any).code = "DOCUMENT_NOT_FOUND";
    throw err;
  }
  return doc;
}

export async function handleFileOpen(params: DocumentParams): Promise<unknown> {
  const { path } = params;
  if (!path) {
    const err = new Error("Parameter 'path' is required");
    (err as any).code = "VALIDATION_ERROR";
    throw err;
  }

  const entry = await fs.getEntryWithUrl("file://" + path);
  const doc = await executeAsModal(
    async () => app.open(entry),
    { commandName: "Open File" }
  );
  return serializeDocument(doc);
}

export async function handleFileClose(params: DocumentParams): Promise<unknown> {
  const { documentId, save = false } = params;
  if (documentId === undefined) {
    const err = new Error("Parameter 'documentId' is required");
    (err as any).code = "VALIDATION_ERROR";
    throw err;
  }

  const doc = findDocument(documentId);

  await executeAsModal(
    async () => {
      if (save) {
        await doc.save();
      }
      await doc.close(
        save
          ? photoshop.constants.SaveOptions.SAVECHANGES
          : photoshop.constants.SaveOptions.DONOTSAVECHANGES
      );
    },
    { commandName: "Close File" }
  );

  return { closed: true, documentId };
}

export async function handleFileSave(params: DocumentParams): Promise<unknown> {
  const { documentId } = params;
  if (documentId === undefined) {
    const err = new Error("Parameter 'documentId' is required");
    (err as any).code = "VALIDATION_ERROR";
    throw err;
  }

  const doc = findDocument(documentId);

  await executeAsModal(
    async () => doc.save(),
    { commandName: "Save File" }
  );
  return { saved: true, documentId };
}

export async function handleFileInfo(params: DocumentParams): Promise<unknown> {
  const { documentId } = params;
  if (documentId === undefined) {
    const err = new Error("Parameter 'documentId' is required");
    (err as any).code = "VALIDATION_ERROR";
    throw err;
  }

  const doc = findDocument(documentId);
  return serializeDocument(doc);
}

export async function handleFileList(_params: DocumentParams): Promise<unknown> {
  const documents = Array.from(app.documents).map((doc: any) => serializeDocument(doc));
  return { documents };
}

// ハンドラマップ: dispatcher.ts のモジュール化対応
export const HANDLERS: Record<string, Handler> = {
  open: handleFileOpen as Handler,
  close: handleFileClose as Handler,
  save: handleFileSave as Handler,
  info: handleFileInfo as Handler,
  list: handleFileList as Handler,
};
```

```typescript
// uxp-plugin/src/dispatcher.ts
/**
 * dispatcher.ts - コマンドディスパッチャ（モジュール化版）
 *
 * コマンド名を "group.action" に分割し、対応するハンドラモジュールに委譲する。
 * file → document エイリアスにも対応。
 */

import { HANDLERS as documentHandlers } from "./handlers/file";

type Handler = (params: Record<string, unknown>) => Promise<unknown>;

// 各ハンドラモジュールが HANDLERS: Record<string, Handler> を export
const HANDLER_MODULES: Record<string, Record<string, Handler>> = {
  document: documentHandlers,
  file: documentHandlers, // file → document エイリアス
};

// system.ping はインラインで定義
const SYSTEM_HANDLERS: Record<string, Handler> = {
  ping: async () => ({ status: "ok", timestamp: Date.now() }),
};

HANDLER_MODULES["system"] = SYSTEM_HANDLERS;

export async function dispatch(
  command: string,
  params: Record<string, unknown>
): Promise<unknown> {
  const dotIndex = command.indexOf(".");
  if (dotIndex === -1) {
    throw Object.assign(new Error(`Invalid command format: ${command}`), {
      code: "UNKNOWN_COMMAND",
    });
  }

  const group = command.substring(0, dotIndex);
  const action = command.substring(dotIndex + 1);

  const handlers = HANDLER_MODULES[group];
  if (!handlers || !handlers[action]) {
    throw Object.assign(new Error(`Unknown command: ${command}`), {
      code: "UNKNOWN_COMMAND",
    });
  }

  return handlers[action](params);
}
```

**Step 4: 通過を確認**

Run: TypeScript コンパイルチェック (`npx tsc --noEmit` in uxp-plugin/)
Expected: PASS

**Step 5: コミット**

```
git add uxp-plugin/src/dispatcher.ts uxp-plugin/src/handlers/file.ts
git commit -m "refactor: modularize UXP dispatcher with HANDLERS map (Phase 1.2)"
```

---

### Task 1.3: UXP WebSocket 修正（リスナーメンバ保持、const ws ガード、_cleanupSocket 全面書き直し）

**Files:**
- Modify: `uxp-plugin/src/ws_client.ts`

**Step 1: 失敗するテストを書く**

WebSocket の修正は UXP 環境特有の問題であり、ユニットテストは困難。設計書セクション 4.2 の修正を適用し、手動検証 + 実機テストで確認する。

**Step 3: 最小限の実装**

```typescript
// uxp-plugin/src/ws_client.ts
/**
 * ws_client.ts - WebSocket クライアント
 *
 * Python SDK (ResilientWSBridge) が起動する WS サーバーに接続する。
 * 固定ポート 49152 を使用（ポートファイル不要）。
 *
 * 自動再接続: 切断時に指数バックオフで再接続を試みる。
 *
 * v2.0.0 修正: "Too many open files" 問題の根本修正
 * - イベントリスナーをメンバ変数として保持（removeEventListener 同一参照対応）
 * - const ws ガードでレース条件を防止
 * - _cleanupSocket() でソケットを確実に解放
 */

export type CommandHandler = (command: string, params: Record<string, unknown>) => Promise<unknown>;

interface CommandMessage {
  id: string;
  command: string;
  params: Record<string, unknown>;
}

interface ResponseMessage {
  id: string;
  success: boolean;
  result?: unknown;
  error?: { code: string; message: string };
}

const DEFAULT_PORT = 49152;
const RECONNECT_BASE_DELAY_MS = 2000;
const RECONNECT_MAX_DELAY_MS = 60000;

export class WSClient {
  private ws: WebSocket | null = null;
  private handler: CommandHandler | null = null;
  private isShuttingDown = false;
  private reconnectAttempts = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private isConnecting = false;

  // イベントリスナーをメンバとして保持（同一参照で解除可能にする）
  private _onOpen: (() => void) | null = null;
  private _onMessage: ((event: MessageEvent) => void) | null = null;
  private _onClose: (() => void) | null = null;
  private _onError: ((event: Event) => void) | null = null;

  setHandler(handler: CommandHandler): void {
    this.handler = handler;
  }

  async connect(): Promise<void> {
    if (this.isConnecting) {
      console.warn("[WS] Connection already in progress, skipping");
      return;
    }
    this.isConnecting = true;

    // 既存の WebSocket を確実にクリーンアップ
    this._cleanupSocket();

    const uri = `ws://localhost:${DEFAULT_PORT}`;
    console.log(`[WS] Connecting to ${uri}`);

    return new Promise<void>((resolve, reject) => {
      let settled = false;

      try {
        this.ws = new WebSocket(uri);
      } catch (e) {
        this.isConnecting = false;
        reject(e);
        return;
      }

      // ローカル変数で現在のソケットを保持（レース条件ガード用）
      const ws = this.ws;

      this._onOpen = () => {
        if (this.ws !== ws) return; // 古いソケットのイベントを無視
        if (settled) return;
        settled = true;
        this.isConnecting = false;
        console.log("[WS] Connected to Python SDK");
        this.reconnectAttempts = 0;
        resolve();
      };

      this._onMessage = (event: MessageEvent) => {
        if (this.ws !== ws) return; // 古いソケットのイベントを無視
        this._handleMessage(event.data as string);
      };

      this._onClose = () => {
        if (this.ws !== ws) return; // 古いソケットのイベントを無視
        console.log("[WS] Connection closed");
        this._cleanupSocket();
        if (!this.isShuttingDown) {
          this._scheduleReconnect();
        }
        if (!settled) {
          settled = true;
          this.isConnecting = false;
          reject(new Error("WebSocket closed before open"));
        }
      };

      this._onError = (event: Event) => {
        if (this.ws !== ws) return; // 古いソケットのイベントを無視
        console.error("[WS] WebSocket error:", event);
        if (!settled) {
          settled = true;
          this.isConnecting = false;
          this._cleanupSocket();
          reject(new Error("WebSocket connection failed"));
        }
      };

      ws.addEventListener("open", this._onOpen);
      ws.addEventListener("message", this._onMessage);
      ws.addEventListener("close", this._onClose);
      ws.addEventListener("error", this._onError);
    });
  }

  private async _handleMessage(raw: string): Promise<void> {
    let msg: CommandMessage;
    try {
      msg = JSON.parse(raw) as CommandMessage;
    } catch (e) {
      console.error("[WS] Invalid JSON received:", raw);
      return;
    }

    if (!this.handler) {
      console.error("[WS] No handler registered");
      return;
    }

    let response: ResponseMessage;
    try {
      const result = await this.handler(msg.command, msg.params);
      response = { id: msg.id, success: true, result };
    } catch (e: unknown) {
      const error = e as Error & { code?: string };
      response = {
        id: msg.id,
        success: false,
        error: {
          code: error.code || "HANDLER_ERROR",
          message: error.message || String(e),
        },
      };
    }

    this._send(response);
  }

  private _send(data: unknown): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    } else {
      console.error("[WS] Cannot send: not connected");
    }
  }

  /**
   * WebSocket のクリーンアップ（ファイルディスクリプタリーク防止）
   * - 同一参照でイベントリスナーを解除
   * - readyState に関わらず close() を呼ぶ
   * - 参照を null に設定
   */
  private _cleanupSocket(): void {
    if (this.ws) {
      try {
        // メンバ保持した同一参照でイベントリスナーを確実に解除
        if (this._onOpen) this.ws.removeEventListener("open", this._onOpen);
        if (this._onMessage) this.ws.removeEventListener("message", this._onMessage);
        if (this._onClose) this.ws.removeEventListener("close", this._onClose);
        if (this._onError) this.ws.removeEventListener("error", this._onError);

        if (
          this.ws.readyState === WebSocket.OPEN ||
          this.ws.readyState === WebSocket.CONNECTING
        ) {
          this.ws.close();
        }
      } catch (e) {
        console.warn("[WS] Error during socket cleanup:", e);
      }
      this.ws = null;
    }
    this._onOpen = null;
    this._onMessage = null;
    this._onClose = null;
    this._onError = null;
  }

  private _scheduleReconnect(): void {
    // 既存のタイマーをクリア（重複防止）
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }

    const delay = Math.min(
      RECONNECT_BASE_DELAY_MS * Math.pow(2, this.reconnectAttempts),
      RECONNECT_MAX_DELAY_MS
    );
    this.reconnectAttempts++;
    console.log(`[WS] Reconnecting in ${delay / 1000}s (attempt ${this.reconnectAttempts})`);

    this.reconnectTimer = setTimeout(async () => {
      this.reconnectTimer = null;
      try {
        await this.connect();
      } catch (e) {
        // connect 内で _cleanupSocket() が呼ばれるので、ここでは再スケジュールのみ
        if (!this.isShuttingDown) {
          this._scheduleReconnect();
        }
      }
    }, delay);
  }

  disconnect(): void {
    this.isShuttingDown = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this._cleanupSocket();
  }
}

// シングルトン
export const wsClient = new WSClient();
```

**Step 4: 通過を確認**

Run: TypeScript コンパイルチェック (`npx tsc --noEmit` in uxp-plugin/)
Expected: PASS

**Step 5: コミット**

```
git add uxp-plugin/src/ws_client.ts
git commit -m "fix: resolve WebSocket fd leak with listener member refs and cleanup (Phase 1.3)"
```

---

### Task 1.4: 例外クラスの拡張

**Files:**
- Modify: `photoshop_sdk/exceptions.py`
- Test: `tests/unit/sdk/test_exceptions.py`

**Step 1: 失敗するテストを書く**

```python
# tests/unit/sdk/test_exceptions.py に追加
# 既存テストの末尾に以下を追加する

from photoshop_sdk.exceptions import (
    BatchPlayBlockedError,
    ChannelNotFoundError,
    FilterError,
    LayerNotFoundError,
    PathNotFoundError,
    SelectionError,
    UnsupportedOperationError,
)


def test_layer_not_found_is_subclass():
    e = LayerNotFoundError("Layer 5 not found", code="LAYER_NOT_FOUND")
    assert isinstance(e, PhotoshopSDKError)
    assert e.code == "LAYER_NOT_FOUND"


def test_filter_error_is_subclass():
    e = FilterError("Filter failed", code="FILTER_ERROR")
    assert isinstance(e, PhotoshopSDKError)
    assert e.code == "FILTER_ERROR"


def test_channel_not_found_is_subclass():
    e = ChannelNotFoundError("Channel not found", code="CHANNEL_NOT_FOUND")
    assert isinstance(e, PhotoshopSDKError)
    assert e.code == "CHANNEL_NOT_FOUND"


def test_selection_error_is_subclass():
    e = SelectionError("Selection failed", code="SELECTION_ERROR")
    assert isinstance(e, PhotoshopSDKError)
    assert e.code == "SELECTION_ERROR"


def test_path_not_found_is_subclass():
    e = PathNotFoundError("Path not found", code="PATH_NOT_FOUND")
    assert isinstance(e, PhotoshopSDKError)
    assert e.code == "PATH_NOT_FOUND"


def test_unsupported_operation_is_subclass():
    e = UnsupportedOperationError("Not supported", code="UNSUPPORTED_OPERATION")
    assert isinstance(e, PhotoshopSDKError)
    assert e.code == "UNSUPPORTED_OPERATION"


def test_batch_play_blocked_is_subclass():
    e = BatchPlayBlockedError("Blocked descriptor", code="BATCH_PLAY_BLOCKED")
    assert isinstance(e, PhotoshopSDKError)
    assert e.code == "BATCH_PLAY_BLOCKED"


def test_error_code_map_contains_new_codes():
    assert "LAYER_NOT_FOUND" in ERROR_CODE_MAP
    assert "FILTER_ERROR" in ERROR_CODE_MAP
    assert "CHANNEL_NOT_FOUND" in ERROR_CODE_MAP
    assert "SELECTION_ERROR" in ERROR_CODE_MAP
    assert "PATH_NOT_FOUND" in ERROR_CODE_MAP
    assert "UNSUPPORTED_OPERATION" in ERROR_CODE_MAP
    assert "BATCH_PLAY_BLOCKED" in ERROR_CODE_MAP


def test_error_code_map_new_codes_map_correctly():
    assert ERROR_CODE_MAP["LAYER_NOT_FOUND"] is LayerNotFoundError
    assert ERROR_CODE_MAP["FILTER_ERROR"] is FilterError
    assert ERROR_CODE_MAP["CHANNEL_NOT_FOUND"] is ChannelNotFoundError
    assert ERROR_CODE_MAP["SELECTION_ERROR"] is SelectionError
    assert ERROR_CODE_MAP["PATH_NOT_FOUND"] is PathNotFoundError
    assert ERROR_CODE_MAP["UNSUPPORTED_OPERATION"] is UnsupportedOperationError
    assert ERROR_CODE_MAP["BATCH_PLAY_BLOCKED"] is BatchPlayBlockedError
```

**Step 2: 失敗を確認**

Run: `python -m pytest tests/unit/sdk/test_exceptions.py -v`
Expected: FAIL (ImportError)

**Step 3: 最小限の実装**

```python
# photoshop_sdk/exceptions.py
from typing import Any, Dict, Optional


class PhotoshopSDKError(Exception):
    """Base exception for Photoshop SDK errors"""

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.code = code
        self.details = details or {}


class ConnectionError(PhotoshopSDKError):
    """WebSocket connection errors"""

    pass


class TimeoutError(PhotoshopSDKError):
    """Command timeout errors"""

    pass


class DocumentNotFoundError(PhotoshopSDKError):
    """Document with given ID not found"""

    def __init__(
        self,
        message: Optional[str] = None,
        doc_id: Optional[int] = None,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        if message is None and doc_id is not None:
            message = f"Document with ID '{doc_id}' not found"
        elif message is None:
            message = "Document not found"
        super().__init__(message, code=code or "DOCUMENT_NOT_FOUND", details=details)


class ValidationError(PhotoshopSDKError):
    """Invalid parameter errors"""

    pass


class HandlerError(PhotoshopSDKError):
    """UXP handler execution error"""

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message, code=code or "HANDLER_ERROR", details=details)


class LayerNotFoundError(PhotoshopSDKError):
    """指定IDのレイヤーが見つからない"""

    pass


class FilterError(PhotoshopSDKError):
    """フィルター適用エラー"""

    pass


class ChannelNotFoundError(PhotoshopSDKError):
    """指定IDのチャンネルが見つからない"""

    pass


class SelectionError(PhotoshopSDKError):
    """選択範囲操作エラー"""

    pass


class PathNotFoundError(PhotoshopSDKError):
    """指定IDのパスが見つからない"""

    pass


class UnsupportedOperationError(PhotoshopSDKError):
    """サポートされていない操作"""

    pass


class BatchPlayBlockedError(PhotoshopSDKError):
    """batchPlay でブロックされたデスクリプタが使用された"""

    pass


# Error code mapping from UXP Plugin responses
ERROR_CODE_MAP: Dict[str, type] = {
    "DOCUMENT_NOT_FOUND": DocumentNotFoundError,
    "CONNECTION_FAILED": ConnectionError,
    "TIMEOUT": TimeoutError,
    "VALIDATION_ERROR": ValidationError,
    "HANDLER_ERROR": HandlerError,
    "LAYER_NOT_FOUND": LayerNotFoundError,
    "FILTER_ERROR": FilterError,
    "CHANNEL_NOT_FOUND": ChannelNotFoundError,
    "SELECTION_ERROR": SelectionError,
    "PATH_NOT_FOUND": PathNotFoundError,
    "UNSUPPORTED_OPERATION": UnsupportedOperationError,
    "BATCH_PLAY_BLOCKED": BatchPlayBlockedError,
}
```

**Step 4: 通過を確認**

Run: `python -m pytest tests/unit/sdk/test_exceptions.py -v`
Expected: PASS

**Step 5: コミット**

```
git add photoshop_sdk/exceptions.py tests/unit/sdk/test_exceptions.py
git commit -m "feat: add exception classes for layer, filter, channel, selection, path, action (Phase 1.4)"
```

---

### Task 1.5: file / document 並行公開（内部同一ハンドラ、MCP二重登録）

**Files:**
- Modify: `photoshop_sdk/schema.py`
- Modify: `cli/main.py`
- Create: `cli/commands/document.py`
- Modify: `cli/commands/file.py`
- Modify: `mcp_server/tool_registry.py`
- Test: `tests/unit/cli/test_document_alias.py`
- Test: `tests/unit/mcp/test_document_alias.py`

**Step 1: 失敗するテストを書く**

```python
# tests/unit/cli/test_document_alias.py
"""document / file エイリアスの並行公開テスト"""

import json
from unittest.mock import AsyncMock, patch

from click.testing import CliRunner

from cli.main import cli
from photoshop_sdk.schema import COMMAND_SCHEMAS, CommandSchema


class TestDocumentFileAlias:
    """document と file が同一コマンドを提供する"""

    def test_document_group_exists(self):
        """document グループが CLI に登録されている"""
        runner = CliRunner()
        result = runner.invoke(cli, ["document", "--help"])
        assert result.exit_code == 0
        assert "document" in result.output.lower() or "Document" in result.output

    def test_file_group_still_exists(self):
        """file グループが引き続き存在する"""
        runner = CliRunner()
        result = runner.invoke(cli, ["file", "--help"])
        assert result.exit_code == 0

    def test_document_list_has_subcommands(self):
        """document グループにサブコマンドが存在する"""
        runner = CliRunner()
        result = runner.invoke(cli, ["document", "--help"])
        assert "list" in result.output
        assert "info" in result.output
        assert "open" in result.output

    def test_file_list_has_same_subcommands(self):
        """file グループにも同一サブコマンドが存在する"""
        runner = CliRunner()
        result = runner.invoke(cli, ["file", "--help"])
        assert "list" in result.output
        assert "info" in result.output
        assert "open" in result.output


class TestDocumentSchemas:
    """CommandSchema に document.* が定義されている"""

    def test_document_schemas_exist(self):
        """document.* コマンドが COMMAND_SCHEMAS に存在する"""
        doc_commands = [s for s in COMMAND_SCHEMAS if s.command.startswith("document.")]
        assert len(doc_commands) >= 5  # list, info, open, close, save は最低限

    def test_document_and_file_commands_match(self):
        """document.* と file.* のコマンドが1:1対応している"""
        doc_commands = {s.command.replace("document.", "") for s in COMMAND_SCHEMAS if s.command.startswith("document.")}
        file_commands = {s.command.replace("file.", "") for s in COMMAND_SCHEMAS if s.command.startswith("file.")}
        assert doc_commands == file_commands


class TestMCPDualRegistration:
    """MCP ツールが file_* と document_* の両方で登録される"""

    def test_dual_registration(self):
        """file_* と document_* の両方のツール名で登録される"""
        from mcp_server.tool_registry import _build_tool_fn

        doc_schemas = [s for s in COMMAND_SCHEMAS if s.command.startswith("document.")]
        file_schemas = [s for s in COMMAND_SCHEMAS if s.command.startswith("file.")]

        doc_tool_names = {s.command.replace(".", "_") for s in doc_schemas}
        file_tool_names = {s.command.replace(".", "_") for s in file_schemas}

        # 両方が存在すること
        assert len(doc_tool_names) > 0
        assert len(file_tool_names) > 0

        # アクション名が一致すること
        doc_actions = {name.replace("document_", "") for name in doc_tool_names}
        file_actions = {name.replace("file_", "") for name in file_tool_names}
        assert doc_actions == file_actions
```

```python
# tests/unit/mcp/test_document_alias.py
"""MCP の document/file 二重登録テスト"""

from photoshop_sdk.schema import COMMAND_SCHEMAS


def test_mcp_schemas_have_both_prefixes():
    """COMMAND_SCHEMAS に document.* と file.* の両方が含まれる"""
    doc = [s for s in COMMAND_SCHEMAS if s.command.startswith("document.")]
    file = [s for s in COMMAND_SCHEMAS if s.command.startswith("file.")]
    assert len(doc) > 0
    assert len(file) > 0
    assert len(doc) == len(file)
```

**Step 2: 失敗を確認**

Run: `python -m pytest tests/unit/cli/test_document_alias.py tests/unit/mcp/test_document_alias.py -v`
Expected: FAIL

**Step 3: 最小限の実装**

```python
# photoshop_sdk/schema.py
"""Pydantic モデル定義 - Python SDK と MCP Server の共通型"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class PhotoshopCommand(BaseModel):
    """Python → UXP へのコマンド送信メッセージ"""

    id: str
    command: str
    params: Dict[str, Any] = Field(default_factory=dict)


class PhotoshopResponse(BaseModel):
    """UXP → Python への結果返却メッセージ"""

    id: str
    success: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None


class DocumentInfo(BaseModel):
    """Photoshop ドキュメント情報"""

    documentId: int
    name: str
    path: Optional[str] = None
    width: int
    height: int
    colorMode: Optional[str] = None
    resolution: Optional[float] = None
    hasUnsavedChanges: Optional[bool] = None


@dataclass(frozen=True)
class ParamSchema:
    """コマンドパラメータの定義"""

    name: str
    type: type
    description: str
    required: bool = True
    default: Any = None
    sdk_name: str | None = None

    @property
    def effective_sdk_name(self) -> str:
        return self.sdk_name or self.name


@dataclass(frozen=True)
class CommandSchema:
    """コマンドのメタデータ定義"""

    command: str
    description: str
    params: list[ParamSchema] = field(default_factory=list)
    mutating: bool = False
    risk_level: str = "read"
    requires_confirm: bool = False
    supports_dry_run: bool = False
    timeout: float = 30.0
    validator: str | None = None


# document.* コマンド定義（正規名）
_DOCUMENT_SCHEMAS: list[CommandSchema] = [
    CommandSchema(
        command="document.list",
        description="List all open Photoshop documents.",
    ),
    CommandSchema(
        command="document.info",
        description="Get detailed information for a specific document.",
        params=[
            ParamSchema(name="doc_id", type=int, description="Document ID", sdk_name="documentId"),
        ],
    ),
    CommandSchema(
        command="document.open",
        description="Open a PSD file in Photoshop.",
        params=[
            ParamSchema(name="path", type=str, description="Absolute path to the PSD file"),
        ],
        mutating=True,
        risk_level="write",
        supports_dry_run=True,
        timeout=120.0,
        validator="validate_file_path",
    ),
    CommandSchema(
        command="document.close",
        description="Close a document. Use save=true to save before closing.",
        params=[
            ParamSchema(name="doc_id", type=int, description="Document ID to close", sdk_name="documentId"),
            ParamSchema(name="save", type=bool, description="Save before closing", required=False, default=False),
        ],
        mutating=True,
        risk_level="write",
        requires_confirm=True,
        supports_dry_run=True,
    ),
    CommandSchema(
        command="document.save",
        description="Save a document.",
        params=[
            ParamSchema(name="doc_id", type=int, description="Document ID to save", sdk_name="documentId"),
        ],
        mutating=True,
        risk_level="write",
        supports_dry_run=True,
    ),
]


def _create_file_alias(schema: CommandSchema) -> CommandSchema:
    """document.* スキーマから file.* エイリアスを生成する"""
    return CommandSchema(
        command=schema.command.replace("document.", "file."),
        description=schema.description,
        params=schema.params,
        mutating=schema.mutating,
        risk_level=schema.risk_level,
        requires_confirm=schema.requires_confirm,
        supports_dry_run=schema.supports_dry_run,
        timeout=schema.timeout,
        validator=schema.validator,
    )


# file.* エイリアス生成
_FILE_SCHEMAS: list[CommandSchema] = [_create_file_alias(s) for s in _DOCUMENT_SCHEMAS]

COMMAND_SCHEMAS: list[CommandSchema] = [
    *_DOCUMENT_SCHEMAS,
    *_FILE_SCHEMAS,
    CommandSchema(
        command="system.ping",
        description="Check connection to Photoshop UXP Plugin.",
        timeout=5.0,
    ),
]
```

```python
# cli/commands/document.py
"""psd document サブコマンド群 — auto_commands で自動生成"""

import click

from cli.auto_commands import register_group_commands


@click.group(name="document")
def document_cmd():
    """Document operations (open, close, save, info, list, and more)"""
    pass


# CommandSchema から自動生成
register_group_commands(document_cmd, "document")
```

```python
# cli/commands/file.py — document の薄いラッパーとして再定義
"""psd file サブコマンド群 — document のエイリアス（auto_commands で自動生成）"""

import click

from cli.auto_commands import register_group_commands


@click.group(name="file")
def file_cmd():
    """File operations (alias for 'document' commands)"""
    pass


# CommandSchema の file.* エイリアスから自動生成
register_group_commands(file_cmd, "file")
```

```python
# cli/main.py
import logging
import os

import click


def resolve_output_format(output: str | None) -> str:
    if output is not None:
        return output
    # TTY でなければ json、TTY なら text
    import sys

    return "json" if not sys.stdout.isatty() else "text"


def resolve_timeout(timeout: float | None) -> float:
    return timeout if timeout is not None else 30.0


@click.group()
@click.version_option(version="1.0.0", prog_name="psd")
@click.option(
    "--output",
    "-o",
    type=click.Choice(["json", "text", "table"]),
    default=None,
    help="Output format (default: json for non-TTY, text for TTY)",
)
@click.option(
    "--fields",
    "-f",
    type=str,
    default=None,
    help="Comma-separated list of fields to include in output (e.g. 'id,name')",
)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.option(
    "--timeout",
    "-t",
    type=float,
    default=None,
    help="Default command timeout in seconds",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Validate inputs and show the command that would be sent, without executing",
)
@click.pass_context
def cli(ctx, output, fields, verbose, timeout, dry_run):
    """Adobe Photoshop CLI - control Photoshop from the command line."""
    ctx.ensure_object(dict)
    ctx.obj["output"] = resolve_output_format(output)
    ctx.obj["fields"] = [f.strip() for f in fields.split(",") if f.strip()] if fields else None
    ctx.obj["verbose"] = verbose or bool(os.environ.get("PS_VERBOSE"))
    ctx.obj["timeout"] = resolve_timeout(timeout)
    ctx.obj["dry_run"] = dry_run

    if ctx.obj["verbose"]:
        logging.basicConfig(level=logging.DEBUG, force=True)
    elif ctx.obj["output"] == "json":
        logging.basicConfig(level=logging.ERROR, force=True)
    else:
        logging.basicConfig(level=logging.WARNING, force=True)


# コマンドグループの登録
from cli.commands.document import document_cmd  # noqa: E402
from cli.commands.file import file_cmd  # noqa: E402
from cli.commands.mcp import mcp  # noqa: E402
from cli.commands.schema import schema_cmd  # noqa: E402
from cli.commands.system import system_cmd  # noqa: E402

cli.add_command(document_cmd)
cli.add_command(file_cmd)
cli.add_command(mcp)
cli.add_command(schema_cmd)
cli.add_command(system_cmd)
```

**Step 4: 通過を確認**

Run: `python -m pytest tests/unit/cli/test_document_alias.py tests/unit/mcp/test_document_alias.py -v`
Expected: PASS

**Step 5: コミット**

```
git add photoshop_sdk/schema.py cli/main.py cli/commands/document.py cli/commands/file.py \
    tests/unit/cli/test_document_alias.py tests/unit/mcp/test_document_alias.py
git commit -m "feat: add document/file dual publishing with shared handlers (Phase 1.5)"
```

---

### Task 1.6: 基盤テスト（既存テストの更新）

**Files:**
- Modify: `tests/unit/cli/test_file_commands.py`
- Modify: `tests/unit/sdk/test_schema.py`
- Modify: `tests/unit/mcp/test_command_schemas.py`
- Test: `tests/unit/cli/test_auto_commands.py` (Task 1.1 で作成済み)

**Step 1: 失敗するテストを書く**

```python
# tests/unit/sdk/test_schema.py に追加

from photoshop_sdk.schema import COMMAND_SCHEMAS, CommandSchema, ParamSchema


class TestCommandSchemaIntegrity:
    """全 CommandSchema の整合性テスト"""

    def test_all_commands_have_group_action_format(self):
        """全コマンドが 'group.action' 形式であること"""
        for schema in COMMAND_SCHEMAS:
            parts = schema.command.split(".")
            assert len(parts) == 2, f"Invalid command format: {schema.command}"
            assert len(parts[0]) > 0
            assert len(parts[1]) > 0

    def test_mutating_commands_have_risk_level(self):
        """mutating=True のコマンドには risk_level が read 以外であること"""
        for schema in COMMAND_SCHEMAS:
            if schema.mutating:
                assert schema.risk_level != "read", (
                    f"Mutating command {schema.command} has risk_level='read'"
                )

    def test_no_duplicate_commands(self):
        """コマンド名に重複がないこと"""
        commands = [s.command for s in COMMAND_SCHEMAS]
        assert len(commands) == len(set(commands)), (
            f"Duplicate commands found: {[c for c in commands if commands.count(c) > 1]}"
        )

    def test_document_file_parity(self):
        """document.* と file.* が1:1対応していること"""
        doc_actions = sorted(
            s.command.split(".")[1] for s in COMMAND_SCHEMAS if s.command.startswith("document.")
        )
        file_actions = sorted(
            s.command.split(".")[1] for s in COMMAND_SCHEMAS if s.command.startswith("file.")
        )
        assert doc_actions == file_actions

    def test_param_sdk_name_or_default(self):
        """全パラメータに effective_sdk_name が取得できること"""
        for schema in COMMAND_SCHEMAS:
            for p in schema.params:
                assert isinstance(p.effective_sdk_name, str)
                assert len(p.effective_sdk_name) > 0
```

**Step 2: 失敗を確認**

Run: `python -m pytest tests/unit/sdk/test_schema.py -v`
Expected: FAIL (new tests fail because of schema changes)

**Step 3: 最小限の実装**

既存テストファイルの import を更新して、新しいスキーマ構造に合わせる。
Task 1.1-1.5 の実装が正しければテストは通過する。

**Step 4: 通過を確認**

Run: `python -m pytest tests/unit/ -v`
Expected: PASS（全ユニットテストが通過）

Run: `ruff check .`
Expected: PASS

**Step 5: コミット**

```
git add tests/unit/sdk/test_schema.py tests/unit/cli/test_file_commands.py
git commit -m "test: add schema integrity tests and update existing tests for Phase 1 (Phase 1.6)"
```

---

## Phase 2: Document拡張 + Layer + Selection + Path

> 詳細仕様: 設計書セクション 2.2, 2.3, 2.6, 2.7 参照

### Task 2.1: Document 新規コマンド追加

**Files:**
- Modify: `photoshop_sdk/schema.py`
- Modify: `uxp-plugin/src/handlers/file.ts` (document ハンドラとして拡張)
- Test: `tests/unit/sdk/test_document_schemas.py`, `tests/integration/test_document_commands.py`

**実装内容:**
- document.create, document.duplicate, document.crop, document.resize-image, document.resize-canvas, document.rotate, document.flatten, document.trim, document.convert-mode, document.sample-color, document.save-as を CommandSchema に追加
- 対応する file.* エイリアスも自動生成（_create_file_alias で一括処理）
- UXP handler: handlers/file.ts に新規ハンドラを追加
- 設計書セクション 2.2 の全パラメータ定義に従う

### Task 2.2: Layer 全コマンド

**Files:**
- Modify: `photoshop_sdk/schema.py`
- Create: `uxp-plugin/src/handlers/layer.ts`
- Test: `tests/unit/sdk/test_layer_schemas.py`, `tests/integration/test_layer_commands.py`

**実装内容:**
- layer.list, layer.info, layer.create, layer.delete, layer.duplicate, layer.move, layer.rename, layer.set-props, layer.translate, layer.scale, layer.rotate, layer.flip, layer.merge, layer.group, layer.rasterize, layer.link, layer.unlink, layer.select を CommandSchema に追加
- layer.create は `kind` パラメータで pixel/group/adjustment を分岐
- UXP handler: handlers/layer.ts に全ハンドラを実装
- dispatcher.ts に layer モジュールを登録
- レイヤーツリーのシリアライズヘルパー関数を実装

### Task 2.3: Selection 全コマンド

**Files:**
- Modify: `photoshop_sdk/schema.py`
- Create: `uxp-plugin/src/handlers/selection.ts`
- Test: `tests/unit/sdk/test_selection_schemas.py`, `tests/integration/test_selection_commands.py`

**実装内容:**
- selection.all, selection.deselect, selection.inverse, selection.rect, selection.ellipse, selection.by-color-range, selection.feather, selection.expand-contract, selection.save-as-mask, selection.load-from-mask を CommandSchema に追加
- UXP handler: handlers/selection.ts に全ハンドラを実装
- dispatcher.ts に selection モジュールを登録
- CLI に selection グループを登録

### Task 2.4: Path 全コマンド

**Files:**
- Modify: `photoshop_sdk/schema.py`
- Create: `uxp-plugin/src/handlers/path.ts`
- Test: `tests/unit/sdk/test_path_schemas.py`, `tests/integration/test_path_commands.py`

**実装内容:**
- path.list, path.info, path.create, path.delete, path.duplicate, path.to-selection, path.from-selection, path.stroke を CommandSchema に追加
- UXP handler: handlers/path.ts に全ハンドラを実装
- dispatcher.ts に path モジュールを登録
- CLI に path グループを登録

### Task 2.5: Phase 2 のレイヤーツリー・Pydantic モデル

**Files:**
- Modify: `photoshop_sdk/schema.py`
- Modify: `uxp-plugin/src/handlers/layer.ts`

**実装内容:**
- LayerInfo, SelectionInfo 等の Pydantic モデルを schema.py に追加
- レイヤーツリーの再帰的シリアライズ（serializeLayerTree）をUXP handler に実装

### Task 2.6: Phase 2 テスト

**Files:**
- Test: `tests/unit/sdk/test_document_schemas.py`
- Test: `tests/unit/sdk/test_layer_schemas.py`
- Test: `tests/unit/sdk/test_selection_schemas.py`
- Test: `tests/unit/sdk/test_path_schemas.py`
- Test: `tests/integration/test_document_commands.py`
- Test: `tests/integration/test_layer_commands.py`
- Test: `tests/integration/test_selection_commands.py`
- Test: `tests/integration/test_path_commands.py`

**実装内容:**
- 全新規 CommandSchema のバリデーションテスト
- MockUXPClient を使用した統合テスト（正常系・異常系）
- エラーコード（LAYER_NOT_FOUND, PATH_NOT_FOUND, SELECTION_ERROR）のテスト

---

## Phase 3: Text

> 詳細仕様: 設計書セクション 2.4 参照

### Task 3.1: Text 全コマンド

**Files:**
- Modify: `photoshop_sdk/schema.py`
- Create: `uxp-plugin/src/handlers/text.ts`
- Test: `tests/unit/sdk/test_text_schemas.py`, `tests/integration/test_text_commands.py`

**実装内容:**
- text.create, text.get, text.set-contents, text.set-style, text.set-paragraph, text.convert-to-shape, text.convert-to-paragraph, text.convert-to-point を CommandSchema に追加
- UXP handler: handlers/text.ts に全ハンドラを実装
- dispatcher.ts に text モジュールを登録
- CLI に text グループを登録
- 設計書セクション 2.4 の全パラメータ定義に従う

### Task 3.2: Phase 3 テスト

**Files:**
- Test: `tests/unit/sdk/test_text_schemas.py`
- Test: `tests/integration/test_text_commands.py`

**実装内容:**
- Text CommandSchema のバリデーションテスト
- MockUXPClient を使用した統合テスト
- テキストスタイルのパラメータ検証テスト

---

## Phase 4: Filter（typed 15種 + 汎用 apply）

> 詳細仕様: 設計書セクション 2.5 参照

### Task 4.1: FILTER_SCHEMAS 辞書（全60+フィルター定義）

**Files:**
- Create: `photoshop_sdk/filter_schemas.py`
- Test: `tests/unit/sdk/test_filter_schemas.py`

**実装内容:**
- 全フィルターのパラメータスキーマを辞書形式で定義
- 各フィルターの名前・パラメータ型・必須/任意・デフォルト値を明示
- filter.apply の汎用バリデーションに使用

### Task 4.2: Filter 汎用 apply 基盤

**Files:**
- Modify: `photoshop_sdk/schema.py`
- Create: `uxp-plugin/src/handlers/filter.ts`

**実装内容:**
- filter.apply, filter.list, filter.info, filter.apply-batch の CommandSchema 定義
- `--params-file` 対応（_resolve_json_file_params で処理）
- UXP handler: batchPlay ベースの汎用フィルター実行エンジン

### Task 4.3: typed サブコマンド 15種の CommandSchema 定義

**Files:**
- Modify: `photoshop_sdk/schema.py`

**実装内容:**
- filter.gaussian-blur, filter.motion-blur, filter.lens-blur, filter.surface-blur, filter.unsharp-mask, filter.smart-sharpen, filter.high-pass, filter.add-noise, filter.reduce-noise, filter.dust-and-scratches, filter.ripple, filter.spherize, filter.twirl, filter.emboss, filter.find-edges の CommandSchema を追加
- 各フィルターの固有パラメータを ParamSchema で定義

### Task 4.4: UXP filter handler

**Files:**
- Modify: `uxp-plugin/src/handlers/filter.ts`

**実装内容:**
- batchPlay ベースの汎用フィルター実行関数
- typed サブコマンド用の個別ハンドラ（内部的に汎用関数を呼ぶ）
- FILTER_SCHEMAS との名前マッピング
- dispatcher.ts に filter モジュールを登録

### Task 4.5: filter.list / filter.info

**Files:**
- Modify: `photoshop_sdk/schema.py`
- Modify: `uxp-plugin/src/handlers/filter.ts`

**実装内容:**
- filter.list: 利用可能なフィルター一覧とパラメータスキーマを返す
- filter.info: 特定フィルターの詳細パラメータスキーマを返す

### Task 4.6: Phase 4 テスト

**Files:**
- Test: `tests/unit/sdk/test_filter_schemas.py`
- Test: `tests/integration/test_filter_commands.py`

**実装内容:**
- FILTER_SCHEMAS の全エントリの整合性テスト
- typed フィルターの CommandSchema バリデーションテスト
- filter.apply の JSON パラメータ/ファイルパラメータテスト
- filter.apply-batch のテスト
- MockUXPClient を使用した統合テスト

---

## Phase 5: Channel + Guide + History + Action + App

> 詳細仕様: 設計書セクション 2.8-2.12 参照

### Task 5.1: Channel 全コマンド

**Files:**
- Modify: `photoshop_sdk/schema.py`
- Create: `uxp-plugin/src/handlers/channel.ts`
- Test: `tests/unit/sdk/test_channel_schemas.py`, `tests/integration/test_channel_commands.py`

**実装内容:**
- channel.list, channel.info, channel.create, channel.delete, channel.duplicate, channel.merge を CommandSchema に追加
- UXP handler を実装、dispatcher.ts に登録

### Task 5.2: Guide 全コマンド

**Files:**
- Modify: `photoshop_sdk/schema.py`
- Create: `uxp-plugin/src/handlers/guide.ts`
- Test: `tests/unit/sdk/test_guide_schemas.py`, `tests/integration/test_guide_commands.py`

**実装内容:**
- guide.list, guide.add, guide.delete, guide.clear-all を CommandSchema に追加
- UXP handler を実装、dispatcher.ts に登録

### Task 5.3: History 全コマンド

**Files:**
- Modify: `photoshop_sdk/schema.py`
- Create: `uxp-plugin/src/handlers/history.ts`
- Test: `tests/unit/sdk/test_history_schemas.py`, `tests/integration/test_history_commands.py`

**実装内容:**
- history.list, history.revert, history.snapshot-create, history.snapshot-apply を CommandSchema に追加
- UXP handler を実装、dispatcher.ts に登録

### Task 5.4: Action 全コマンド（batchPlay --confirm 必須 + BLOCKED_DESCRIPTORS）

**Files:**
- Modify: `photoshop_sdk/schema.py`
- Create: `uxp-plugin/src/handlers/action.ts`
- Test: `tests/unit/sdk/test_action_schemas.py`, `tests/integration/test_action_commands.py`

**実装内容:**
- action.list, action.play, action.batch-play, action.record を CommandSchema に追加
- action.batch-play は `requires_confirm=True`, `risk_level="destructive"`
- UXP handler に BLOCKED_DESCRIPTORS フィルタリングを実装
- ファイルシステム/ネットワーク/スクリプト実行のデスクリプタをブロック

### Task 5.5: App 全コマンド

**Files:**
- Modify: `photoshop_sdk/schema.py`
- Create: `uxp-plugin/src/handlers/app.ts`
- Test: `tests/unit/sdk/test_app_schemas.py`, `tests/integration/test_app_commands.py`

**実装内容:**
- app.info, app.fonts, app.foreground-color, app.background-color, app.active-document, app.set-active-document, app.current-tool, app.color-settings を CommandSchema に追加
- UXP handler を実装、dispatcher.ts に登録

### Task 5.6: System 拡張

**Files:**
- Modify: `photoshop_sdk/schema.py`
- Modify: `uxp-plugin/src/dispatcher.ts` (system handlers)

**実装内容:**
- system.status, system.reconnect を CommandSchema に追加
- UXP handler を実装

### Task 5.7: Phase 5 テスト

**Files:**
- Test: 各グループのユニットテスト・統合テスト

**実装内容:**
- 全新規 CommandSchema のバリデーションテスト
- batch-play の BLOCKED_DESCRIPTORS テスト
- MockUXPClient を使用した統合テスト

---

## Phase 6: 統合テスト + ドキュメント

> 詳細仕様: 設計書セクション 6 参照

### Task 6.1: 全コマンドの統合テスト

**Files:**
- Modify/Create: `tests/integration/` 配下の各テストファイル

**実装内容:**
- 全コマンドグループの正常系・異常系統合テスト
- エラーコード伝播の検証
- dry-run モードの検証

### Task 6.2: SKILL.md 更新

**Files:**
- Modify: `SKILL.md`

**実装内容:**
- 全コマンド一覧の更新
- 新規コマンドグループの説明追加

### Task 6.3: psd schema コマンドの更新

**Files:**
- Modify: `cli/commands/schema.py`

**実装内容:**
- 全 CommandSchema の情報を表示できるように更新
- グループ別フィルタリング対応

### Task 6.4: 実機テスト

**実装内容:**
- Photoshop + UXP Plugin 環境での全コマンド動作確認
- UXP API のサポート範囲の検証
- 未サポート API の UNSUPPORTED_OPERATION エラー対応

### Task 6.5: バージョンバンプ

**Files:**
- Modify: `pyproject.toml`

**実装内容:**
- バージョンを 2.0.0 にバンプ
