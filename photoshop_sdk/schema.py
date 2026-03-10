"""Pydantic モデル定義 - Python SDK と MCP Server の共通型"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class PhotoshopCommand(BaseModel):
    """Python → UXP へのコマンド送信メッセージ"""

    id: str
    command: str
    params: Dict[str, Any] = Field(default_factory=dict)


class PhotoshopResponse(BaseModel):
    """UXP → Python への結果返却メッセージ"""

    id: str
    success: bool
    result: Optional[Dict[str, Any]] = None
    error: Optional[Dict[str, Any]] = None


class DocumentInfo(BaseModel):
    """Photoshop ドキュメント情報"""

    documentId: int
    name: str
    path: Optional[str] = None
    width: int
    height: int
    colorMode: Optional[str] = None
    resolution: Optional[float] = None
    hasUnsavedChanges: Optional[bool] = None


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
