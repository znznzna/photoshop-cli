"""auto_commands.py のユニットテスト

CLI コマンド自動生成機構のテスト:
- build_click_command: CommandSchema → click.Command 変換
- _parse_json_option: JSON 文字列パース
- _resolve_json_file_params: --param-file 解決
- register_group_commands: Click グループへの登録
- dry-run サポート
- validator サポート
- SDK パラメータ名変換 (effective_sdk_name)
"""

import json
from unittest.mock import AsyncMock, patch

import click
from click.testing import CliRunner

from cli.auto_commands import (
    _parse_json_option,
    _resolve_json_file_params,
    build_click_command,
    register_group_commands,
)
from photoshop_sdk.schema import CommandSchema, ParamSchema

# ============================================================
# _parse_json_option
# ============================================================


class TestParseJsonOption:
    def test_valid_json_dict(self):
        result = _parse_json_option('{"key": "value"}', "test_param")
        assert result == {"key": "value"}

    def test_valid_json_list(self):
        result = _parse_json_option('[1, 2, 3]', "test_param")
        assert result == [1, 2, 3]

    def test_invalid_json_error_message(self):
        """無効な JSON でエラーメッセージにパラメータ名と位置情報を含む"""
        try:
            _parse_json_option("{invalid json}", "my_param")
            assert False, "Should have raised click.BadParameter"
        except click.BadParameter as e:
            msg = str(e)
            assert "my_param" in msg
            # エラーメッセージにヒントまたは位置情報が含まれる
            assert "JSON" in msg or "json" in msg

    def test_none_returns_none(self):
        result = _parse_json_option(None, "test_param")
        assert result is None

    def test_empty_string_returns_none(self):
        result = _parse_json_option("", "test_param")
        assert result is None


# ============================================================
# _resolve_json_file_params
# ============================================================


class TestResolveJsonFileParams:
    def test_file_overrides_inline(self, tmp_path):
        """--param-file が --param を上書きする"""
        json_file = tmp_path / "data.json"
        json_file.write_text('{"from": "file"}')

        params = {"data": '{"from": "inline"}', "data_file": str(json_file)}
        result = _resolve_json_file_params(params)
        assert result["data"] == {"from": "file"}
        assert "data_file" not in result

    def test_inline_only(self):
        """--param-file がない場合は --param をパースする"""
        params = {"data": '{"from": "inline"}'}
        result = _resolve_json_file_params(params)
        assert result["data"] == '{"from": "inline"}'

    def test_file_not_found(self, tmp_path):
        """存在しないファイルで click.BadParameter"""
        params = {"data_file": str(tmp_path / "nonexistent.json")}
        try:
            _resolve_json_file_params(params)
            assert False, "Should have raised click.BadParameter"
        except click.BadParameter:
            pass

    def test_file_invalid_json(self, tmp_path):
        """不正 JSON ファイルで click.BadParameter"""
        json_file = tmp_path / "bad.json"
        json_file.write_text("{not valid json}")
        params = {"data_file": str(json_file)}
        try:
            _resolve_json_file_params(params)
            assert False, "Should have raised click.BadParameter"
        except click.BadParameter:
            pass

    def test_no_file_params(self):
        """_file パラメータがない場合はそのまま返す"""
        params = {"doc_id": 1, "name": "test"}
        result = _resolve_json_file_params(params)
        assert result == {"doc_id": 1, "name": "test"}


# ============================================================
# build_click_command
# ============================================================


class TestBuildClickCommand:
    def test_basic_command_no_params(self):
        """パラメータなしの基本コマンド"""
        schema = CommandSchema(command="file.list", description="List files")
        cmd = build_click_command(schema)

        assert isinstance(cmd, click.Command)
        assert cmd.name == "list"
        assert "List files" in (cmd.help or "")

    def test_command_with_int_param(self):
        """int パラメータが --option として生成される"""
        schema = CommandSchema(
            command="file.info",
            description="Get info",
            params=[ParamSchema(name="doc_id", type=int, description="Document ID")],
        )
        cmd = build_click_command(schema)

        param_names = [p.name for p in cmd.params]
        assert "doc_id" in param_names

    def test_command_with_bool_param_flag(self):
        """bool パラメータが --foo/--no-foo フラグパターンになる"""
        schema = CommandSchema(
            command="file.close",
            description="Close file",
            params=[
                ParamSchema(name="save", type=bool, description="Save before close", required=False, default=False),
            ],
        )
        cmd = build_click_command(schema)

        # bool は --save/--no-save パターン
        save_param = next(p for p in cmd.params if p.name == "save")
        assert save_param.is_flag

    def test_command_with_required_param(self):
        """required=True のパラメータは Click でも required"""
        schema = CommandSchema(
            command="file.info",
            description="Get info",
            params=[ParamSchema(name="doc_id", type=int, description="Document ID", required=True)],
        )
        cmd = build_click_command(schema)
        doc_id_param = next(p for p in cmd.params if p.name == "doc_id")
        assert doc_id_param.required

    def test_command_with_optional_param(self):
        """required=False のパラメータは Click でもオプショナル"""
        schema = CommandSchema(
            command="file.close",
            description="Close",
            params=[
                ParamSchema(name="save", type=bool, description="Save", required=False, default=False),
            ],
        )
        cmd = build_click_command(schema)
        save_param = next(p for p in cmd.params if p.name == "save")
        assert not save_param.required

    def test_command_with_dict_param_generates_file_option(self):
        """dict パラメータが --param と --param-file の両方を生成する"""
        schema = CommandSchema(
            command="layer.style",
            description="Apply style",
            params=[ParamSchema(name="style", type=dict, description="Style object")],
        )
        cmd = build_click_command(schema)

        param_names = [p.name for p in cmd.params]
        assert "style" in param_names
        assert "style_file" in param_names

    def test_command_with_list_param_generates_file_option(self):
        """list パラメータが --param と --param-file の両方を生成する"""
        schema = CommandSchema(
            command="batch.run",
            description="Run batch",
            params=[ParamSchema(name="actions", type=list, description="Actions list")],
        )
        cmd = build_click_command(schema)

        param_names = [p.name for p in cmd.params]
        assert "actions" in param_names
        assert "actions_file" in param_names

    def test_mutating_command_has_dry_run(self):
        """supports_dry_run=True のコマンドが --dry-run をサポート"""
        schema = CommandSchema(
            command="file.open",
            description="Open file",
            mutating=True,
            supports_dry_run=True,
        )
        cmd = build_click_command(schema)
        # dry-run は ctx.obj から取得するので、コマンド自体にはパラメータ不要
        # ただし、コマンドが dry-run モードで動作するか検証
        assert cmd is not None


# ============================================================
# build_click_command の実行テスト（CliRunner 使用）
# ============================================================


class TestBuildClickCommandExecution:
    def _make_group_with_command(self, schema):
        """テスト用 Click グループにコマンドを登録"""

        @click.group()
        @click.option("--output", "-o", default="json")
        @click.option("--dry-run", is_flag=True, default=False)
        @click.option("--timeout", "-t", type=float, default=None)
        @click.option("--fields", "-f", type=str, default=None)
        @click.pass_context
        def grp(ctx, output, dry_run, timeout, fields):
            ctx.ensure_object(dict)
            ctx.obj["output"] = output
            ctx.obj["dry_run"] = dry_run
            ctx.obj["timeout"] = timeout or 30.0
            ctx.obj["fields"] = [f.strip() for f in fields.split(",") if f.strip()] if fields else None

        cmd = build_click_command(schema)
        grp.add_command(cmd)
        return grp

    def test_execute_no_params(self):
        """パラメータなしコマンドの実行"""
        schema = CommandSchema(command="file.list", description="List files")
        grp = self._make_group_with_command(schema)

        mock_cm = AsyncMock()
        mock_cm.execute = AsyncMock(return_value={"success": True, "documents": []})

        runner = CliRunner()
        with patch("cli.auto_commands._get_connection_manager", return_value=mock_cm):
            result = runner.invoke(grp, ["--output", "json", "list"])

        assert result.exit_code == 0, f"exit_code={result.exit_code}, output={result.output}"
        mock_cm.execute.assert_called_once_with("file.list", {}, timeout=30.0)

    def test_execute_with_int_param(self):
        """int パラメータ付きコマンドの実行"""
        schema = CommandSchema(
            command="file.info",
            description="Get info",
            params=[ParamSchema(name="doc_id", type=int, description="Document ID", sdk_name="documentId")],
        )
        grp = self._make_group_with_command(schema)

        mock_cm = AsyncMock()
        mock_cm.execute = AsyncMock(return_value={"success": True, "documentId": 1, "name": "test.psd"})

        runner = CliRunner()
        with patch("cli.auto_commands._get_connection_manager", return_value=mock_cm):
            result = runner.invoke(grp, ["--output", "json", "info", "--doc-id", "1"])

        assert result.exit_code == 0, f"exit_code={result.exit_code}, output={result.output}"
        # sdk_name="documentId" に変換される
        mock_cm.execute.assert_called_once_with("file.info", {"documentId": 1}, timeout=30.0)

    def test_execute_with_bool_param(self):
        """bool パラメータ付きコマンドの実行"""
        schema = CommandSchema(
            command="file.close",
            description="Close file",
            params=[
                ParamSchema(name="doc_id", type=int, description="Document ID", sdk_name="documentId"),
                ParamSchema(name="save", type=bool, description="Save", required=False, default=False),
            ],
        )
        grp = self._make_group_with_command(schema)

        mock_cm = AsyncMock()
        mock_cm.execute = AsyncMock(return_value={"success": True, "closed": True})

        runner = CliRunner()
        with patch("cli.auto_commands._get_connection_manager", return_value=mock_cm):
            result = runner.invoke(grp, ["--output", "json", "close", "--doc-id", "1", "--save"])

        assert result.exit_code == 0, f"exit_code={result.exit_code}, output={result.output}"
        mock_cm.execute.assert_called_once_with("file.close", {"documentId": 1, "save": True}, timeout=30.0)

    def test_execute_with_no_flag(self):
        """--no-save フラグの動作（デフォルトと同じなので SDK パラメータから除外）"""
        schema = CommandSchema(
            command="file.close",
            description="Close file",
            params=[
                ParamSchema(name="doc_id", type=int, description="Document ID", sdk_name="documentId"),
                ParamSchema(name="save", type=bool, description="Save", required=False, default=False),
            ],
        )
        grp = self._make_group_with_command(schema)

        mock_cm = AsyncMock()
        mock_cm.execute = AsyncMock(return_value={"success": True, "closed": True})

        runner = CliRunner()
        with patch("cli.auto_commands._get_connection_manager", return_value=mock_cm):
            result = runner.invoke(grp, ["--output", "json", "close", "--doc-id", "1", "--no-save"])

        assert result.exit_code == 0
        # --no-save は default=False と同じなので SDK パラメータに含まれない
        mock_cm.execute.assert_called_once_with("file.close", {"documentId": 1}, timeout=30.0)

    def test_dry_run_mode(self):
        """dry-run モードでは実行せず、コマンド情報を表示"""
        schema = CommandSchema(
            command="file.open",
            description="Open file",
            params=[ParamSchema(name="path", type=str, description="File path")],
            mutating=True,
            supports_dry_run=True,
        )
        grp = self._make_group_with_command(schema)

        runner = CliRunner()
        # ConnectionManager は呼ばれないはず
        with patch("cli.auto_commands._get_connection_manager") as mock_get_cm:
            result = runner.invoke(grp, ["--output", "json", "--dry-run", "open", "--path", "/test/file.psd"])

        assert result.exit_code == 0, f"exit_code={result.exit_code}, output={result.output}"
        data = json.loads(result.output)
        assert data["dry_run"] is True
        assert data["command"] == "file.open"
        mock_get_cm.assert_not_called()

    def test_dry_run_non_mutating_ignores(self):
        """non-mutating コマンドでは dry-run フラグが無視され通常実行される"""
        schema = CommandSchema(
            command="file.list",
            description="List files",
            mutating=False,
            supports_dry_run=False,
        )
        grp = self._make_group_with_command(schema)

        mock_cm = AsyncMock()
        mock_cm.execute = AsyncMock(return_value={"success": True, "documents": []})

        runner = CliRunner()
        with patch("cli.auto_commands._get_connection_manager", return_value=mock_cm):
            result = runner.invoke(grp, ["--output", "json", "--dry-run", "list"])

        assert result.exit_code == 0
        # 非 mutating なので実行される
        mock_cm.execute.assert_called_once()

    def test_execute_error_connection(self):
        """接続エラーで exit code 2"""
        schema = CommandSchema(command="file.list", description="List files")
        grp = self._make_group_with_command(schema)

        mock_cm = AsyncMock()
        mock_cm.execute = AsyncMock(
            return_value={
                "success": False,
                "error": {"code": "CONNECTION_ERROR", "message": "Not connected", "category": "connection"},
            }
        )

        runner = CliRunner()
        with patch("cli.auto_commands._get_connection_manager", return_value=mock_cm):
            result = runner.invoke(grp, ["--output", "json", "list"])

        assert result.exit_code == 2

    def test_execute_error_timeout(self):
        """タイムアウトエラーで exit code 3"""
        schema = CommandSchema(command="file.list", description="List files")
        grp = self._make_group_with_command(schema)

        mock_cm = AsyncMock()
        mock_cm.execute = AsyncMock(
            return_value={
                "success": False,
                "error": {"code": "TIMEOUT_ERROR", "message": "Timed out", "category": "timeout"},
            }
        )

        runner = CliRunner()
        with patch("cli.auto_commands._get_connection_manager", return_value=mock_cm):
            result = runner.invoke(grp, ["--output", "json", "list"])

        assert result.exit_code == 3

    def test_execute_error_validation(self):
        """バリデーションエラーで exit code 4"""
        schema = CommandSchema(command="file.list", description="List files")
        grp = self._make_group_with_command(schema)

        mock_cm = AsyncMock()
        mock_cm.execute = AsyncMock(
            return_value={
                "success": False,
                "error": {"code": "VALIDATION_ERROR", "message": "Invalid", "category": "validation"},
            }
        )

        runner = CliRunner()
        with patch("cli.auto_commands._get_connection_manager", return_value=mock_cm):
            result = runner.invoke(grp, ["--output", "json", "list"])

        assert result.exit_code == 4

    def test_execute_error_not_found(self):
        """not_found エラーで exit code 5"""
        schema = CommandSchema(command="file.info", description="Get info")
        grp = self._make_group_with_command(schema)

        mock_cm = AsyncMock()
        mock_cm.execute = AsyncMock(
            return_value={
                "success": False,
                "error": {"code": "DOCUMENT_NOT_FOUND", "message": "Not found", "category": "not_found"},
            }
        )

        runner = CliRunner()
        with patch("cli.auto_commands._get_connection_manager", return_value=mock_cm):
            result = runner.invoke(grp, ["--output", "json", "info"])

        assert result.exit_code == 5

    def test_execute_error_general(self):
        """一般エラーで exit code 1"""
        schema = CommandSchema(command="file.list", description="List files")
        grp = self._make_group_with_command(schema)

        mock_cm = AsyncMock()
        mock_cm.execute = AsyncMock(
            return_value={
                "success": False,
                "error": {"code": "SDK_ERROR", "message": "Unknown", "category": "sdk"},
            }
        )

        runner = CliRunner()
        with patch("cli.auto_commands._get_connection_manager", return_value=mock_cm):
            result = runner.invoke(grp, ["--output", "json", "list"])

        assert result.exit_code == 1

    def test_validator_called(self, tmp_path):
        """validator 指定コマンドでバリデーターが呼ばれる"""
        f = tmp_path / "test.psd"
        f.write_text("dummy")

        schema = CommandSchema(
            command="file.open",
            description="Open file",
            params=[ParamSchema(name="path", type=str, description="File path")],
            mutating=True,
            supports_dry_run=True,
            validator="validate_file_path",
        )
        grp = self._make_group_with_command(schema)

        mock_cm = AsyncMock()
        mock_cm.execute = AsyncMock(return_value={"success": True, "documentId": 1})

        runner = CliRunner()
        with patch("cli.auto_commands._get_connection_manager", return_value=mock_cm):
            result = runner.invoke(grp, ["--output", "json", "open", "--path", str(f)])

        assert result.exit_code == 0, f"exit_code={result.exit_code}, output={result.output}"

    def test_validator_rejects_invalid(self):
        """validator が無効な入力を拒否 → exit code 4"""
        schema = CommandSchema(
            command="file.open",
            description="Open file",
            params=[ParamSchema(name="path", type=str, description="File path")],
            validator="validate_file_path",
        )
        grp = self._make_group_with_command(schema)

        runner = CliRunner()
        result = runner.invoke(grp, ["--output", "json", "open", "--path", "/nonexistent/file.psd"])
        assert result.exit_code == 4

    def test_sdk_name_conversion(self):
        """sdk_name が指定されたパラメータは SDK 名で送信される"""
        schema = CommandSchema(
            command="file.info",
            description="Get info",
            params=[
                ParamSchema(name="doc_id", type=int, description="Document ID", sdk_name="documentId"),
            ],
        )
        grp = self._make_group_with_command(schema)

        mock_cm = AsyncMock()
        mock_cm.execute = AsyncMock(return_value={"success": True})

        runner = CliRunner()
        with patch("cli.auto_commands._get_connection_manager", return_value=mock_cm):
            result = runner.invoke(grp, ["--output", "json", "info", "--doc-id", "42"])

        assert result.exit_code == 0
        call_params = mock_cm.execute.call_args[0][1]
        assert "documentId" in call_params
        assert call_params["documentId"] == 42
        assert "doc_id" not in call_params

    def test_optional_param_omitted_when_default(self):
        """required=False でデフォルト値と同じ場合、SDK パラメータに含まれない"""
        schema = CommandSchema(
            command="file.close",
            description="Close file",
            params=[
                ParamSchema(name="doc_id", type=int, description="Document ID", sdk_name="documentId"),
                ParamSchema(name="save", type=bool, description="Save", required=False, default=False),
            ],
        )
        grp = self._make_group_with_command(schema)

        mock_cm = AsyncMock()
        mock_cm.execute = AsyncMock(return_value={"success": True})

        runner = CliRunner()
        with patch("cli.auto_commands._get_connection_manager", return_value=mock_cm):
            result = runner.invoke(grp, ["--output", "json", "close", "--doc-id", "1"])

        assert result.exit_code == 0
        call_params = mock_cm.execute.call_args[0][1]
        assert "save" not in call_params

    def test_schema_timeout_used(self):
        """スキーマの timeout が使われる"""
        schema = CommandSchema(command="system.ping", description="Ping", timeout=5.0)
        grp = self._make_group_with_command(schema)

        mock_cm = AsyncMock()
        mock_cm.execute = AsyncMock(return_value={"success": True})

        runner = CliRunner()
        with patch("cli.auto_commands._get_connection_manager", return_value=mock_cm):
            result = runner.invoke(grp, ["--output", "json", "ping"])

        assert result.exit_code == 0
        mock_cm.execute.assert_called_once_with("system.ping", {}, timeout=5.0)

    def test_cli_timeout_overrides_schema(self):
        """CLI --timeout がスキーマの timeout を上書きする"""
        schema = CommandSchema(command="system.ping", description="Ping", timeout=5.0)
        grp = self._make_group_with_command(schema)

        mock_cm = AsyncMock()
        mock_cm.execute = AsyncMock(return_value={"success": True})

        runner = CliRunner()
        with patch("cli.auto_commands._get_connection_manager", return_value=mock_cm):
            result = runner.invoke(grp, ["--output", "json", "--timeout", "60", "ping"])

        assert result.exit_code == 0
        mock_cm.execute.assert_called_once_with("system.ping", {}, timeout=60.0)

    def test_dict_param_from_json_string(self):
        """dict パラメータを JSON 文字列で渡す"""
        schema = CommandSchema(
            command="layer.style",
            description="Apply style",
            params=[ParamSchema(name="style", type=dict, description="Style object")],
        )
        grp = self._make_group_with_command(schema)

        mock_cm = AsyncMock()
        mock_cm.execute = AsyncMock(return_value={"success": True})

        runner = CliRunner()
        with patch("cli.auto_commands._get_connection_manager", return_value=mock_cm):
            result = runner.invoke(grp, ["--output", "json", "style", "--style", '{"color": "red"}'])

        assert result.exit_code == 0, f"exit_code={result.exit_code}, output={result.output}"
        call_params = mock_cm.execute.call_args[0][1]
        assert call_params["style"] == {"color": "red"}

    def test_dict_param_from_file(self, tmp_path):
        """dict パラメータをファイルから読み込む"""
        json_file = tmp_path / "style.json"
        json_file.write_text('{"color": "blue"}')

        schema = CommandSchema(
            command="layer.style",
            description="Apply style",
            params=[ParamSchema(name="style", type=dict, description="Style object")],
        )
        grp = self._make_group_with_command(schema)

        mock_cm = AsyncMock()
        mock_cm.execute = AsyncMock(return_value={"success": True})

        runner = CliRunner()
        with patch("cli.auto_commands._get_connection_manager", return_value=mock_cm):
            result = runner.invoke(
                grp, ["--output", "json", "style", "--style-file", str(json_file)]
            )

        assert result.exit_code == 0, f"exit_code={result.exit_code}, output={result.output}"
        call_params = mock_cm.execute.call_args[0][1]
        assert call_params["style"] == {"color": "blue"}


# ============================================================
# register_group_commands
# ============================================================


class TestRegisterGroupCommands:
    def test_register_filters_by_group_name(self):
        """group_name でフィルタしてコマンドを登録"""
        schemas = [
            CommandSchema(command="file.list", description="List files"),
            CommandSchema(command="file.info", description="Get info"),
            CommandSchema(command="system.ping", description="Ping"),
        ]

        @click.group()
        def grp():
            pass

        register_group_commands(grp, "file", schemas=schemas)

        cmd_names = list(grp.commands.keys())
        assert "list" in cmd_names
        assert "info" in cmd_names
        assert "ping" not in cmd_names

    def test_register_uses_global_schemas_by_default(self):
        """schemas=None の場合は COMMAND_SCHEMAS を使用"""

        @click.group()
        def grp():
            pass

        register_group_commands(grp, "file")

        # COMMAND_SCHEMAS に file.list, file.info, file.open, file.close, file.save がある
        cmd_names = list(grp.commands.keys())
        assert "list" in cmd_names
        assert "info" in cmd_names

    def test_register_no_matching_commands(self):
        """マッチするコマンドがない場合は空"""
        schemas = [
            CommandSchema(command="system.ping", description="Ping"),
        ]

        @click.group()
        def grp():
            pass

        register_group_commands(grp, "file", schemas=schemas)

        assert len(grp.commands) == 0
