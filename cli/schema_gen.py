"""Click コマンドツリーから JSON Schema を生成する"""

from typing import Any

import click

from photoshop_sdk.schema import DocumentInfo

# コマンドごとの response schema マッピング
_DOCUMENT_RESPONSE_SCHEMAS: dict[str, Any] = {
    "document.list": {
        "type": "array",
        "items": DocumentInfo.model_json_schema(),
        "description": "List of open documents",
    },
    "document.info": DocumentInfo.model_json_schema(),
    "document.open": {
        "type": "object",
        "properties": {
            "documentId": {"type": "integer", "description": "Opened document ID"},
            "name": {"type": "string", "description": "Document name"},
        },
    },
    "document.close": {
        "type": "object",
        "properties": {
            "closed": {"type": "boolean"},
        },
    },
    "document.save": {
        "type": "object",
        "properties": {
            "saved": {"type": "boolean"},
        },
    },
}

# file.* エイリアスの response schema を自動生成
_FILE_RESPONSE_SCHEMAS: dict[str, Any] = {
    k.replace("document.", "file."): v for k, v in _DOCUMENT_RESPONSE_SCHEMAS.items()
}

_RESPONSE_SCHEMAS: dict[str, Any] = {
    **_DOCUMENT_RESPONSE_SCHEMAS,
    **_FILE_RESPONSE_SCHEMAS,
    "system.ping": {
        "type": "object",
        "properties": {
            "status": {"type": "string", "description": "Connection status"},
        },
    },
}

# Click 型 → JSON Schema 型マッピング
_CLICK_TYPE_MAP: dict[type, str] = {
    click.INT: "integer",
    click.FLOAT: "number",
    click.STRING: "string",
    click.BOOL: "boolean",
}


def _click_type_to_json_type(param_type: click.ParamType) -> str:
    """Click のパラメータ型を JSON Schema 型に変換"""
    for click_type, json_type in _CLICK_TYPE_MAP.items():
        if isinstance(param_type, type(click_type)):
            return json_type
    if isinstance(param_type, click.Choice):
        return "string"
    return "string"


def _click_type_to_enum(param_type: click.ParamType) -> list[str] | None:
    """Choice 型の場合は enum を返す"""
    if isinstance(param_type, click.Choice):
        return list(param_type.choices)
    return None


def generate_command_schema(cmd_path: str, cli_group: click.Group) -> dict[str, Any] | None:
    """コマンドパス（例: "file.open"）から JSON Schema を生成

    Returns:
        JSON Schema dict。コマンドが見つからない場合は None。
    """
    parts = cmd_path.split(".")
    current: click.BaseCommand = cli_group

    # コマンドツリーを辿る
    for part in parts:
        if isinstance(current, click.Group):
            current = current.commands.get(part)
            if current is None:
                return None
        else:
            return None

    if not isinstance(current, click.Command):
        return None

    # パラメータを収集
    params_schema: dict[str, Any] = {}
    required_params: list[str] = []

    for param in current.params:
        if param.name in ("help",):
            continue

        param_info: dict[str, Any] = {
            "type": _click_type_to_json_type(param.type),
        }

        help_text = getattr(param, "help", None)
        if help_text:
            param_info["description"] = help_text

        enum_values = _click_type_to_enum(param.type)
        if enum_values:
            param_info["enum"] = enum_values

        if param.default is not None and param.default != ():
            try:
                import json as _json

                _json.dumps(param.default)
                param_info["default"] = param.default
            except (TypeError, ValueError):
                pass

        if param.required:
            required_params.append(param.name)

        # Click の Argument は位置引数
        if isinstance(param, click.Argument):
            param_info["_cli_type"] = "argument"
            required_params.append(param.name)
        else:
            param_info["_cli_type"] = "option"

        params_schema[param.name] = param_info

    schema: dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": cmd_path,
        "description": current.help or "",
        "type": "object",
        "properties": {
            "command": {"const": cmd_path},
            "params": {
                "type": "object",
                "properties": params_schema,
                "required": list(set(required_params)),
            },
        },
    }

    # response schema があれば追加
    response_schema = _RESPONSE_SCHEMAS.get(cmd_path)
    if response_schema:
        schema["response"] = response_schema

    return schema


def list_available_commands(cli_group: click.Group, prefix: str = "") -> list[str]:
    """利用可能なコマンドパスの一覧を返す"""
    commands: list[str] = []
    for name, cmd in cli_group.commands.items():
        full_path = f"{prefix}{name}" if not prefix else f"{prefix}.{name}"
        if isinstance(cmd, click.Group):
            commands.extend(list_available_commands(cmd, full_path))
        else:
            commands.append(full_path)
    return commands
