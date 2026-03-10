"""後方互換: mcp オブジェクトと main() を再公開"""

from mcp_server._run import main, mcp

__all__ = ["main", "mcp"]
