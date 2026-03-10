

def test_mcp_server_importable():
    """MCP server が import できる"""
    from mcp_server.server import main, mcp
    assert callable(main)
    assert mcp is not None


def test_mcp_app_name():
    from mcp_server.server import mcp
    # FastMCP アプリの name 確認
    assert "photoshop" in mcp.name.lower() or "psd" in mcp.name.lower()
