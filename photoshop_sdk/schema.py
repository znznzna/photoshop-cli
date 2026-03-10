"""Pydantic モデル定義 - Python SDK と MCP Server の共通型"""

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
