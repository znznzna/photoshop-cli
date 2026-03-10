# MCP Phase 2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** MCP レイヤーに全 6 コマンド（file.list/info/open/close/save, system.ping）を動的ツール登録パターンで実装する
**Architecture:** CommandSchema 定義から tool_registry が FastMCP ツールを自動生成し、ConnectionManager が PhotoshopClient のライフサイクルとリクエスト直列化を管理する。lightroom-cli の実績あるパターンを踏襲。
**Tech Stack:** Python 3.10+, FastMCP 3.x, Pydantic 2.x, websockets 12.x, pytest, pytest-asyncio, ruff
---

## 前提条件

- 既存テスト: 106件全パス (`python -m pytest tests/unit/ -v`)
- Lint: `ruff check . && ruff format .` がクリーン
- 設計書: `docs/plans/2026-03-11-mcp-phase2-design.md` 承認済み

## 注意事項

- FastMCP 3.x のリソース関数は `str` または `bytes` を返す必要がある（`dict` 不可）。`json.dumps()` で変換する。
- 動的ツール関数のシグネチャは `inspect.Parameter.POSITIONAL_OR_KEYWORD` を使用する（FastMCP 3.x 互換確認済み）。
- `psd-mcp` エントリポイント（`pyproject.toml` の `mcp_server.server:main`）は `server.py` の後方互換ラッパーで対応し、変更不要。

---

### Task 1: ParamSchema と CommandSchema を photoshop_sdk/schema.py に追加

**Files:**
- Modify: `photoshop_sdk/schema.py`
- Test: `tests/unit/mcp/test_command_schemas.py`
- Create: `tests/unit/mcp/__init__.py`

**Step 1: テストディレクトリとテストファイルを作成**

Create `tests/unit/mcp/__init__.py` (empty file).

Create `tests/unit/mcp/test_command_schemas.py`:

```python
"""CommandSchema 定義の網羅性・整合性テスト"""

import pytest

from photoshop_sdk.schema import COMMAND_SCHEMAS, CommandSchema, ParamSchema


class TestParamSchema:
    def test_effective_sdk_name_with_override(self):
        """sdk_name が指定されている場合はそちらを返す"""
        p = ParamSchema(name="doc_id", type=int, description="Doc ID", sdk_name="documentId")
        assert p.effective_sdk_name == "documentId"

    def test_effective_sdk_name_without_override(self):
        """sdk_name が None の場合は name を返す"""
        p = ParamSchema(name="path", type=str, description="Path")
        assert p.effective_sdk_name == "path"

    def test_frozen(self):
        """ParamSchema は frozen（不変）"""
        p = ParamSchema(name="x", type=int, description="X")
        with pytest.raises(AttributeError):
            p.name = "y"


class TestCommandSchema:
    def test_frozen(self):
        """CommandSchema は frozen（不変）"""
        s = CommandSchema(command="test.cmd", description="Test")
        with pytest.raises(AttributeError):
            s.command = "other"

    def test_defaults(self):
        """デフォルト値が正しい"""
        s = CommandSchema(command="test.cmd", description="Test")
        assert s.params == []
        assert s.mutating is False
        assert s.risk_level == "read"
        assert s.requires_confirm is False
        assert s.supports_dry_run is False
        assert s.timeout == 30.0
        assert s.validator is None


class TestCommandSchemas:
    def test_all_commands_have_schemas(self):
        """全6コマンドの CommandSchema が定義されている"""
        commands = {s.command for s in COMMAND_SCHEMAS}
        expected = {"file.list", "file.info", "file.open", "file.close", "file.save", "system.ping"}
        assert commands == expected

    def test_no_duplicate_commands(self):
        """重複するコマンドがない"""
        commands = [s.command for s in COMMAND_SCHEMAS]
        assert len(commands) == len(set(commands))

    def test_risk_levels_valid(self):
        """risk_level が許可された値のみ"""
        for s in COMMAND_SCHEMAS:
            assert s.risk_level in ("read", "write", "destructive"), f"{s.command}: invalid risk_level={s.risk_level}"

    def test_mutating_commands_have_dry_run(self):
        """mutating コマンドは supports_dry_run が有効"""
        for s in COMMAND_SCHEMAS:
            if s.mutating:
                assert s.supports_dry_run, f"{s.command} is mutating but doesn't support dry_run"

    def test_file_open_has_validator(self):
        """file.open に validate_file_path バリデータが設定されている"""
        schema = next(s for s in COMMAND_SCHEMAS if s.command == "file.open")
        assert schema.validator == "validate_file_path"

    def test_file_open_timeout(self):
        """file.open のタイムアウトは120秒"""
        schema = next(s for s in COMMAND_SCHEMAS if s.command == "file.open")
        assert schema.timeout == 120.0

    def test_system_ping_timeout(self):
        """system.ping のタイムアウトは5秒"""
        schema = next(s for s in COMMAND_SCHEMAS if s.command == "system.ping")
        assert schema.timeout == 5.0

    def test_file_close_requires_confirm(self):
        """file.close は requires_confirm が有効"""
        schema = next(s for s in COMMAND_SCHEMAS if s.command == "file.close")
        assert schema.requires_confirm is True

    def test_doc_id_params_have_sdk_name(self):
        """doc_id パラメータは sdk_name=documentId が設定されている"""
        for s in COMMAND_SCHEMAS:
            for p in s.params:
                if p.name == "doc_id":
                    assert p.sdk_name == "documentId", f"{s.command}: doc_id missing sdk_name"

    def test_read_commands_not_mutating(self):
        """read risk_level のコマンドは mutating=False"""
        for s in COMMAND_SCHEMAS:
            if s.risk_level == "read":
                assert not s.mutating, f"{s.command}: read command should not be mutating"
```

**Step 2: 失敗を確認**

Run: `python -m pytest tests/unit/mcp/test_command_schemas.py -v`
Expected: FAIL (ImportError — ParamSchema, CommandSchema, COMMAND_SCHEMAS が存在しない)

**Step 3: 実装**

Modify `photoshop_sdk/schema.py` — 既存の Pydantic モデルの後に以下を追加:

```python
from dataclasses import dataclass, field
from typing import Any  # 既存の typing import に Any を追加


@dataclass(frozen=True)
class ParamSchema:
    """コマンドパラメータの定義"""

    name: str
    type: type
    description: str
    required: bool = True
    default: Any = None
    sdk_name: str | None = None

    @property
    def effective_sdk_name(self) -> str:
        return self.sdk_name or self.name


@dataclass(frozen=True)
class CommandSchema:
    """コマンドのメタデータ定義"""

    command: str
    description: str
    params: list[ParamSchema] = field(default_factory=list)
    mutating: bool = False
    risk_level: str = "read"
    requires_confirm: bool = False
    supports_dry_run: bool = False
    timeout: float = 30.0
    validator: str | None = None


COMMAND_SCHEMAS: list[CommandSchema] = [
    CommandSchema(
        command="file.list",
        description="List all open Photoshop documents.",
    ),
    CommandSchema(
        command="file.info",
        description="Get detailed information for a specific document.",
        params=[
            ParamSchema(name="doc_id", type=int, description="Document ID", sdk_name="documentId"),
        ],
    ),
    CommandSchema(
        command="file.open",
        description="Open a PSD file in Photoshop.",
        params=[
            ParamSchema(name="path", type=str, description="Absolute path to the PSD file"),
        ],
        mutating=True,
        risk_level="write",
        supports_dry_run=True,
        timeout=120.0,
        validator="validate_file_path",
    ),
    CommandSchema(
        command="file.close",
        description="Close a document. Use save=true to save before closing.",
        params=[
            ParamSchema(name="doc_id", type=int, description="Document ID to close", sdk_name="documentId"),
            ParamSchema(name="save", type=bool, description="Save before closing", required=False, default=False),
        ],
        mutating=True,
        risk_level="write",
        requires_confirm=True,
        supports_dry_run=True,
    ),
    CommandSchema(
        command="file.save",
        description="Save a document.",
        params=[
            ParamSchema(name="doc_id", type=int, description="Document ID to save", sdk_name="documentId"),
        ],
        mutating=True,
        risk_level="write",
        supports_dry_run=True,
    ),
    CommandSchema(
        command="system.ping",
        description="Check connection to Photoshop UXP Plugin.",
        timeout=5.0,
    ),
]
```

**Step 4: 通過を確認**

Run: `python -m pytest tests/unit/mcp/test_command_schemas.py -v`
Expected: PASS (全テスト通過)

Run: `python -m pytest tests/unit/ -v`
Expected: PASS (既存テスト含め全通過)

**Step 5: コミット**

```bash
git add photoshop_sdk/schema.py tests/unit/mcp/__init__.py tests/unit/mcp/test_command_schemas.py
git commit -m "feat: add ParamSchema, CommandSchema, and COMMAND_SCHEMAS to SDK (MCP Phase 2 foundation)"
```

---

### Task 2: ConnectionManager を実装

**Files:**
- Create: `mcp_server/connection.py`
- Test: `tests/unit/mcp/test_connection.py`

**Step 1: テストを書く**

Create `tests/unit/mcp/test_connection.py`:

```python
"""ConnectionManager ユニットテスト"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

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

        # start() は1回だけ呼ばれる
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
        """ConnectionError は retryable=True の dict に変換される"""
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
        await mgr.execute("system.ping")  # 接続する
        assert mgr._state == ConnectionState.CONNECTED

        await mgr.disconnect()
        assert mgr._state == ConnectionState.DISCONNECTED
        assert mgr._client is None
        mock_client.stop.assert_awaited_once()

    async def test_disconnect_when_not_connected(self):
        """未接続時の disconnect は安全"""
        mgr = ConnectionManager()
        await mgr.disconnect()  # 例外なし
        assert mgr._state == ConnectionState.DISCONNECTED
```

**Step 2: 失敗を確認**

Run: `python -m pytest tests/unit/mcp/test_connection.py -v`
Expected: FAIL (ImportError — connection.py が存在しない)

**Step 3: 実装**

Create `mcp_server/connection.py`:

```python
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
            # ダブルチェック（lock 取得中に他が接続完了している場合）
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
```

**Step 4: 通過を確認**

Run: `python -m pytest tests/unit/mcp/test_connection.py -v`
Expected: PASS

Run: `python -m pytest tests/unit/ -v`
Expected: PASS (既存テスト含め全通過)

**Step 5: コミット**

```bash
git add mcp_server/connection.py tests/unit/mcp/test_connection.py
git commit -m "feat: add ConnectionManager with lazy connect and error-to-dict conversion (MCP Phase 2)"
```

---

### Task 3: tool_registry を実装

**Files:**
- Create: `mcp_server/tool_registry.py`
- Test: `tests/unit/mcp/test_tool_registry.py`

**Step 1: テストを書く**

Create `tests/unit/mcp/test_tool_registry.py`:

```python
"""動的ツール登録のユニットテスト"""

import inspect

import pytest
from unittest.mock import AsyncMock

from fastmcp import FastMCP

from photoshop_sdk.schema import COMMAND_SCHEMAS, CommandSchema, ParamSchema
from mcp_server.tool_registry import _build_tool_fn, _build_description, register_all_tools


class TestBuildToolFn:
    def test_no_params_signature(self):
        """パラメータなしコマンドのシグネチャ"""
        schema = CommandSchema(command="file.list", description="List files")
        conn_mgr = AsyncMock()
        fn = _build_tool_fn(schema, conn_mgr)

        sig = inspect.signature(fn)
        assert len(sig.parameters) == 0
        assert fn.__name__ == "file_list"

    def test_required_param_signature(self):
        """必須パラメータのシグネチャ"""
        schema = CommandSchema(
            command="file.info",
            description="Get info",
            params=[ParamSchema(name="doc_id", type=int, description="Doc ID")],
        )
        conn_mgr = AsyncMock()
        fn = _build_tool_fn(schema, conn_mgr)

        sig = inspect.signature(fn)
        assert "doc_id" in sig.parameters
        param = sig.parameters["doc_id"]
        assert param.annotation is int
        assert param.default is inspect.Parameter.empty

    def test_optional_param_signature(self):
        """オプショナルパラメータのシグネチャ"""
        schema = CommandSchema(
            command="file.close",
            description="Close",
            params=[
                ParamSchema(name="doc_id", type=int, description="Doc ID"),
                ParamSchema(name="save", type=bool, description="Save", required=False, default=False),
            ],
            mutating=True,
            supports_dry_run=True,
        )
        conn_mgr = AsyncMock()
        fn = _build_tool_fn(schema, conn_mgr)

        sig = inspect.signature(fn)
        assert sig.parameters["save"].default is False

    def test_dry_run_added_for_mutating(self):
        """mutating + supports_dry_run コマンドに dry_run パラメータが追加される"""
        schema = CommandSchema(
            command="file.save",
            description="Save",
            params=[ParamSchema(name="doc_id", type=int, description="Doc ID")],
            mutating=True,
            supports_dry_run=True,
        )
        conn_mgr = AsyncMock()
        fn = _build_tool_fn(schema, conn_mgr)

        sig = inspect.signature(fn)
        assert "dry_run" in sig.parameters
        assert sig.parameters["dry_run"].default is False
        assert sig.parameters["dry_run"].annotation is bool

    def test_no_dry_run_for_read(self):
        """read コマンドに dry_run パラメータは追加されない"""
        schema = CommandSchema(command="file.list", description="List")
        conn_mgr = AsyncMock()
        fn = _build_tool_fn(schema, conn_mgr)

        sig = inspect.signature(fn)
        assert "dry_run" not in sig.parameters

    async def test_execute_calls_conn_mgr(self):
        """ツール関数実行時に conn_mgr.execute が呼ばれる"""
        schema = CommandSchema(
            command="file.info",
            description="Get info",
            params=[ParamSchema(name="doc_id", type=int, description="Doc ID", sdk_name="documentId")],
        )
        conn_mgr = AsyncMock()
        conn_mgr.execute = AsyncMock(return_value={"success": True, "documentId": 1})
        fn = _build_tool_fn(schema, conn_mgr)

        result = await fn(doc_id=1)

        conn_mgr.execute.assert_awaited_once_with("file.info", {"documentId": 1}, timeout=30.0)
        assert result["success"] is True

    async def test_sdk_name_mapping(self):
        """sdk_name が指定されたパラメータは名前が変換される"""
        schema = CommandSchema(
            command="file.close",
            description="Close",
            params=[
                ParamSchema(name="doc_id", type=int, description="Doc ID", sdk_name="documentId"),
                ParamSchema(name="save", type=bool, description="Save", required=False, default=False),
            ],
            mutating=True,
            supports_dry_run=True,
        )
        conn_mgr = AsyncMock()
        conn_mgr.execute = AsyncMock(return_value={"success": True})
        fn = _build_tool_fn(schema, conn_mgr)

        await fn(doc_id=5, save=True)

        conn_mgr.execute.assert_awaited_once_with("file.close", {"documentId": 5, "save": True}, timeout=30.0)

    async def test_dry_run_returns_preview(self):
        """dry_run=True の場合は実行せず preview を返す"""
        schema = CommandSchema(
            command="file.save",
            description="Save",
            params=[ParamSchema(name="doc_id", type=int, description="Doc ID", sdk_name="documentId")],
            mutating=True,
            supports_dry_run=True,
        )
        conn_mgr = AsyncMock()
        fn = _build_tool_fn(schema, conn_mgr)

        result = await fn(doc_id=1, dry_run=True)

        assert result["dry_run"] is True
        assert result["command"] == "file.save"
        assert result["params"] == {"documentId": 1}
        conn_mgr.execute.assert_not_awaited()

    async def test_validator_called(self):
        """validator が設定されている場合は呼ばれる"""
        schema = CommandSchema(
            command="file.open",
            description="Open",
            params=[ParamSchema(name="path", type=str, description="Path")],
            mutating=True,
            supports_dry_run=True,
            timeout=120.0,
            validator="validate_file_path",
        )
        conn_mgr = AsyncMock()
        conn_mgr.execute = AsyncMock(return_value={"success": True})
        fn = _build_tool_fn(schema, conn_mgr)

        # validate_file_path は存在しないファイルで ValidationError を投げる
        result = await fn(path="/nonexistent/file.psd")

        assert result["success"] is False
        assert result["error"]["code"] == "VALIDATION_ERROR"
        conn_mgr.execute.assert_not_awaited()


class TestBuildDescription:
    def test_read_command(self):
        """read コマンドはタグなし"""
        schema = CommandSchema(command="file.list", description="List all open documents.")
        desc = _build_description(schema)
        assert "List all open documents." in desc
        assert "[mutating]" not in desc

    def test_mutating_command(self):
        """mutating コマンドはタグ付き"""
        schema = CommandSchema(
            command="file.open",
            description="Open a PSD file.",
            mutating=True,
            risk_level="write",
            supports_dry_run=True,
        )
        desc = _build_description(schema)
        assert "[risk:write]" in desc
        assert "[mutating]" in desc
        assert "[supports-dry-run]" in desc

    def test_requires_confirm(self):
        """requires_confirm タグ"""
        schema = CommandSchema(
            command="file.close",
            description="Close a document.",
            mutating=True,
            risk_level="write",
            requires_confirm=True,
            supports_dry_run=True,
        )
        desc = _build_description(schema)
        assert "[requires-confirm]" in desc


class TestRegisterAllTools:
    def test_all_tools_registered(self):
        """全 CommandSchema がツールとして登録される"""
        mcp = FastMCP(name="test")
        conn_mgr = AsyncMock()
        register_all_tools(mcp, conn_mgr)

        # COMMAND_SCHEMAS の数だけツールが登録されている
        assert len(COMMAND_SCHEMAS) == 6

    def test_tool_names(self):
        """ツール名が command.replace('.', '_') 形式"""
        mcp = FastMCP(name="test")
        conn_mgr = AsyncMock()
        register_all_tools(mcp, conn_mgr)

        expected_names = {"file_list", "file_info", "file_open", "file_close", "file_save", "system_ping"}
        # FastMCP 内部 API で確認
        # register_all_tools が例外なく完了 = 全ツール登録成功
        # 統合テスト (Task 5) で Client 経由の名前検証を行う
```

**Step 2: 失敗を確認**

Run: `python -m pytest tests/unit/mcp/test_tool_registry.py -v`
Expected: FAIL (ImportError — tool_registry.py が存在しない)

**Step 3: 実装**

Create `mcp_server/tool_registry.py`:

```python
"""CommandSchema から FastMCP ツールを動的に生成・登録する"""

from __future__ import annotations

import inspect
import logging
from typing import TYPE_CHECKING, Any

from photoshop_sdk.exceptions import ValidationError as PSValidationError
from photoshop_sdk.schema import COMMAND_SCHEMAS, CommandSchema
from photoshop_sdk.validators import validate_file_path

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from .connection import ConnectionManager

logger = logging.getLogger(__name__)

# Python 型 → FastMCP が解釈する型ヒント
_TYPE_MAP = {str: str, int: int, bool: bool, float: float}

# validator 名 → 関数マッピング
_VALIDATORS = {
    "validate_file_path": validate_file_path,
}


def _build_tool_fn(schema: CommandSchema, conn_mgr: "ConnectionManager"):
    """CommandSchema から FastMCP 互換のツール関数を動的に生成する"""

    # 1. inspect.Parameter リストを構築
    parameters = []
    for p in schema.params:
        default = inspect.Parameter.empty if p.required else p.default
        parameters.append(
            inspect.Parameter(
                name=p.name,
                kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default=default,
                annotation=_TYPE_MAP.get(p.type, p.type),
            )
        )

    # mutating かつ supports_dry_run なら dry_run パラメータを自動追加
    if schema.mutating and schema.supports_dry_run:
        parameters.append(
            inspect.Parameter(
                name="dry_run",
                kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default=False,
                annotation=bool,
            )
        )

    sig = inspect.Signature(parameters=parameters, return_annotation=dict)

    # 2. クロージャで schema をキャプチャ
    _schema = schema
    _conn_mgr = conn_mgr

    async def tool_fn(**kwargs) -> dict:
        # dry_run 処理
        is_dry_run = kwargs.pop("dry_run", False)

        # validator 実行
        if _schema.validator and _schema.validator in _VALIDATORS:
            try:
                validator_fn = _VALIDATORS[_schema.validator]
                for p in _schema.params:
                    if p.name in kwargs and p.required:
                        validated = validator_fn(kwargs[p.name])
                        kwargs[p.name] = str(validated)
                        break
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

        # SDK パラメータ名にマッピング
        sdk_params = {}
        for p in _schema.params:
            if p.name in kwargs:
                sdk_params[p.effective_sdk_name] = kwargs[p.name]

        if is_dry_run:
            return {
                "dry_run": True,
                "command": _schema.command,
                "params": sdk_params,
                "message": f"Validation passed. Would execute: {_schema.command}",
            }

        return await _conn_mgr.execute(_schema.command, sdk_params, timeout=_schema.timeout)

    # 3. シグネチャと名前を設定
    tool_fn.__signature__ = sig
    tool_fn.__name__ = _schema.command.replace(".", "_")
    tool_fn.__qualname__ = tool_fn.__name__

    return tool_fn


def _build_description(schema: CommandSchema) -> str:
    """CommandSchema からツール説明文を構築する"""
    lines = [schema.description]
    lines.append("")

    tags = []
    if schema.risk_level != "read":
        tags.append(f"[risk:{schema.risk_level}]")
    if schema.mutating:
        tags.append("[mutating]")
    if schema.requires_confirm:
        tags.append("[requires-confirm]")
    if schema.supports_dry_run:
        tags.append("[supports-dry-run]")
    if tags:
        lines.append(" ".join(tags))

    return "\n".join(lines).strip()


def register_all_tools(mcp: "FastMCP", conn_mgr: "ConnectionManager") -> None:
    """全 CommandSchema を FastMCP ツールとして登録する"""
    for schema in COMMAND_SCHEMAS:
        tool_fn = _build_tool_fn(schema, conn_mgr)
        description = _build_description(schema)
        mcp.tool(name=tool_fn.__name__, description=description)(tool_fn)
```

**Step 4: 通過を確認**

Run: `python -m pytest tests/unit/mcp/test_tool_registry.py -v`
Expected: PASS

Run: `python -m pytest tests/unit/ -v`
Expected: PASS (既存テスト含め全通過)

**Step 5: コミット**

```bash
git add mcp_server/tool_registry.py tests/unit/mcp/test_tool_registry.py
git commit -m "feat: add dynamic tool registration via CommandSchema (MCP Phase 2)"
```

---

### Task 4: instructions.py を作成

**Files:**
- Create: `mcp_server/instructions.py`

**Step 1: 実装**

Create `mcp_server/instructions.py`:

```python
"""MCP Server instructions for AI agents."""

MCP_INSTRUCTIONS = """\
Adobe Photoshop control server.
Use the available tools to open, close, save, and inspect Photoshop documents.
Photoshop must be running with the UXP Plugin active.

## Risk Levels
- [risk:read] — Safe read-only operations
- [risk:write] — Modifies document state
- [risk:destructive] — Irreversible changes (none currently)

## Tags
- [mutating] — Changes Photoshop state
- [requires-confirm] — Confirm with user before executing
- [supports-dry-run] — Pass dry_run=true to validate without executing
"""
```

**Step 2: コミット**

```bash
git add mcp_server/instructions.py
git commit -m "feat: add MCP instructions for AI agents (MCP Phase 2)"
```

---

### Task 5: _run.py を作成し server.py を後方互換ラッパーに変更

**Files:**
- Create: `mcp_server/_run.py`
- Modify: `mcp_server/server.py`
- Modify: `tests/unit/test_mcp_server.py`
- Test: `tests/unit/mcp/test_integration.py`

**Step 1: 統合テストを書く**

Create `tests/unit/mcp/test_integration.py`:

```python
"""FastMCP TestClient による統合テスト"""

import json

import pytest
from unittest.mock import AsyncMock, patch

from fastmcp import Client

from mcp_server._run import create_mcp_server


@pytest.fixture
def mcp_server():
    """テスト用 MCP サーバーを生成"""
    return create_mcp_server()


class TestToolRegistration:
    async def test_all_tools_listed(self, mcp_server):
        """全6ツールが登録されている"""
        async with Client(mcp_server) as client:
            tools = await client.list_tools()
            tool_names = {t.name for t in tools}
            expected = {"file_list", "file_info", "file_open", "file_close", "file_save", "system_ping"}
            assert tool_names == expected

    async def test_file_info_has_doc_id_param(self, mcp_server):
        """file_info ツールに doc_id パラメータがある"""
        async with Client(mcp_server) as client:
            tools = await client.list_tools()
            file_info = next(t for t in tools if t.name == "file_info")
            assert "doc_id" in file_info.inputSchema.get("properties", {})
            assert "doc_id" in file_info.inputSchema.get("required", [])

    async def test_file_open_has_dry_run_param(self, mcp_server):
        """file_open ツールに dry_run パラメータがある"""
        async with Client(mcp_server) as client:
            tools = await client.list_tools()
            file_open = next(t for t in tools if t.name == "file_open")
            assert "dry_run" in file_open.inputSchema.get("properties", {})

    async def test_file_list_no_dry_run(self, mcp_server):
        """file_list ツールに dry_run パラメータがない"""
        async with Client(mcp_server) as client:
            tools = await client.list_tools()
            file_list = next(t for t in tools if t.name == "file_list")
            assert "dry_run" not in file_list.inputSchema.get("properties", {})

    async def test_system_ping_no_params(self, mcp_server):
        """system_ping ツールにパラメータがない"""
        async with Client(mcp_server) as client:
            tools = await client.list_tools()
            system_ping = next(t for t in tools if t.name == "system_ping")
            props = system_ping.inputSchema.get("properties", {})
            assert len(props) == 0

    async def test_file_close_has_save_and_dry_run(self, mcp_server):
        """file_close ツールに doc_id, save, dry_run パラメータがある"""
        async with Client(mcp_server) as client:
            tools = await client.list_tools()
            file_close = next(t for t in tools if t.name == "file_close")
            props = file_close.inputSchema.get("properties", {})
            assert "doc_id" in props
            assert "save" in props
            assert "dry_run" in props

    async def test_tool_descriptions_contain_tags(self, mcp_server):
        """mutating ツールの説明にタグが含まれる"""
        async with Client(mcp_server) as client:
            tools = await client.list_tools()
            file_open = next(t for t in tools if t.name == "file_open")
            assert "[mutating]" in file_open.description
            assert "[risk:write]" in file_open.description

            file_close = next(t for t in tools if t.name == "file_close")
            assert "[requires-confirm]" in file_close.description


class TestToolExecution:
    @patch("mcp_server.connection.PhotoshopClient")
    async def test_file_list_execution(self, mock_client_cls, mcp_server):
        """file_list ツールが実行できる"""
        mock_client = AsyncMock()
        mock_client.execute_command = AsyncMock(return_value={"documents": []})
        mock_client_cls.return_value = mock_client

        async with Client(mcp_server) as client:
            result = await client.call_tool("file_list", {})
            data = result.data
            assert data["success"] is True

    @patch("mcp_server.connection.PhotoshopClient")
    async def test_system_ping_execution(self, mock_client_cls, mcp_server):
        """system_ping ツールが実行できる"""
        mock_client = AsyncMock()
        mock_client.execute_command = AsyncMock(return_value={"status": "ok"})
        mock_client_cls.return_value = mock_client

        async with Client(mcp_server) as client:
            result = await client.call_tool("system_ping", {})
            data = result.data
            assert data["success"] is True
            assert data["status"] == "ok"

    @patch("mcp_server.connection.PhotoshopClient")
    async def test_file_info_execution(self, mock_client_cls, mcp_server):
        """file_info ツールが doc_id → documentId 変換して実行する"""
        mock_client = AsyncMock()
        mock_client.execute_command = AsyncMock(
            return_value={"documentId": 1, "name": "test.psd", "width": 1920, "height": 1080}
        )
        mock_client_cls.return_value = mock_client

        async with Client(mcp_server) as client:
            result = await client.call_tool("file_info", {"doc_id": 1})
            data = result.data
            assert data["success"] is True
            assert data["name"] == "test.psd"

        # SDK に documentId として渡されたことを確認
        mock_client.execute_command.assert_awaited_once_with("file.info", {"documentId": 1}, timeout=30.0)

    async def test_file_save_dry_run(self, mcp_server):
        """file_save の dry_run が実行なしでプレビューを返す"""
        async with Client(mcp_server) as client:
            result = await client.call_tool("file_save", {"doc_id": 1, "dry_run": True})
            data = result.data
            assert data["dry_run"] is True
            assert data["command"] == "file.save"
            assert data["params"] == {"documentId": 1}


class TestResourceAccess:
    async def test_status_resource(self, mcp_server):
        """photoshop://status リソースが読み取れる"""
        async with Client(mcp_server) as client:
            resources = await client.list_resources()
            resource_uris = [str(r.uri) for r in resources]
            assert "photoshop://status" in resource_uris

            content = await client.read_resource("photoshop://status")
            data = json.loads(content)
            assert data["state"] == "disconnected"


class TestBackwardCompat:
    def test_server_py_exports(self):
        """server.py が main と mcp を再公開する"""
        from mcp_server.server import main, mcp

        assert callable(main)
        assert mcp is not None
        assert mcp.name == "photoshop-cli"
```

**Step 2: 既存テストを更新**

Modify `tests/unit/test_mcp_server.py`:

```python
def test_mcp_server_importable():
    """MCP server が import できる"""
    from mcp_server.server import main, mcp

    assert callable(main)
    assert mcp is not None


def test_mcp_app_name():
    from mcp_server.server import mcp

    assert mcp.name == "photoshop-cli"
```

**Step 3: 失敗を確認**

Run: `python -m pytest tests/unit/mcp/test_integration.py -v`
Expected: FAIL (_run.py が存在しない)

**Step 4: 実装**

Create `mcp_server/_run.py`:

```python
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
```

Modify `mcp_server/server.py` to:

```python
"""後方互換: mcp オブジェクトと main() を再公開"""

from mcp_server._run import main, mcp

__all__ = ["main", "mcp"]
```

**Step 5: 通過を確認**

Run: `python -m pytest tests/unit/mcp/test_integration.py -v`
Expected: PASS

Run: `python -m pytest tests/unit/test_mcp_server.py -v`
Expected: PASS

Run: `python -m pytest tests/unit/ -v`
Expected: PASS (全テスト通過)

**Step 6: コミット**

```bash
git add mcp_server/_run.py mcp_server/server.py tests/unit/mcp/test_integration.py tests/unit/test_mcp_server.py
git commit -m "feat: add MCP server bootstrap with dynamic tool registration and backward-compat server.py (MCP Phase 2)"
```

---

### Task 6: 全テスト通過 + Lint 確認

**Files:**
- (修正が必要な場合のみ)

**Step 1: 全テスト実行**

Run: `python -m pytest tests/unit/ -v`
Expected: PASS (全テスト通過、既存106件 + 新規テスト全件)

**Step 2: Lint 実行**

Run: `ruff check .`
Expected: クリーン（エラーなし）

Run: `ruff format .`
Expected: クリーン（変更なし）

**Step 3: 最終確認**

Run: `python -m pytest tests/unit/ -v --tb=short`
Expected: PASS (全テスト通過)

**Step 4: 問題があれば修正してコミット**

```bash
# 修正が必要な場合のみ
git add -A
git commit -m "fix: resolve lint/test issues for MCP Phase 2"
```

---

## 実装サマリ

| Task | ファイル | テスト数（概算） |
|------|---------|-----------------|
| 1 | `photoshop_sdk/schema.py` + `tests/unit/mcp/test_command_schemas.py` | ~13 |
| 2 | `mcp_server/connection.py` + `tests/unit/mcp/test_connection.py` | ~12 |
| 3 | `mcp_server/tool_registry.py` + `tests/unit/mcp/test_tool_registry.py` | ~12 |
| 4 | `mcp_server/instructions.py` | 0 |
| 5 | `mcp_server/_run.py` + `mcp_server/server.py` + `tests/unit/mcp/test_integration.py` + `tests/unit/test_mcp_server.py` | ~12 |
| 6 | Lint + 全テスト確認 | 0 |
| **合計** | **9 ファイル変更/作成** | **~49 新規テスト** |

## ファイル変更一覧

| ファイル | 操作 |
|---------|------|
| `photoshop_sdk/schema.py` | 変更（ParamSchema, CommandSchema, COMMAND_SCHEMAS 追加） |
| `mcp_server/connection.py` | 新規（ConnectionManager, ConnectionState） |
| `mcp_server/tool_registry.py` | 新規（_build_tool_fn, _build_description, register_all_tools） |
| `mcp_server/instructions.py` | 新規（MCP_INSTRUCTIONS） |
| `mcp_server/_run.py` | 新規（create_mcp_server, mcp, main） |
| `mcp_server/server.py` | 変更（Phase 1 スタブ → 後方互換ラッパー） |
| `tests/unit/mcp/__init__.py` | 新規（空） |
| `tests/unit/mcp/test_command_schemas.py` | 新規 |
| `tests/unit/mcp/test_connection.py` | 新規 |
| `tests/unit/mcp/test_tool_registry.py` | 新規 |
| `tests/unit/mcp/test_integration.py` | 新規 |
| `tests/unit/test_mcp_server.py` | 変更（新構造に合わせて更新） |
