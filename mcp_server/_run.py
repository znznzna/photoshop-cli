"""FastMCP サーバー初期化とツール登録"""

from __future__ import annotations

import json
import logging

from fastmcp import FastMCP

from .connection import ConnectionManager
from .instructions import MCP_INSTRUCTIONS
from .tool_registry import register_all_tools

logger = logging.getLogger(__name__)


def create_mcp_server() -> FastMCP:
    """FastMCP サーバーを構築して返す"""
    mcp = FastMCP(
        name="photoshop-cli",
        instructions=MCP_INSTRUCTIONS,
    )

    conn_mgr = ConnectionManager()
    register_all_tools(mcp, conn_mgr)

    @mcp.resource("photoshop://status")
    async def connection_status() -> str:
        """Photoshop 接続状態"""
        return json.dumps(await conn_mgr.status())

    return mcp


mcp = create_mcp_server()


def main():
    """MCP Server エントリポイント"""
    mcp.run()
