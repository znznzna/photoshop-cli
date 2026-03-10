"""
OS横断のパス解決モジュール。
優先順位: 環境変数 > OS判定デフォルト

macOS/Linux: /tmp/photoshop_ws_port.txt
Windows: %TEMP%/photoshop_ws_port.txt
"""

import os
import sys
import tempfile
from pathlib import Path


def get_port_file() -> Path:
    """WebSocket ポートファイルのパスを返す"""
    env = os.environ.get("PS_PORT_FILE")
    if env:
        return Path(env)
    if sys.platform == "win32":
        return Path(tempfile.gettempdir()) / "photoshop_ws_port.txt"
    # macOS/Linux: /tmp に固定
    return Path("/tmp") / "photoshop_ws_port.txt"


def get_ws_port_file() -> Path:
    """get_port_file の別名（後方互換）"""
    return get_port_file()
