"""PhotoshopClient - 高レベル API（ResilientWSBridge のラッパー）"""

import logging
from typing import Any, Dict, List, Optional

from .exceptions import ERROR_CODE_MAP, PhotoshopSDKError
from .schema import DocumentInfo
from .ws_bridge import ResilientWSBridge

logger = logging.getLogger(__name__)

# コマンドごとのタイムアウト設定
COMMAND_TIMEOUTS: Dict[str, float] = {
    "default": 30.0,
    "file.open": 120.0,
    "file.export": 120.0,
    "batch.run": 300.0,
}


class PhotoshopClient:
    """Photoshop との通信を抽象化する高レベルクライアント"""

    def __init__(
        self,
        host: str = "localhost",
        port_file: Optional[str] = None,
    ):
        self._bridge = ResilientWSBridge(host=host, port_file=port_file)

    async def start(self) -> None:
        """WS サーバーを起動（UXP Plugin からの接続を待ち受け開始）"""
        await self._bridge.start()

    async def stop(self) -> None:
        """WS サーバーを停止"""
        await self._bridge.stop()

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()

    def _get_timeout(self, command: str, override: Optional[float] = None) -> float:
        if override is not None:
            return override
        return COMMAND_TIMEOUTS.get(command, COMMAND_TIMEOUTS["default"])

    async def execute_command(
        self,
        command: str,
        params: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """コマンドを実行し、結果 dict を返す（エラー時は例外を送出）"""
        cmd_timeout = self._get_timeout(command, timeout)
        return await self._bridge.send_command(command, params, timeout=cmd_timeout)

    # ─── File 操作 API ────────────────────────────────────────────

    async def file_open(self, path: str) -> Dict[str, Any]:
        """PSD ファイルを開く"""
        return await self.execute_command("file.open", {"path": path})

    async def file_close(self, doc_id: int, save: bool = False) -> Dict[str, Any]:
        """ドキュメントを閉じる"""
        return await self.execute_command("file.close", {"documentId": doc_id, "save": save})

    async def file_save(self, doc_id: int) -> Dict[str, Any]:
        """ドキュメントを保存する"""
        return await self.execute_command("file.save", {"documentId": doc_id})

    async def file_info(self, doc_id: int) -> DocumentInfo:
        """ドキュメント情報を取得する"""
        result = await self.execute_command("file.info", {"documentId": doc_id})
        return DocumentInfo(**result)

    async def file_list(self) -> List[DocumentInfo]:
        """開いているすべてのドキュメントを一覧表示する"""
        result = await self.execute_command("file.list")
        documents = result.get("documents", [])
        return [DocumentInfo(**doc) for doc in documents]

    async def ping(self) -> Dict[str, Any]:
        """接続確認"""
        return await self.execute_command("system.ping")
