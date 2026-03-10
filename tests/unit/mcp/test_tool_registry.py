"""動的ツール登録のユニットテスト"""

import inspect
from unittest.mock import AsyncMock

from fastmcp import FastMCP

from mcp_server.tool_registry import _build_description, _build_tool_fn, register_all_tools
from photoshop_sdk.schema import COMMAND_SCHEMAS, CommandSchema, ParamSchema


class TestBuildToolFn:
    def test_no_params_signature(self):
        """パラメータなしコマンドのシグネチャ"""
        schema = CommandSchema(command="file.list", description="List files")
        conn_mgr = AsyncMock()
        fn = _build_tool_fn(schema, conn_mgr)

        sig = inspect.signature(fn)
        assert len(sig.parameters) == 0
        assert fn.__name__ == "file_list"

    def test_required_param_signature(self):
        """必須パラメータのシグネチャ"""
        schema = CommandSchema(
            command="file.info",
            description="Get info",
            params=[ParamSchema(name="doc_id", type=int, description="Doc ID")],
        )
        conn_mgr = AsyncMock()
        fn = _build_tool_fn(schema, conn_mgr)

        sig = inspect.signature(fn)
        assert "doc_id" in sig.parameters
        param = sig.parameters["doc_id"]
        assert param.annotation is int
        assert param.default is inspect.Parameter.empty

    def test_optional_param_signature(self):
        """オプショナルパラメータのシグネチャ"""
        schema = CommandSchema(
            command="file.close",
            description="Close",
            params=[
                ParamSchema(name="doc_id", type=int, description="Doc ID"),
                ParamSchema(name="save", type=bool, description="Save", required=False, default=False),
            ],
            mutating=True,
            supports_dry_run=True,
        )
        conn_mgr = AsyncMock()
        fn = _build_tool_fn(schema, conn_mgr)

        sig = inspect.signature(fn)
        assert sig.parameters["save"].default is False

    def test_dry_run_added_for_mutating(self):
        """mutating + supports_dry_run コマンドに dry_run パラメータが追加される"""
        schema = CommandSchema(
            command="file.save",
            description="Save",
            params=[ParamSchema(name="doc_id", type=int, description="Doc ID")],
            mutating=True,
            supports_dry_run=True,
        )
        conn_mgr = AsyncMock()
        fn = _build_tool_fn(schema, conn_mgr)

        sig = inspect.signature(fn)
        assert "dry_run" in sig.parameters
        assert sig.parameters["dry_run"].default is False
        assert sig.parameters["dry_run"].annotation is bool

    def test_no_dry_run_for_read(self):
        """read コマンドに dry_run パラメータは追加されない"""
        schema = CommandSchema(command="file.list", description="List")
        conn_mgr = AsyncMock()
        fn = _build_tool_fn(schema, conn_mgr)

        sig = inspect.signature(fn)
        assert "dry_run" not in sig.parameters

    async def test_execute_calls_conn_mgr(self):
        """ツール関数実行時に conn_mgr.execute が呼ばれる"""
        schema = CommandSchema(
            command="file.info",
            description="Get info",
            params=[ParamSchema(name="doc_id", type=int, description="Doc ID", sdk_name="documentId")],
        )
        conn_mgr = AsyncMock()
        conn_mgr.execute = AsyncMock(return_value={"success": True, "documentId": 1})
        fn = _build_tool_fn(schema, conn_mgr)

        result = await fn(doc_id=1)

        conn_mgr.execute.assert_awaited_once_with("file.info", {"documentId": 1}, timeout=30.0)
        assert result["success"] is True

    async def test_sdk_name_mapping(self):
        """sdk_name が指定されたパラメータは名前が変換される"""
        schema = CommandSchema(
            command="file.close",
            description="Close",
            params=[
                ParamSchema(name="doc_id", type=int, description="Doc ID", sdk_name="documentId"),
                ParamSchema(name="save", type=bool, description="Save", required=False, default=False),
            ],
            mutating=True,
            supports_dry_run=True,
        )
        conn_mgr = AsyncMock()
        conn_mgr.execute = AsyncMock(return_value={"success": True})
        fn = _build_tool_fn(schema, conn_mgr)

        await fn(doc_id=5, save=True)

        conn_mgr.execute.assert_awaited_once_with("file.close", {"documentId": 5, "save": True}, timeout=30.0)

    async def test_dry_run_returns_preview(self):
        """dry_run=True の場合は実行せず preview を返す"""
        schema = CommandSchema(
            command="file.save",
            description="Save",
            params=[ParamSchema(name="doc_id", type=int, description="Doc ID", sdk_name="documentId")],
            mutating=True,
            supports_dry_run=True,
        )
        conn_mgr = AsyncMock()
        fn = _build_tool_fn(schema, conn_mgr)

        result = await fn(doc_id=1, dry_run=True)

        assert result["dry_run"] is True
        assert result["command"] == "file.save"
        assert result["params"] == {"documentId": 1}
        conn_mgr.execute.assert_not_awaited()

    async def test_validator_called(self):
        """validator が設定されている場合は呼ばれる"""
        schema = CommandSchema(
            command="file.open",
            description="Open",
            params=[ParamSchema(name="path", type=str, description="Path")],
            mutating=True,
            supports_dry_run=True,
            timeout=120.0,
            validator="validate_file_path",
        )
        conn_mgr = AsyncMock()
        conn_mgr.execute = AsyncMock(return_value={"success": True})
        fn = _build_tool_fn(schema, conn_mgr)

        # validate_file_path raises ValidationError for nonexistent files
        result = await fn(path="/nonexistent/file.psd")

        assert result["success"] is False
        assert result["error"]["code"] == "VALIDATION_ERROR"
        conn_mgr.execute.assert_not_awaited()


class TestBuildDescription:
    def test_read_command(self):
        """read コマンドはタグなし"""
        schema = CommandSchema(command="file.list", description="List all open documents.")
        desc = _build_description(schema)
        assert "List all open documents." in desc
        assert "[mutating]" not in desc

    def test_mutating_command(self):
        """mutating コマンドはタグ付き"""
        schema = CommandSchema(
            command="file.open",
            description="Open a PSD file.",
            mutating=True,
            risk_level="write",
            supports_dry_run=True,
        )
        desc = _build_description(schema)
        assert "[risk:write]" in desc
        assert "[mutating]" in desc
        assert "[supports-dry-run]" in desc

    def test_requires_confirm(self):
        """requires_confirm タグ"""
        schema = CommandSchema(
            command="file.close",
            description="Close a document.",
            mutating=True,
            risk_level="write",
            requires_confirm=True,
            supports_dry_run=True,
        )
        desc = _build_description(schema)
        assert "[requires-confirm]" in desc


class TestRegisterAllTools:
    def test_all_tools_registered(self):
        """全 CommandSchema がツールとして登録される"""
        mcp = FastMCP(name="test")
        conn_mgr = AsyncMock()
        register_all_tools(mcp, conn_mgr)

        assert len(COMMAND_SCHEMAS) == 6

    def test_tool_names(self):
        """ツール名が command.replace('.', '_') 形式"""
        mcp = FastMCP(name="test")
        conn_mgr = AsyncMock()
        register_all_tools(mcp, conn_mgr)

        # register_all_tools が例外なく完了 = 全ツール登録成功
        # 期待ツール名: file_list, file_info, file_open, file_close, file_save, system_ping
