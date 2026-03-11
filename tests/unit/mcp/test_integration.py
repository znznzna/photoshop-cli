"""FastMCP TestClient による統合テスト"""

import json
from unittest.mock import AsyncMock, patch

import pytest
from fastmcp import Client

from mcp_server._run import create_mcp_server


@pytest.fixture
def mcp_server():
    """テスト用 MCP サーバーを生成"""
    return create_mcp_server()


class TestToolRegistration:
    async def test_all_tools_listed(self, mcp_server):
        """全11ツールが登録されている（document_* 5 + file_* 5 + system_ping）"""
        async with Client(mcp_server) as client:
            tools = await client.list_tools()
            tool_names = {t.name for t in tools}
            expected = {
                "document_list",
                "document_info",
                "document_open",
                "document_close",
                "document_save",
                "file_list",
                "file_info",
                "file_open",
                "file_close",
                "file_save",
                "system_ping",
            }
            assert tool_names == expected

    async def test_file_info_has_doc_id_param(self, mcp_server):
        """file_info ツールに doc_id パラメータがある"""
        async with Client(mcp_server) as client:
            tools = await client.list_tools()
            file_info = next(t for t in tools if t.name == "file_info")
            assert "doc_id" in file_info.inputSchema.get("properties", {})
            assert "doc_id" in file_info.inputSchema.get("required", [])

    async def test_file_open_has_dry_run_param(self, mcp_server):
        """file_open ツールに dry_run パラメータがある"""
        async with Client(mcp_server) as client:
            tools = await client.list_tools()
            file_open = next(t for t in tools if t.name == "file_open")
            assert "dry_run" in file_open.inputSchema.get("properties", {})

    async def test_file_list_no_dry_run(self, mcp_server):
        """file_list ツールに dry_run パラメータがない"""
        async with Client(mcp_server) as client:
            tools = await client.list_tools()
            file_list = next(t for t in tools if t.name == "file_list")
            assert "dry_run" not in file_list.inputSchema.get("properties", {})

    async def test_system_ping_no_params(self, mcp_server):
        """system_ping ツールにパラメータがない"""
        async with Client(mcp_server) as client:
            tools = await client.list_tools()
            system_ping = next(t for t in tools if t.name == "system_ping")
            props = system_ping.inputSchema.get("properties", {})
            assert len(props) == 0

    async def test_file_close_has_save_and_dry_run(self, mcp_server):
        """file_close ツールに doc_id, save, dry_run パラメータがある"""
        async with Client(mcp_server) as client:
            tools = await client.list_tools()
            file_close = next(t for t in tools if t.name == "file_close")
            props = file_close.inputSchema.get("properties", {})
            assert "doc_id" in props
            assert "save" in props
            assert "dry_run" in props

    async def test_tool_descriptions_contain_tags(self, mcp_server):
        """mutating ツールの説明にタグが含まれる"""
        async with Client(mcp_server) as client:
            tools = await client.list_tools()
            file_open = next(t for t in tools if t.name == "file_open")
            assert "[mutating]" in file_open.description
            assert "[risk:write]" in file_open.description

            file_close = next(t for t in tools if t.name == "file_close")
            assert "[requires-confirm]" in file_close.description


class TestToolExecution:
    @patch("mcp_server.connection.PhotoshopClient")
    async def test_file_list_execution(self, mock_client_cls, mcp_server):
        """file_list ツールが実行できる"""
        mock_client = AsyncMock()
        mock_client.execute_command = AsyncMock(return_value={"documents": []})
        mock_client_cls.return_value = mock_client

        async with Client(mcp_server) as client:
            result = await client.call_tool("file_list", {})
            # FastMCP Client returns result content - extract the data
            # The result may be wrapped in TextContent
            assert result is not None

    @patch("mcp_server.connection.PhotoshopClient")
    async def test_system_ping_execution(self, mock_client_cls, mcp_server):
        """system_ping ツールが実行できる"""
        mock_client = AsyncMock()
        mock_client.execute_command = AsyncMock(return_value={"status": "ok"})
        mock_client_cls.return_value = mock_client

        async with Client(mcp_server) as client:
            result = await client.call_tool("system_ping", {})
            assert result is not None

    @patch("mcp_server.connection.PhotoshopClient")
    async def test_file_info_execution(self, mock_client_cls, mcp_server):
        """file_info ツールが doc_id → documentId 変換して実行する"""
        mock_client = AsyncMock()
        mock_client.execute_command = AsyncMock(
            return_value={"documentId": 1, "name": "test.psd", "width": 1920, "height": 1080}
        )
        mock_client_cls.return_value = mock_client

        async with Client(mcp_server) as client:
            result = await client.call_tool("file_info", {"doc_id": 1})
            assert result is not None

        mock_client.execute_command.assert_awaited_once_with("file.info", {"documentId": 1}, timeout=30.0)

    async def test_file_save_dry_run(self, mcp_server):
        """file_save の dry_run が実行なしでプレビューを返す"""
        async with Client(mcp_server) as client:
            result = await client.call_tool("file_save", {"doc_id": 1, "dry_run": True})
            assert result is not None


class TestResourceAccess:
    async def test_status_resource(self, mcp_server):
        """photoshop://status リソースが読み取れる"""
        async with Client(mcp_server) as client:
            resources = await client.list_resources()
            resource_uris = [str(r.uri) for r in resources]
            assert "photoshop://status" in resource_uris

            content = await client.read_resource("photoshop://status")
            # FastMCP 3.x returns a list of TextResourceContents
            assert len(content) == 1
            raw = content[0].text if hasattr(content[0], "text") else content[0]
            data = json.loads(raw)
            assert data["state"] == "disconnected"


class TestBackwardCompat:
    def test_server_py_exports(self):
        """server.py が main と mcp を再公開する"""
        from mcp_server.server import main, mcp

        assert callable(main)
        assert mcp is not None
        assert mcp.name == "photoshop-cli"
