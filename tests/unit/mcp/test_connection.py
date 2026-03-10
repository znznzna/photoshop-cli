"""ConnectionManager ユニットテスト"""

from unittest.mock import AsyncMock, patch

import pytest

from mcp_server.connection import ConnectionManager, ConnectionState


class TestConnectionState:
    def test_states_exist(self):
        """全接続状態が定義されている"""
        assert ConnectionState.DISCONNECTED == "disconnected"
        assert ConnectionState.CONNECTING == "connecting"
        assert ConnectionState.CONNECTED == "connected"
        assert ConnectionState.ERROR == "error"


class TestConnectionManagerInit:
    def test_initial_state(self):
        """初期状態は DISCONNECTED"""
        mgr = ConnectionManager()
        assert mgr._state == ConnectionState.DISCONNECTED
        assert mgr._client is None

    def test_custom_host(self):
        """host パラメータが設定される"""
        mgr = ConnectionManager(host="192.168.1.1")
        assert mgr._host == "192.168.1.1"


class TestConnectionManagerStatus:
    async def test_status_disconnected(self):
        """切断状態のステータス"""
        mgr = ConnectionManager()
        status = await mgr.status()
        assert status["state"] == "disconnected"
        assert status["host"] == "localhost"


class TestConnectionManagerEnsureConnected:
    @patch("mcp_server.connection.PhotoshopClient")
    async def test_lazy_connect(self, mock_client_cls):
        """初回 execute で自動接続する"""
        mock_client = AsyncMock()
        mock_client.execute_command = AsyncMock(return_value={"status": "ok"})
        mock_client_cls.return_value = mock_client

        mgr = ConnectionManager()
        result = await mgr.execute("system.ping")

        mock_client.start.assert_awaited_once()
        assert mgr._state == ConnectionState.CONNECTED
        assert result["success"] is True

    @patch("mcp_server.connection.PhotoshopClient")
    async def test_reuses_existing_connection(self, mock_client_cls):
        """2回目以降は既存接続を再利用する"""
        mock_client = AsyncMock()
        mock_client.execute_command = AsyncMock(return_value={"status": "ok"})
        mock_client_cls.return_value = mock_client

        mgr = ConnectionManager()
        await mgr.execute("system.ping")
        await mgr.execute("system.ping")

        mock_client.start.assert_awaited_once()

    @patch("mcp_server.connection.PhotoshopClient")
    async def test_connect_failure_sets_error_state(self, mock_client_cls):
        """接続失敗時は ERROR 状態になる"""
        mock_client = AsyncMock()
        mock_client.start.side_effect = Exception("Connection refused")
        mock_client_cls.return_value = mock_client

        mgr = ConnectionManager()

        with pytest.raises(Exception, match="Connection refused"):
            await mgr._ensure_connected()

        assert mgr._state == ConnectionState.ERROR


class TestConnectionManagerExecute:
    @patch("mcp_server.connection.PhotoshopClient")
    async def test_success_response(self, mock_client_cls):
        """成功時は success=True の dict を返す"""
        mock_client = AsyncMock()
        mock_client.execute_command = AsyncMock(return_value={"documentId": 1, "name": "test.psd"})
        mock_client_cls.return_value = mock_client

        mgr = ConnectionManager()
        result = await mgr.execute("file.info", {"documentId": 1})

        assert result["success"] is True
        assert result["documentId"] == 1
        assert result["name"] == "test.psd"

    @patch("mcp_server.connection.PhotoshopClient")
    async def test_validation_error_response(self, mock_client_cls):
        """ValidationError は retryable=False の dict に変換される"""
        from photoshop_sdk.exceptions import ValidationError as PSValidationError

        mock_client = AsyncMock()
        mock_client.execute_command = AsyncMock(
            side_effect=PSValidationError("Invalid path", code="VALIDATION_ERROR", details={"field": "path"})
        )
        mock_client_cls.return_value = mock_client

        mgr = ConnectionManager()
        result = await mgr.execute("file.open", {"path": "/bad"})

        assert result["success"] is False
        assert result["error"]["category"] == "validation"
        assert result["error"]["retryable"] is False

    @patch("mcp_server.connection.PhotoshopClient")
    async def test_connection_error_response(self, mock_client_cls):
        """ConnectionError は retryable=True の dict に変換され、クライアントがクリーンアップされる"""
        from photoshop_sdk.exceptions import ConnectionError as PSConnectionError

        mock_client = AsyncMock()
        mock_client.execute_command = AsyncMock(side_effect=PSConnectionError("Lost connection"))
        mock_client_cls.return_value = mock_client

        mgr = ConnectionManager()
        result = await mgr.execute("system.ping")

        assert result["success"] is False
        assert result["error"]["category"] == "connection"
        assert result["error"]["retryable"] is True
        assert mgr._state == ConnectionState.DISCONNECTED
        assert mgr._client is None  # P1: クライアントがクリーンアップされている

    @patch("mcp_server.connection.PhotoshopClient")
    async def test_timeout_error_response(self, mock_client_cls):
        """TimeoutError は retryable=True の dict に変換される"""
        from photoshop_sdk.exceptions import TimeoutError as PSTimeoutError

        mock_client = AsyncMock()
        mock_client.execute_command = AsyncMock(side_effect=PSTimeoutError("Timed out"))
        mock_client_cls.return_value = mock_client

        mgr = ConnectionManager()
        result = await mgr.execute("file.open", {"path": "/test.psd"}, timeout=120)

        assert result["success"] is False
        assert result["error"]["category"] == "timeout"
        assert result["error"]["retryable"] is True

    @patch("mcp_server.connection.PhotoshopClient")
    async def test_document_not_found_response(self, mock_client_cls):
        """DocumentNotFoundError は retryable=False の dict に変換される"""
        from photoshop_sdk.exceptions import DocumentNotFoundError

        mock_client = AsyncMock()
        mock_client.execute_command = AsyncMock(side_effect=DocumentNotFoundError(doc_id=99))
        mock_client_cls.return_value = mock_client

        mgr = ConnectionManager()
        result = await mgr.execute("file.info", {"documentId": 99})

        assert result["success"] is False
        assert result["error"]["category"] == "not_found"
        assert result["error"]["retryable"] is False

    @patch("mcp_server.connection.PhotoshopClient")
    async def test_generic_sdk_error_response(self, mock_client_cls):
        """PhotoshopSDKError は retryable=False の dict に変換される"""
        from photoshop_sdk.exceptions import PhotoshopSDKError

        mock_client = AsyncMock()
        mock_client.execute_command = AsyncMock(side_effect=PhotoshopSDKError("Unknown SDK error"))
        mock_client_cls.return_value = mock_client

        mgr = ConnectionManager()
        result = await mgr.execute("file.list")

        assert result["success"] is False
        assert result["error"]["category"] == "sdk"

    @patch("mcp_server.connection.PhotoshopClient")
    async def test_timeout_parameter_passed(self, mock_client_cls):
        """timeout パラメータが execute_command に渡される"""
        mock_client = AsyncMock()
        mock_client.execute_command = AsyncMock(return_value={"ok": True})
        mock_client_cls.return_value = mock_client

        mgr = ConnectionManager()
        await mgr.execute("file.open", {"path": "/test.psd"}, timeout=120.0)

        mock_client.execute_command.assert_awaited_once_with("file.open", {"path": "/test.psd"}, timeout=120.0)


class TestConnectionManagerDisconnect:
    @patch("mcp_server.connection.PhotoshopClient")
    async def test_disconnect(self, mock_client_cls):
        """disconnect で接続を切断する"""
        mock_client = AsyncMock()
        mock_client.execute_command = AsyncMock(return_value={"ok": True})
        mock_client_cls.return_value = mock_client

        mgr = ConnectionManager()
        await mgr.execute("system.ping")
        assert mgr._state == ConnectionState.CONNECTED

        await mgr.disconnect()
        assert mgr._state == ConnectionState.DISCONNECTED
        assert mgr._client is None
        mock_client.stop.assert_awaited_once()

    async def test_disconnect_when_not_connected(self):
        """未接続時の disconnect は安全"""
        mgr = ConnectionManager()
        await mgr.disconnect()
        assert mgr._state == ConnectionState.DISCONNECTED


class TestConnectionManagerUnexpectedError:
    @patch("mcp_server.connection.PhotoshopClient")
    async def test_unexpected_error_returns_internal_error(self, mock_client_cls):
        """非SDK例外は INTERNAL_ERROR の dict に変換される"""
        mock_client = AsyncMock()
        mock_client.execute_command = AsyncMock(side_effect=RuntimeError("Unexpected IO failure"))
        mock_client_cls.return_value = mock_client

        mgr = ConnectionManager()
        result = await mgr.execute("file.list")

        assert result["success"] is False
        assert result["error"]["code"] == "INTERNAL_ERROR"
        assert result["error"]["category"] == "internal"
        assert result["error"]["retryable"] is False

    @patch("mcp_server.connection.PhotoshopClient")
    async def test_startup_error_returns_structured_response(self, mock_client_cls):
        """起動時の非SDK例外も構造化レスポンスになる"""
        mock_client = AsyncMock()
        mock_client.start.side_effect = OSError("Port already in use")
        mock_client_cls.return_value = mock_client

        mgr = ConnectionManager()
        result = await mgr.execute("system.ping")

        assert result["success"] is False
        assert result["error"]["code"] == "INTERNAL_ERROR"
        assert result["error"]["category"] == "internal"
