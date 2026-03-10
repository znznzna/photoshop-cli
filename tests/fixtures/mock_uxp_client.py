"""
MockUXPClient: UXP Plugin の代わりに WS クライアントとして接続するモック。

使用例:
    async with MockUXPClient(port_file="/tmp/photoshop_ws_port.txt") as mock:
        mock.register_response("file.list", {"documents": [...]})
        result = await client.file_list()
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import websockets

logger = logging.getLogger(__name__)


class MockUXPClient:
    """UXP Plugin のふりをする WebSocket クライアントモック"""

    def __init__(self, port_file: str, connect_delay: float = 0.05):
        self._port_file = Path(port_file)
        self._connect_delay = connect_delay
        self._responses: Dict[str, Any] = {}
        self._handlers: Dict[str, Callable] = {}
        self._ws: Optional[Any] = None
        self._task: Optional[asyncio.Task] = None
        self._connected = False

    def register_response(self, command: str, result: Any) -> None:
        """コマンドに対する固定レスポンスを登録する"""
        self._responses[command] = result

    def register_handler(self, command: str, handler: Callable) -> None:
        """コマンドに対する動的ハンドラを登録する（params を受け取り result を返す）"""
        self._handlers[command] = handler

    async def connect(self) -> None:
        """WS サーバー（ResilientWSBridge）に接続する"""
        # ポートファイルを読む
        await asyncio.sleep(self._connect_delay)
        port_text = self._port_file.read_text().strip()
        port = int(port_text)
        uri = f"ws://localhost:{port}"
        self._ws = await websockets.connect(uri)
        self._connected = True
        self._task = asyncio.create_task(self._receive_loop())
        logger.info(f"MockUXPClient connected to {uri}")

    async def _receive_loop(self) -> None:
        """サーバーからのコマンドを受信してレスポンスを送り返す"""
        try:
            async for raw in self._ws:
                msg = json.loads(raw)
                await self._handle_command(msg)
        except websockets.exceptions.ConnectionClosedError:
            logger.info("MockUXPClient: WS connection closed")
        except Exception as e:
            logger.error(f"MockUXPClient receive loop error: {e}")
        finally:
            self._connected = False

    async def _handle_command(self, msg: Dict[str, Any]) -> None:
        """コマンドを処理してレスポンスを送信する"""
        request_id = msg.get("id")
        command = msg.get("command", "")
        params = msg.get("params", {})

        # 動的ハンドラを優先
        if command in self._handlers:
            try:
                result = self._handlers[command](params)
                if asyncio.iscoroutine(result):
                    result = await result
                resp = {"id": request_id, "success": True, "result": result}
            except Exception as e:
                resp = {
                    "id": request_id,
                    "success": False,
                    "error": {"code": "HANDLER_ERROR", "message": str(e)},
                }
        elif command in self._responses:
            stored = self._responses[command]
            if isinstance(stored, dict) and "error" in stored:
                resp = {"id": request_id, "success": False, "error": stored["error"]}
            else:
                resp = {"id": request_id, "success": True, "result": stored}
        else:
            # 未登録コマンドはエラーを返す
            resp = {
                "id": request_id,
                "success": False,
                "error": {
                    "code": "UNKNOWN_COMMAND",
                    "message": f"Unknown command: {command}",
                },
            }

        await self._ws.send(json.dumps(resp))

    async def disconnect(self) -> None:
        """接続を切断する"""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        if self._ws:
            await self._ws.close()
        self._connected = False

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()
