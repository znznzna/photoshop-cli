import json
import re
from io import StringIO
from typing import Any

from rich.console import Console
from rich.table import Table


class OutputFormatter:
    _OUTPUT_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
    _MAX_OUTPUT_STRING_LENGTH = 50_000

    @staticmethod
    def _sanitize_output(data: Any, *, truncate: bool = False, _truncated: list | None = None) -> Any:
        """制御文字を除去し、長文字列を切り詰める"""
        if isinstance(data, str):
            s = OutputFormatter._OUTPUT_CONTROL_CHAR_RE.sub("", data)
            if truncate and len(s) > OutputFormatter._MAX_OUTPUT_STRING_LENGTH:
                if _truncated is not None:
                    _truncated.append(True)
                return s[: OutputFormatter._MAX_OUTPUT_STRING_LENGTH] + f"... (truncated, {len(data)} chars total)"
            return s
        if isinstance(data, dict):
            return {
                k: OutputFormatter._sanitize_output(v, truncate=truncate, _truncated=_truncated)
                for k, v in data.items()
            }
        if isinstance(data, list):
            return [OutputFormatter._sanitize_output(item, truncate=truncate, _truncated=_truncated) for item in data]
        return data

    @staticmethod
    def format(data: Any, mode: str = "text", fields: list[str] | None = None) -> str:
        truncated_tracker: list = []
        data = OutputFormatter._sanitize_output(data, truncate=(mode == "json"), _truncated=truncated_tracker)
        if truncated_tracker and isinstance(data, dict):
            data["_truncated"] = True

        if mode == "json":
            return json.dumps(data, indent=2, ensure_ascii=False)
        elif mode == "table":
            return OutputFormatter._format_table(data)
        else:
            return OutputFormatter._format_text(data)

    @staticmethod
    def _format_text(data: Any, indent: int = 0) -> str:
        if isinstance(data, dict):
            lines = []
            for k, v in data.items():
                if isinstance(v, (dict, list)):
                    lines.append(f"{'  ' * indent}{k}:")
                    lines.append(OutputFormatter._format_text(v, indent + 1))
                else:
                    lines.append(f"{'  ' * indent}{k}: {v}")
            return "\n".join(lines)
        elif isinstance(data, list):
            return "\n".join(OutputFormatter._format_text(item, indent) for item in data)
        return str(data)

    @staticmethod
    def _format_table(data: Any) -> str:
        if not isinstance(data, list) or not data:
            return OutputFormatter._format_text(data)
        console = Console(file=StringIO(), force_terminal=False, width=120)
        table = Table(show_lines=False, pad_edge=True)
        for key in data[0].keys():
            table.add_column(key, no_wrap=True, overflow="ellipsis")
        for row in data:
            table.add_row(*[str(v) for v in row.values()])
        console.print(table)
        return console.file.getvalue()

    @staticmethod
    def format_error(
        message: str,
        mode: str = "text",
        *,
        code: str = "ERROR",
        command: str | None = None,
        suggestions: list[str] | None = None,
    ) -> str:
        if mode == "json":
            error_obj: dict[str, Any] = {
                "code": code,
                "message": message,
            }
            if command:
                error_obj["command"] = command
            if suggestions:
                error_obj["suggestions"] = suggestions
            return json.dumps({"error": error_obj})
        return f"Error: {message}"
