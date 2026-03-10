# MCP Phase 2 設計書 — 動的ツール登録 + ConnectionManager

**日付**: 2026-03-11
**ステータス**: 提案
**目標**: MCP レイヤーの全 6 コマンドを実装し、lightroom-cli の動的パターンを踏襲する

---

## 1. アプローチ比較

| 観点 | A: 手動登録（現行拡張） | B: 動的登録（lightroom-cli 踏襲） | C: ハイブリッド（静的定義 + 動的生成） |
|------|------------------------|----------------------------------|--------------------------------------|
| **概要** | server.py に @mcp.tool() を手書きで6つ追加 | CommandSchema リストから tool_registry が自動生成 | CommandSchema を定義するが、登録は手動 |
| **追加コスト** | 低（既存ファイル編集のみ） | 中（3ファイル新規作成） | 中（CommandSchema + 手動登録） |
| **保守性** | 低（コマンド追加のたびに server.py を編集） | **高**（CommandSchema 追加のみで MCP ツール自動生成） | 中（スキーマと登録の2箇所変更） |
| **lightroom-cli との一貫性** | なし | **完全一致** | 部分的 |
| **型安全性** | 手動で保証 | CommandSchema + inspect.Signature で自動保証 | CommandSchema で保証 |
| **テスト容易性** | 個別テスト必要 | スキーマ駆動で網羅的テスト可能 | 中程度 |
| **将来拡張（layer/selection 等）** | 手動追加が増大 | スキーマ追加のみ | スキーマ追加 + 登録追加 |
| **dry_run 対応** | 各ツールに手動実装 | mutating フラグで自動付与 | 手動実装 |

### 推奨: **B（動的登録）**

**理由**:
1. ユーザーが lightroom-cli パターンの踏襲を明示的に選択済み
2. 今後のコマンド追加（layer, selection, export 等）で保守コストが線形に下がる
3. dry_run / risk_level / requires_confirm のメタデータが CommandSchema に集約され、一貫した振る舞いを保証
4. CLI の schema_gen.py と MCP の tool_registry.py が同じ CommandSchema を共有可能（将来統合）

---

## 2. 推奨アプローチ（B）の詳細設計

### 2.1 アーキテクチャ

```
                    ┌─────────────────────────────────────────┐
                    │            mcp_server/                   │
                    │                                          │
                    │  _run.py          ← エントリポイント     │
                    │    ├─ FastMCP 初期化                     │
                    │    ├─ ConnectionManager 生成             │
                    │    └─ register_all_tools() 呼び出し      │
                    │                                          │
                    │  connection.py    ← 永続クライアント管理  │
                    │    └─ ConnectionManager                  │
                    │        ├─ lazy connect (PhotoshopClient) │
                    │        ├─ asyncio.Lock() 直列化          │
                    │        └─ execute() → dict 返却          │
                    │                                          │
                    │  tool_registry.py ← 動的ツール登録       │
                    │    ├─ COMMAND_SCHEMAS: list[CommandSchema]│
                    │    ├─ register_all_tools(mcp, conn_mgr)  │
                    │    └─ _build_tool_fn() 動的シグネチャ生成 │
                    │                                          │
                    │  instructions.py  ← MCP instructions     │
                    │                                          │
                    │  server.py        ← 後方互換 (mcp 再公開)│
                    └─────────────────────────────────────────┘
                                    │
                                    ▼
                    ┌─────────────────────────────────────────┐
                    │          photoshop_sdk/                   │
                    │  client.py  ← PhotoshopClient            │
                    │  schema.py  ← CommandSchema 定義を追加    │
                    │  validators.py ← validate_file_path()    │
                    │  exceptions.py ← 例外階層                │
                    │  ws_bridge.py ← ResilientWSBridge        │
                    └─────────────────────────────────────────┘
```

### 2.2 データフロー

```
MCP Client (Claude Code)
    │
    ▼  tool call: photoshop_file_open(path="/foo.psd")
FastMCP ─── 動的生成された tool 関数
    │
    ▼  tool_fn(path="/foo.psd")
tool_registry._build_tool_fn() が生成した関数
    │  1. validation (validate_file_path 等)
    │  2. dry_run チェック → dry_run なら即 dict 返却
    │  3. conn_mgr.execute("file.open", {"path": "/foo.psd"})
    │
    ▼
ConnectionManager.execute()
    │  1. lazy connect (PhotoshopClient.start())
    │  2. async with self._lock:
    │  3.   client.execute_command(command, params, timeout)
    │  4. 例外 → dict 変換
    │
    ▼
PhotoshopClient.execute_command()
    │
    ▼
ResilientWSBridge.send_command()
    │
    ▼  WebSocket
UXP Plugin → Photoshop
```

### 2.3 各ファイルの責務と主要コード構造

#### 2.3.1 `photoshop_sdk/schema.py` — CommandSchema 追加

既存の `PhotoshopCommand`, `PhotoshopResponse`, `DocumentInfo` に加え、`CommandSchema` と `ParamSchema` を追加する。

```python
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ParamSchema:
    """コマンドパラメータの定義"""
    name: str                          # "path", "doc_id"
    type: type                         # str, int, bool
    description: str                   # ツール説明に使用
    required: bool = True
    default: Any = None
    # MCP ツール側のパラメータ名（SDK 側と異なる場合）
    # 例: MCP では "doc_id" だが SDK は "documentId"
    sdk_name: str | None = None

    @property
    def effective_sdk_name(self) -> str:
        return self.sdk_name or self.name


@dataclass(frozen=True)
class CommandSchema:
    """コマンドのメタデータ定義"""
    command: str                       # "file.open"
    description: str                   # ツール説明文
    params: list[ParamSchema] = field(default_factory=list)
    mutating: bool = False             # 変更操作か
    risk_level: str = "read"           # "read" | "write" | "destructive"
    requires_confirm: bool = False     # 確認が必要か
    supports_dry_run: bool = False     # dry_run パラメータを自動付与するか
    timeout: float = 30.0             # デフォルトタイムアウト（秒）
    validator: str | None = None       # "validate_file_path" 等
```

**CommandSchema の配置場所**: `photoshop_sdk/schema.py`

SDK レイヤーに置く理由:
- CLI の `schema_gen.py` と MCP の `tool_registry.py` の両方から参照可能
- コマンドのメタデータは SDK の責務（Photoshop コマンドの定義）
- 将来的に CLI を CommandSchema 駆動に統一する際の移行パスが明確

#### 2.3.2 `mcp_server/tool_registry.py` — 動的ツール登録

```python
"""CommandSchema から FastMCP ツールを動的に生成・登録する"""

import inspect
from typing import TYPE_CHECKING

from photoshop_sdk.schema import CommandSchema, ParamSchema, COMMAND_SCHEMAS
from photoshop_sdk.validators import validate_file_path

if TYPE_CHECKING:
    from fastmcp import FastMCP
    from .connection import ConnectionManager

# Python 型 → JSON-friendly な型ヒント（FastMCP が解釈する）
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

    # 2. 実行関数を定義
    async def tool_fn(**kwargs) -> dict:
        # dry_run 処理
        is_dry_run = kwargs.pop("dry_run", False)

        # validator 実行
        if schema.validator and schema.validator in _VALIDATORS:
            validator_fn = _VALIDATORS[schema.validator]
            # validator は最初の required パラメータに適用
            for p in schema.params:
                if p.name in kwargs and p.required:
                    validated = validator_fn(kwargs[p.name])
                    kwargs[p.name] = str(validated)
                    break

        # SDK パラメータ名にマッピング
        sdk_params = {}
        for p in schema.params:
            if p.name in kwargs:
                sdk_params[p.effective_sdk_name] = kwargs[p.name]

        if is_dry_run:
            return {
                "dry_run": True,
                "command": schema.command,
                "params": sdk_params,
                "message": f"Validation passed. Would execute: {schema.command}",
            }

        return await conn_mgr.execute(
            schema.command, sdk_params, timeout=schema.timeout
        )

    # 3. シグネチャと名前を設定
    tool_fn.__signature__ = sig
    tool_fn.__name__ = schema.command.replace(".", "_")
    tool_fn.__qualname__ = tool_fn.__name__

    return tool_fn


def _build_description(schema: CommandSchema) -> str:
    """CommandSchema からツール説明文を構築する"""
    lines = [schema.description]
    lines.append("")

    # メタデータタグ
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

#### 2.3.3 `mcp_server/connection.py` — ConnectionManager

```python
"""MCP セッション中の永続的な Photoshop 接続管理"""

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


class ConnectionManager:
    """PhotoshopClient のライフサイクルとリクエスト直列化を管理する"""

    def __init__(self, host: str = "localhost", port_file: Optional[str] = None):
        self._host = host
        self._port_file = port_file
        self._client: Optional[PhotoshopClient] = None
        self._lock = asyncio.Lock()
        self._connected = False

    async def _ensure_connected(self) -> PhotoshopClient:
        """lazy connect: 未接続なら接続する"""
        if self._client is None or not self._connected:
            self._client = PhotoshopClient(
                host=self._host, port_file=self._port_file
            )
            await self._client.start()
            self._connected = True
            logger.info("PhotoshopClient connected (lazy)")
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
                        "details": e.details,
                    },
                }
            except PSConnectionError as e:
                self._connected = False
                return {
                    "success": False,
                    "error": {
                        "code": "CONNECTION_ERROR",
                        "message": str(e),
                    },
                }
            except PSTimeoutError as e:
                return {
                    "success": False,
                    "error": {
                        "code": "TIMEOUT_ERROR",
                        "message": str(e),
                    },
                }
            except DocumentNotFoundError as e:
                return {
                    "success": False,
                    "error": {
                        "code": e.code or "DOCUMENT_NOT_FOUND",
                        "message": str(e),
                        "details": e.details,
                    },
                }
            except PhotoshopSDKError as e:
                return {
                    "success": False,
                    "error": {
                        "code": e.code or "SDK_ERROR",
                        "message": str(e),
                    },
                }

    async def disconnect(self) -> None:
        """接続を切断する"""
        if self._client:
            await self._client.stop()
            self._client = None
            self._connected = False

    async def status(self) -> dict:
        """接続状態を返す"""
        return {
            "connected": self._connected,
            "host": self._host,
        }
```

**lightroom-cli との差分**:
- photoshop-cli は**逆転 WebSocket**（Python がサーバー）のため、`_ensure_connected` は `client.start()` で WS サーバーを起動し UXP Plugin の接続を待つ。lightroom-cli の `_ensure_connected` は WS クライアントとして接続する
- `mutating` コマンドの再接続後チェックは Phase 2 では省略（photoshop-cli の逆転 WS 構造では Plugin 側が再接続してくるため、サーバー側で再接続を能動的に行う必要がない）

#### 2.3.4 `mcp_server/_run.py` — エントリポイント

```python
"""FastMCP サーバー初期化とツール登録"""

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

    # photoshop://status リソース
    @mcp.resource("photoshop://status")
    async def connection_status() -> dict:
        """Photoshop 接続状態"""
        return await conn_mgr.status()

    return mcp


mcp = create_mcp_server()


def main():
    """MCP Server エントリポイント"""
    mcp.run()
```

#### 2.3.5 `mcp_server/instructions.py` — MCP instructions

```python
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

#### 2.3.6 `mcp_server/server.py` — 後方互換

```python
"""後方互換: mcp オブジェクトと main() を再公開"""
from mcp_server._run import main, mcp

__all__ = ["main", "mcp"]
```

### 2.4 CommandSchema 定義（6 コマンド）

`photoshop_sdk/schema.py` に追加:

```python
COMMAND_SCHEMAS: list[CommandSchema] = [
    CommandSchema(
        command="file.list",
        description="List all open Photoshop documents.",
        params=[],
        mutating=False,
        risk_level="read",
        requires_confirm=False,
        supports_dry_run=False,
        timeout=30.0,
    ),
    CommandSchema(
        command="file.info",
        description="Get detailed information for a specific document.",
        params=[
            ParamSchema(
                name="doc_id",
                type=int,
                description="Document ID",
                required=True,
                sdk_name="documentId",
            ),
        ],
        mutating=False,
        risk_level="read",
        requires_confirm=False,
        supports_dry_run=False,
        timeout=30.0,
    ),
    CommandSchema(
        command="file.open",
        description="Open a PSD file in Photoshop.",
        params=[
            ParamSchema(
                name="path",
                type=str,
                description="Absolute path to the PSD file",
                required=True,
            ),
        ],
        mutating=True,
        risk_level="write",
        requires_confirm=False,
        supports_dry_run=True,
        timeout=120.0,
        validator="validate_file_path",
    ),
    CommandSchema(
        command="file.close",
        description="Close a document. Use --save to save before closing.",
        params=[
            ParamSchema(
                name="doc_id",
                type=int,
                description="Document ID to close",
                required=True,
                sdk_name="documentId",
            ),
            ParamSchema(
                name="save",
                type=bool,
                description="Save before closing",
                required=False,
                default=False,
            ),
        ],
        mutating=True,
        risk_level="write",
        requires_confirm=True,
        supports_dry_run=True,
        timeout=30.0,
    ),
    CommandSchema(
        command="file.save",
        description="Save a document.",
        params=[
            ParamSchema(
                name="doc_id",
                type=int,
                description="Document ID to save",
                required=True,
                sdk_name="documentId",
            ),
        ],
        mutating=True,
        risk_level="write",
        requires_confirm=False,
        supports_dry_run=True,
        timeout=30.0,
    ),
    CommandSchema(
        command="system.ping",
        description="Check connection to Photoshop UXP Plugin.",
        params=[],
        mutating=False,
        risk_level="read",
        requires_confirm=False,
        supports_dry_run=False,
        timeout=5.0,
    ),
]
```

### 2.5 エラーハンドリング方針

MCP レイヤーでは**例外を投げず dict で返す**方針を採用:

| レイヤー | エラー表現 | 理由 |
|---------|-----------|------|
| SDK (client.py, ws_bridge.py) | 例外を送出 | Python 標準のエラーハンドリング |
| CLI (commands/) | 例外を catch → exit code + 表示 | CLI の慣習 |
| **MCP (connection.py)** | **例外を catch → dict 返却** | MCP プロトコルの制約（JSON レスポンス） |

**ConnectionManager.execute()** が全例外を catch し、以下の形式で返す:

```python
# 成功時
{"success": True, "documentId": 1, "name": "file.psd", ...}

# 失敗時
{"success": False, "error": {"code": "CONNECTION_ERROR", "message": "..."}}
```

**validation エラー**（validate_file_path 等）は `tool_registry._build_tool_fn()` 内で発生するため、tool_fn 内で catch して dict 返却する。ConnectionManager に到達する前にバリデーションエラーを処理する。

```python
# tool_fn 内の validation エラーハンドリング
async def tool_fn(**kwargs) -> dict:
    try:
        if schema.validator:
            ...  # validation
    except PSValidationError as e:
        return {
            "success": False,
            "error": {"code": "VALIDATION_ERROR", "message": str(e)},
        }
    ...
```

### 2.6 テスト戦略

#### 2.6.1 テスト構成

```
tests/unit/
  test_mcp_server.py        ← 既存（拡張）
  mcp/                      ← 新規ディレクトリ
    __init__.py
    test_tool_registry.py   ← ツール登録・シグネチャ検証
    test_connection.py      ← ConnectionManager ユニットテスト
    test_command_schemas.py  ← CommandSchema 定義の網羅性検証
    test_integration.py     ← FastMCP TestClient による E2E テスト
```

#### 2.6.2 テストパターン

**1. CommandSchema 網羅性テスト** (`test_command_schemas.py`):

```python
from photoshop_sdk.schema import COMMAND_SCHEMAS

def test_all_commands_have_schemas():
    """全6コマンドの CommandSchema が定義されている"""
    commands = {s.command for s in COMMAND_SCHEMAS}
    expected = {"file.list", "file.info", "file.open", "file.close", "file.save", "system.ping"}
    assert commands == expected

def test_risk_levels_valid():
    """risk_level が許可された値のみ"""
    for s in COMMAND_SCHEMAS:
        assert s.risk_level in ("read", "write", "destructive")

def test_mutating_commands_have_dry_run():
    """mutating コマンドは supports_dry_run が有効"""
    for s in COMMAND_SCHEMAS:
        if s.mutating:
            assert s.supports_dry_run, f"{s.command} is mutating but doesn't support dry_run"
```

**2. ツール登録テスト** (`test_tool_registry.py`):

```python
from fastmcp import FastMCP
from unittest.mock import AsyncMock
from mcp_server.tool_registry import register_all_tools

def test_all_tools_registered():
    """全 CommandSchema がツールとして登録される"""
    mcp = FastMCP(name="test")
    conn_mgr = AsyncMock()
    register_all_tools(mcp, conn_mgr)
    # FastMCP の登録済みツール数を検証
    # (FastMCP の内部 API に依存 — 要確認)

def test_tool_signatures():
    """動的生成されたツール関数のシグネチャが正しい"""
    ...

def test_dry_run_parameter_added_for_mutating():
    """mutating コマンドに dry_run パラメータが自動追加される"""
    ...
```

**3. ConnectionManager テスト** (`test_connection.py`):

```python
import pytest
from unittest.mock import AsyncMock, patch

@pytest.fixture
def conn_mgr():
    return ConnectionManager(host="localhost")

async def test_lazy_connect(conn_mgr):
    """初回 execute で自動接続する"""
    ...

async def test_exception_to_dict(conn_mgr):
    """SDK 例外が dict に変換される"""
    ...

async def test_lock_serialization(conn_mgr):
    """同時リクエストが直列化される"""
    ...
```

**4. FastMCP TestClient 統合テスト** (`test_integration.py`):

```python
import pytest
from fastmcp import Client
from mcp_server._run import create_mcp_server

@pytest.fixture
def mcp_server():
    return create_mcp_server()

async def test_file_list_tool(mcp_server):
    """file_list ツールが呼び出せる"""
    async with Client(mcp_server) as client:
        tools = await client.list_tools()
        tool_names = [t.name for t in tools]
        assert "file_list" in tool_names

async def test_system_ping_tool(mcp_server):
    """system_ping ツールが呼び出せる"""
    async with Client(mcp_server) as client:
        # PhotoshopClient をモックして実行
        ...
```

### 2.7 CLI との共有ポイント

| 共有コンポーネント | 場所 | CLI 使用 | MCP 使用 |
|-------------------|------|---------|---------|
| `validate_file_path()` | `photoshop_sdk/validators.py` | file.open コマンド | tool_registry (validator フィールド) |
| `PhotoshopClient` | `photoshop_sdk/client.py` | 各コマンドで直接使用 | ConnectionManager 経由 |
| 例外階層 | `photoshop_sdk/exceptions.py` | catch → exit code | catch → dict 変換 |
| `DocumentInfo` | `photoshop_sdk/schema.py` | レスポンス型 | レスポンス型（将来） |
| **`CommandSchema`** (新規) | `photoshop_sdk/schema.py` | 将来: schema_gen.py 統合 | tool_registry.py |
| `COMMAND_TIMEOUTS` | `photoshop_sdk/client.py` | タイムアウト設定 | CommandSchema.timeout で上書き |

### 2.8 ファイル変更サマリ

| ファイル | 操作 | 内容 |
|---------|------|------|
| `photoshop_sdk/schema.py` | **変更** | ParamSchema, CommandSchema, COMMAND_SCHEMAS 追加 |
| `mcp_server/_run.py` | **新規** | FastMCP 初期化 + ConnectionManager + register_all_tools |
| `mcp_server/connection.py` | **新規** | ConnectionManager クラス |
| `mcp_server/tool_registry.py` | **新規** | 動的ツール登録ロジック |
| `mcp_server/instructions.py` | **新規** | MCP_INSTRUCTIONS 定数 |
| `mcp_server/server.py` | **変更** | Phase 1 スタブ → 後方互換ラッパー |
| `mcp_server/__init__.py` | **変更** | 必要に応じて更新 |
| `tests/unit/mcp/` | **新規** | 4 テストファイル |
| `tests/unit/test_mcp_server.py` | **変更** | 新構造に合わせて更新 |

---

## 3. 不確実な点・要確認事項

### 3.1 FastMCP 3.x の動的ツール登録 API

- lightroom-cli で使用している `mcp.tool(name=..., description=...)(fn)` パターンが FastMCP 3.x で動作するか要確認
- FastMCP 3.x の `Client` (TestClient) の API が `list_tools()` / `call_tool()` をサポートするか要確認
- 確認方法: `from fastmcp import Client` の import テストを実行

### 3.2 逆転 WebSocket の lazy connect タイミング

- ConnectionManager の `_ensure_connected()` は WS サーバーを起動するが、UXP Plugin の接続完了を待つ必要があるか
- 現在の `PhotoshopClient.start()` は `ResilientWSBridge.start()` を呼ぶだけで、Plugin の接続を待たない
- 最初の `execute_command()` で接続がない場合は `ConnectionError` が返る（現状の振る舞い）
- **結論**: lazy connect は「サーバー起動」までとし、Plugin 接続は execute 時にチェック（現行動作と同じ）

### 3.3 pyproject.toml のエントリポイント

- 現在の `psd-mcp` エントリポイントが `mcp_server.server:main` を指しているか確認
- `mcp_server._run:main` に変更するか、`server.py` の後方互換ラッパーで対応するか
- **推奨**: `server.py` の後方互換ラッパーにより、エントリポイント変更不要

### 3.4 ConnectionManager のライフサイクル

- MCP セッション終了時に `conn_mgr.disconnect()` を呼ぶ必要があるか
- FastMCP のシャットダウンフックがあるか確認
- なければ、Python の `atexit` または `signal` ハンドラで対応

---

## 4. 実装順序（推奨）

| Step | 内容 | 依存 |
|------|------|------|
| 1 | `photoshop_sdk/schema.py` に CommandSchema + COMMAND_SCHEMAS 追加 | なし |
| 2 | `tests/unit/mcp/test_command_schemas.py` 作成・テスト通過 | Step 1 |
| 3 | `mcp_server/connection.py` 作成 | なし |
| 4 | `tests/unit/mcp/test_connection.py` 作成・テスト通過 | Step 3 |
| 5 | `mcp_server/tool_registry.py` 作成 | Step 1 |
| 6 | `tests/unit/mcp/test_tool_registry.py` 作成・テスト通過 | Step 5 |
| 7 | `mcp_server/instructions.py` 作成 | なし |
| 8 | `mcp_server/_run.py` 作成 | Step 3, 5, 7 |
| 9 | `mcp_server/server.py` を後方互換ラッパーに変更 | Step 8 |
| 10 | `tests/unit/mcp/test_integration.py` 作成・テスト通過 | Step 8 |
| 11 | `tests/unit/test_mcp_server.py` 更新 | Step 9 |
| 12 | 全テスト通過確認 + ruff check/format | 全 Step |
