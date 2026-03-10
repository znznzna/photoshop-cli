"""入力バリデーション純関数 -- CLI / MCP Server の両方から呼び出し可能"""

import os
import re
from pathlib import Path

from .exceptions import ValidationError

# 制御文字パターン（\t, \n, \r も含む -- ファイルパスに含まれるべきでない）
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f]")


def validate_file_path(path: str) -> Path:
    """ファイルパスのバリデーション。正規化済み Path を返す。

    検証項目:
    1. 空文字列の拒否
    2. 制御文字の拒否
    3. パストラバーサル（".." を含む）の拒否
    4. ファイル存在確認

    Raises:
        ValidationError: バリデーション失敗時（exit code 4）
    """
    # 1. 空文字列
    if not path or not path.strip():
        raise ValidationError(
            "File path must not be empty",
            code="VALIDATION_ERROR",
            details={"field": "path", "rule": "non_empty"},
        )

    # 2. 制御文字
    if _CONTROL_CHAR_RE.search(path):
        raise ValidationError(
            "File path contains invalid control characters",
            code="VALIDATION_ERROR",
            details={"field": "path", "rule": "no_control_chars"},
        )

    # 3. パストラバーサル
    # resolve() 前の生パスで ".." を検出（resolve 後は消えるため）
    normalized = os.path.normpath(path)
    if ".." in normalized.split(os.sep):
        raise ValidationError(
            "File path must not contain path traversal sequences (..)",
            code="VALIDATION_ERROR",
            details={"field": "path", "rule": "no_traversal"},
        )

    # 4. ~ 展開 + 絶対パス化 + 存在確認
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists():
        raise ValidationError(
            f"File not found: {path}",
            code="VALIDATION_ERROR",
            details={"field": "path", "rule": "file_exists", "path": str(resolved)},
        )

    if not resolved.is_file():
        raise ValidationError(
            f"Path is not a file: {path}",
            code="VALIDATION_ERROR",
            details={"field": "path", "rule": "is_file", "path": str(resolved)},
        )

    return resolved
