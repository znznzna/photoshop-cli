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

_TYPE_MAP = {str: str, int: int, bool: bool, float: float}

_VALIDATORS = {
    "validate_file_path": validate_file_path,
}


def _build_tool_fn(schema: CommandSchema, conn_mgr: "ConnectionManager"):
    """CommandSchema から FastMCP 互換のツール関数を動的に生成する"""

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

    _schema = schema
    _conn_mgr = conn_mgr

    async def tool_fn(**kwargs) -> dict:
        is_dry_run = kwargs.pop("dry_run", False)

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

    tool_fn.__signature__ = sig
    tool_fn.__name__ = _schema.command.replace(".", "_")
    tool_fn.__qualname__ = tool_fn.__name__

    # Pydantic's get_type_hints() reads __annotations__, not inspect.Signature,
    # so we must sync annotations explicitly for FastMCP tool registration to work.
    annotations: dict[str, Any] = {}
    for p in schema.params:
        annotations[p.name] = _TYPE_MAP.get(p.type, p.type)
    if schema.mutating and schema.supports_dry_run:
        annotations["dry_run"] = bool
    annotations["return"] = dict
    tool_fn.__annotations__ = annotations

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
