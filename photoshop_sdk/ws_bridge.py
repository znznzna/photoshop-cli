"""
ResilientWSBridge: WebSocket サーバーとして動作し、UXP Plugin からの接続を待ち受ける。

通常の lightroom-cli とは逆転した接続構造:
  - Python SDK: WebSocket サーバー（listen）
  - UXP Plugin: WebSocket クライアント（connect）
"""

import asyncio
import enum
import json
import logging
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

import websockets
from websockets.asyncio.server import ServerConnection

logger = logging.getLogger(__name__)


class ConnectionState(enum.Enum):
    WAITING_FOR_PLUGIN = "waiting_for_plugin"
    CONNECTED = "connected"
    SHUTDOWN = "shutdown"


class ResilientWSBridge:
    """WebSocket サーバーとして UXP Plugin の接続を待ち受けるブリッジ"""

    def __init__(
        self,
        host: str = "localhost",
        port_file: Optional[str] = None,
        heartbeat_interval: float = 30.0,
    ):
        self._host = host
        if port_file is None:
            from .paths import get_port_file
            self._port_file = str(get_port_file())
        else:
            self._port_file = port_file

        self._heartbeat_interval = heartbeat_interval
        self._server: Optional[Any] = None
        self._connection: Optional[ServerConnection] = None
        self._state = ConnectionState.WAITING_FOR_PLUGIN
        self._pending_requests: Dict[str, asyncio.Future] = {}
        self._serve_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None

    @property
    def state(self) -> ConnectionState:
        return self._state

    async def start(self) -> None:
        """WebSocket サーバーを起動し、ポートをファイルに書き込む"""
        self._server = await websockets.serve(
            self._handle_connection,
            self._host,
            0,  # ランダムポートを使用
        )
        port = self._server.sockets[0].getsockname()[1]
        Path(self._port_file).write_text(str(port))
        logger.info(f"WS server listening on ws://{self._host}:{port}")
        logger.info(f"Port written to {self._port_file}")

    async def _handle_connection(self, websocket: ServerConnection) -> None:
        """UXP Plugin からの接続ハンドラ"""
        # stale接続のクリーンアップ: 既存接続があれば閉じる
        if self._connection is not None:
            logger.warning("Replacing stale connection with new one")
            try:
                await self._connection.close()
            except Exception:
                pass
            self._reject_pending_requests("Connection replaced by new client")

        self._connection = websocket
        self._state = ConnectionState.CONNECTED
        logger.info("UXP Plugin connected")

        if self._heartbeat_interval > 0:
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        try:
            async for raw_message in websocket:
                try:
                    message = json.loads(raw_message)
                    await self._handle_message(message)
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON from UXP Plugin: {e}")
        except websockets.exceptions.ConnectionClosedError:
            logger.info("UXP Plugin disconnected (connection closed)")
        except Exception as e:
            logger.error(f"Connection handler error: {e}")
        finally:
            if self._heartbeat_task:
                self._heartbeat_task.cancel()
                try:
                    await self._heartbeat_task
                except asyncio.CancelledError:
                    pass
            self._connection = None
            self._state = ConnectionState.WAITING_FOR_PLUGIN
            self._reject_pending_requests("UXP Plugin disconnected")
            logger.info("UXP Plugin connection closed, waiting for reconnection")

    def _reject_pending_requests(self, reason: str) -> None:
        """未解決の全リクエストを ConnectionError で reject する"""
        from .exceptions import ConnectionError as PSConnectionError

        pending = list(self._pending_requests.items())
        self._pending_requests.clear()
        for request_id, future in pending:
            if not future.done():
                future.set_exception(PSConnectionError(reason))
            logger.debug(f"Rejected pending request {request_id}: {reason}")

    async def _handle_message(self, message: Dict[str, Any]) -> None:
        """UXP Plugin からのレスポンスを pending_request に解決する"""
        request_id = message.get("id")
        if request_id and request_id in self._pending_requests:
            future = self._pending_requests.pop(request_id)
            if not future.done():
                future.set_result(message)
        else:
            logger.warning(f"Received message with unknown id: {request_id}")

    async def send_command(
        self,
        command: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: float = 30.0,
    ) -> Dict[str, Any]:
        """UXP Plugin にコマンドを送信し、応答を待つ"""
        if self._state != ConnectionState.CONNECTED or self._connection is None:
            from .exceptions import ConnectionError as PSConnectionError
            raise PSConnectionError(
                "UXP Plugin is not connected. Please ensure Photoshop is running with the plugin active."
            )

        request_id = str(uuid.uuid4())
        request = {
            "id": request_id,
            "command": command,
            "params": params or {},
        }

        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending_requests[request_id] = future

        try:
            await self._connection.send(json.dumps(request))
            response = await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending_requests.pop(request_id, None)
            from .exceptions import TimeoutError as PSTimeoutError
            raise PSTimeoutError(f"Command '{command}' timed out after {timeout}s")
        except Exception:
            self._pending_requests.pop(request_id, None)
            raise

        if not response.get("success"):
            error = response.get("error", {})
            error_code = error.get("code", "UNKNOWN")
            error_message = error.get("message", "Unknown error")
            from .exceptions import ERROR_CODE_MAP, PhotoshopSDKError
            exception_class = ERROR_CODE_MAP.get(error_code, PhotoshopSDKError)
            raise exception_class(error_message, code=error_code, details=error)

        return response.get("result", {})

    async def _heartbeat_loop(self) -> None:
        """定期的に system.ping を送信して接続を確認"""
        while self._state == ConnectionState.CONNECTED:
            try:
                await asyncio.sleep(self._heartbeat_interval)
                await self.send_command("system.ping", timeout=5.0)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Heartbeat failed: {e}")

    async def stop(self) -> None:
        """サーバーを停止し、ポートファイルを削除する"""
        self._state = ConnectionState.SHUTDOWN

        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        if self._connection:
            await self._connection.close()

        if self._server:
            self._server.close()
            await self._server.wait_closed()

        port_file = Path(self._port_file)
        if port_file.exists():
            port_file.unlink()

        logger.info("WS server stopped")
