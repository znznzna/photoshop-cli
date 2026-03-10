"""MCP セッション中の永続的な Photoshop 接続管理"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

from photoshop_sdk.client import PhotoshopClient
from photoshop_sdk.exceptions import (
    ConnectionError as PSConnectionError,
    DocumentNotFoundError,
    PhotoshopSDKError,
    TimeoutError as PSTimeoutError,
    ValidationError as PSValidationError,
)

logger = logging.getLogger(__name__)


class ConnectionState:
    """接続状態の列挙"""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


class ConnectionManager:
    """PhotoshopClient のライフサイクルとリクエスト直列化を管理する

    接続状態マシン:
        DISCONNECTED → CONNECTING → CONNECTED
                                  ↘ ERROR → DISCONNECTED (再試行時)
        CONNECTED → DISCONNECTED (切断時 / ConnectionError 時)
    """

    def __init__(self, host: str = "localhost", port_file: Optional[str] = None):
        self._host = host
        self._port_file = port_file
        self._client: Optional[PhotoshopClient] = None
        self._lock = asyncio.Lock()
        self._state = ConnectionState.DISCONNECTED
        self._connect_lock = asyncio.Lock()

    async def _ensure_connected(self) -> PhotoshopClient:
        """lazy connect: 未接続なら接続する（レースコンディション防止付き）"""
        if self._state == ConnectionState.CONNECTED and self._client:
            return self._client

        async with self._connect_lock:
            if self._state == ConnectionState.CONNECTED and self._client:
                return self._client

            self._state = ConnectionState.CONNECTING
            try:
                self._client = PhotoshopClient(host=self._host, port_file=self._port_file)
                await self._client.start()
                self._state = ConnectionState.CONNECTED
                logger.info("PhotoshopClient connected (lazy)")
            except Exception:
                self._state = ConnectionState.ERROR
                self._client = None
                raise
        return self._client

    async def execute(
        self,
        command: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: float = 30.0,
    ) -> dict:
        """コマンドを実行し、結果を dict で返す。例外は dict に変換する。"""
        async with self._lock:
            try:
                client = await self._ensure_connected()
                result = await client.execute_command(command, params, timeout=timeout)
                return {"success": True, **result}
            except PSValidationError as e:
                return {
                    "success": False,
                    "error": {
                        "code": e.code or "VALIDATION_ERROR",
                        "message": str(e),
                        "category": "validation",
                        "retryable": False,
                        "details": e.details,
                    },
                }
            except PSConnectionError as e:
                self._state = ConnectionState.DISCONNECTED
                return {
                    "success": False,
                    "error": {
                        "code": "CONNECTION_ERROR",
                        "message": str(e),
                        "category": "connection",
                        "retryable": True,
                    },
                }
            except PSTimeoutError as e:
                return {
                    "success": False,
                    "error": {
                        "code": "TIMEOUT_ERROR",
                        "message": str(e),
                        "category": "timeout",
                        "retryable": True,
                    },
                }
            except DocumentNotFoundError as e:
                return {
                    "success": False,
                    "error": {
                        "code": e.code or "DOCUMENT_NOT_FOUND",
                        "message": str(e),
                        "category": "not_found",
                        "retryable": False,
                        "details": e.details,
                    },
                }
            except PhotoshopSDKError as e:
                return {
                    "success": False,
                    "error": {
                        "code": e.code or "SDK_ERROR",
                        "message": str(e),
                        "category": "sdk",
                        "retryable": False,
                    },
                }

    async def disconnect(self) -> None:
        """接続を切断する"""
        if self._client:
            await self._client.stop()
            self._client = None
        self._state = ConnectionState.DISCONNECTED

    async def status(self) -> dict:
        """接続状態を返す"""
        return {
            "state": self._state,
            "host": self._host,
        }
