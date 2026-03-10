"""FastMCP server for Photoshop CLI - Phase 1 Stub"""

from __future__ import annotations

import logging

from fastmcp import FastMCP

logger = logging.getLogger(__name__)

mcp = FastMCP(
    name="photoshop-cli",
    instructions=(
        "Adobe Photoshop control server. "
        "Use the available tools to open, close, save, and inspect Photoshop documents. "
        "Photoshop must be running with the UXP Plugin active."
    ),
)


# ── Phase 1 Stub ────────────────────────────────────────────────────────
# 実装は Phase 2 で行う。ここでは起動確認のみ。

@mcp.tool()
async def file_list() -> dict:
    """List all open Photoshop documents. (Phase 1 stub)"""
    # TODO: Phase 2 で実装
    raise NotImplementedError("file_list is not yet implemented (Phase 2)")


@mcp.tool()
async def file_info(doc_id: int) -> dict:
    """Get info for a specific document. (Phase 1 stub)"""
    # TODO: Phase 2 で実装
    raise NotImplementedError("file_info is not yet implemented (Phase 2)")


@mcp.tool()
async def file_open(path: str) -> dict:
    """Open a PSD file in Photoshop. (Phase 1 stub)"""
    # TODO: Phase 2 で実装
    raise NotImplementedError("file_open is not yet implemented (Phase 2)")


def main():
    """MCP Server エントリポイント"""
    mcp.run()


if __name__ == "__main__":
    main()
