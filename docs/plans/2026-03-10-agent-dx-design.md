# Agent DX 改善設計書 — 5機能の詳細設計

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** エージェントが photoshop-cli を安全かつ効率的に操作できるよう、入力バリデーション・`--fields`・`--dry-run`・`psd schema`・SKILL.md 不変条件の5機能を追加する
**Date:** 2026-03-10
**Status:** Draft — 承認待ち

---

## 1. アプローチ比較

### 1-A. バリデーション層の配置

| アプローチ | 概要 | メリット | デメリット |
|---|---|---|---|
| **A1: CLI層のみ** | Click コールバック / カスタム型でバリデーション | シンプル、CLI固有ロジック（パス解決等）に近い | MCP Server で再利用不可。Phase 2 で重複実装が発生 |
| **A2: SDK層のみ** | `PhotoshopClient` のメソッド冒頭でバリデーション | MCP/CLI 両方で共有可能 | パス解決など CLI 固有の関心事が SDK に漏れる |
| **A3: 共通バリデータ + 層別呼び出し（推奨）** | `photoshop_sdk/validators.py` に純関数を定義し、CLI層・SDK層それぞれが適切なタイミングで呼び出す | 再利用性◎、関心分離◎、テスト容易 | ファイル1つ増える（許容範囲） |

### 1-B. スキーマ生成方法

| アプローチ | 概要 | メリット | デメリット |
|---|---|---|---|
| **B1: Click イントロスペクション** | `click.Command` オブジェクトの params を走査して JSON Schema 生成 | 実装が Click に閉じる、メンテ不要（コマンド追加で自動反映） | Click の型情報は限定的（description が help 文字列のみ） |
| **B2: 手書き JSON Schema 定義** | 各コマンドの JSON Schema を手動定義 | 正確で柔軟 | メンテナンスコスト高、コマンド追加時に忘れやすい |
| **B3: Click + Pydantic ハイブリッド（推奨）** | Click パラメータを走査しつつ、SDK の Pydantic モデル（`DocumentInfo` 等）から response schema を補完 | 自動生成 + 型情報豊富、DRY | やや実装が複雑（だが1回書けばOK） |

### 推奨: A3 + B3

**根拠:**
1. Phase 2 の MCP Server 実装時に validators.py をそのまま使える
2. スキーマは Click 定義が Single Source of Truth — コマンド追加時の手動メンテが不要
3. Pydantic モデルを response schema に活用することで、エージェントが出力構造も把握できる

---

## 2. 推奨アプローチの詳細設計

### 2.1 ファイル変更一覧

| ファイル | 変更種別 | 内容 |
|---|---|---|
| `photoshop_sdk/validators.py` | **新規** | パスバリデーション純関数群 |
| `photoshop_sdk/exceptions.py` | 修正 | `ValidationError` に `field` 属性追加 |
| `cli/commands/file.py` | 修正 | バリデーション呼び出し、`--dry-run` 対応 |
| `cli/main.py` | 修正 | `--fields` グローバルオプション追加 |
| `cli/output.py` | 修正 | `fields` フィルタリング実装 |
| `cli/commands/schema.py` | **新規** | `psd schema` サブコマンド |
| `cli/schema_gen.py` | **新規** | Click → JSON Schema 変換ロジック |
| `plugin/skills/photoshop-cli/SKILL.md` | 修正 | エージェント不変条件セクション追加 |
| `tests/unit/sdk/test_validators.py` | **新規** | バリデータのユニットテスト |
| `tests/unit/cli/test_fields.py` | **新規** | `--fields` のユニットテスト |
| `tests/unit/cli/test_dry_run.py` | **新規** | `--dry-run` のユニットテスト |
| `tests/unit/cli/test_schema_cmd.py` | **新規** | `psd schema` のユニットテスト |

---

### 2.2 P0: 入力バリデーション

#### 2.2.1 `photoshop_sdk/validators.py`（新規）

```python
"""入力バリデーション純関数 — CLI / MCP Server の両方から呼び出し可能"""

import os
import re
from pathlib import Path

from .exceptions import ValidationError

# 制御文字パターン（\t, \n, \r は許容しない — ファイルパスに含まれるべきでない）
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f]")

# パストラバーサルパターン
_TRAVERSAL_PATTERNS = ("..", "~")


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
    # resolve() 前の生パスで ".." を検出（resolve後は消えるため）
    normalized = os.path.normpath(path)
    if ".." in normalized.split(os.sep):
        raise ValidationError(
            "File path must not contain path traversal sequences (..)",
            code="VALIDATION_ERROR",
            details={"field": "path", "rule": "no_traversal"},
        )

    # 4. 存在確認
    resolved = Path(path).resolve()
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
```

**設計判断:**
- **純関数**にすることで、テスト容易性と再利用性を確保
- `ValidationError` は既存の例外を活用（exit code 4 が SKILL.md で既に定義済み）
- `details` dict に `field` と `rule` を含めることで、エージェントがプログラマティックにエラー原因を特定できる
- `~` を含むパスは `Path.resolve()` で展開されるため明示的に拒否しない。ただし `..` は resolve 前に検出する（resolve 後は消えてしまうため）

#### 2.2.2 `cli/commands/file.py` への統合

`file_open` コマンドの冒頭でバリデーションを呼び出す:

```python
from photoshop_sdk.validators import validate_file_path

@file_cmd.command("open")
@click.argument("path")
@click.pass_context
def file_open(ctx, path: str):
    """Open a PSD file in Photoshop"""
    fmt = ctx.obj.get("output", "text") if ctx.obj else "text"
    timeout = ctx.obj.get("timeout", 30.0) if ctx.obj else 30.0

    # バリデーション（Photoshop に送信する前にローカルで検証）
    try:
        resolved = validate_file_path(path)
        path = str(resolved)  # 正規化済みパスを使用
    except ValidationError as e:
        click.echo(
            OutputFormatter.format_error(str(e), fmt, code=e.code or "VALIDATION_ERROR"),
            err=True,
        )
        ctx.exit(4)
        return

    # 以降は既存ロジック（変更なし）
    async def _run():
        ...
```

#### 2.2.3 `_handle_client_error` への `ValidationError` 追加

```python
from photoshop_sdk.exceptions import (
    ConnectionError as PSConnectionError,
    PhotoshopSDKError,
    TimeoutError as PSTimeoutError,
    ValidationError as PSValidationError,
)

def _handle_client_error(ctx, e: Exception, fmt: str) -> None:
    if isinstance(e, PSValidationError):
        click.echo(
            OutputFormatter.format_error(str(e), fmt, code="VALIDATION_ERROR"),
            err=True,
        )
        ctx.exit(4)
    elif isinstance(e, PSConnectionError):
        ...  # 既存のまま
```

---

### 2.3 P1: `--fields` 実装

#### 2.3.1 `cli/main.py` — グローバルオプション追加

```python
@click.group()
@click.version_option(version="0.1.0", prog_name="psd")
@click.option("--output", "-o", type=click.Choice(["json", "text", "table"]), default=None,
              help="Output format (default: json for non-TTY, text for TTY)")
@click.option("--fields", "-f", type=str, default=None,
              help="Comma-separated list of fields to include in output (e.g. 'id,name')")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.option("--timeout", "-t", type=float, default=None,
              help="Default command timeout in seconds")
@click.pass_context
def cli(ctx, output, fields, verbose, timeout):
    ctx.ensure_object(dict)
    ctx.obj["output"] = resolve_output_format(output)
    ctx.obj["fields"] = [f.strip() for f in fields.split(",")] if fields else None
    ctx.obj["verbose"] = verbose or bool(os.environ.get("PS_VERBOSE"))
    ctx.obj["timeout"] = resolve_timeout(timeout)
    ...
```

#### 2.3.2 `cli/output.py` — `fields` フィルタリング実装

`format()` メソッドの `fields` パラメータを実装する:

```python
@staticmethod
def format(data: Any, mode: str = "text", fields: list[str] | None = None) -> str:
    truncated_tracker: list = []
    data = OutputFormatter._sanitize_output(data, truncate=(mode == "json"), _truncated=truncated_tracker)
    if truncated_tracker and isinstance(data, dict):
        data["_truncated"] = True

    # fields フィルタリング
    if fields:
        data = OutputFormatter._filter_fields(data, fields)

    if mode == "json":
        return json.dumps(data, indent=2, ensure_ascii=False)
    elif mode == "table":
        return OutputFormatter._format_table(data)
    else:
        return OutputFormatter._format_text(data)

@staticmethod
def _filter_fields(data: Any, fields: list[str]) -> Any:
    """指定されたフィールドのみを残す"""
    if isinstance(data, dict):
        return {k: v for k, v in data.items() if k in fields}
    elif isinstance(data, list):
        return [OutputFormatter._filter_fields(item, fields) for item in data]
    return data
```

#### 2.3.3 各コマンドでの `fields` 受け渡し

`file.py` の各コマンドで `ctx.obj["fields"]` を `OutputFormatter.format()` に渡す:

```python
fields = ctx.obj.get("fields") if ctx.obj else None
click.echo(OutputFormatter.format(data, fmt, fields=fields))
```

**設計判断:**
- `--fields` はグローバルオプション。全コマンドで一貫して使える
- フィルタリングは出力層（`OutputFormatter`）で行う。SDK の返却値には手を加えない
- 存在しないフィールド名を指定した場合はサイレントに無視する（エージェントがスキーマを見て正しいフィールド名を使う前提）
- ネストされたフィールド（ドット記法 `layers.name` 等）は YAGNI で今回は対象外

---

### 2.4 P1: SKILL.md エージェント不変条件

`plugin/skills/photoshop-cli/SKILL.md` に以下のセクションを追加:

```markdown
## エージェント不変条件（Agent Invariants）

以下のルールは **必ず** 遵守すること。違反するとデータ損失やユーザーの信頼を損なう。

### 1. 変更操作の前にユーザー確認を取る

`file open`, `file close`, `file save` は Photoshop の状態を変更する。
実行前に必ずユーザーに確認を取ること。

```
❌ psd file close --doc-id 1
✅ 「Document 1 (photo.psd) を閉じてもよいですか？」→ 承認後に実行
```

### 2. 読み取り操作は `--output json` で呼ぶ

`file list` と `file info` は必ず `--output json` を指定すること。
テキスト出力はパースが不安定で、エージェントのハルシネーションの原因になる。

```bash
# 正しい
psd --output json file list
psd --output json file info --doc-id 1

# 間違い（パースエラーの原因）
psd file list
```

### 3. `--fields` でコンテキストウィンドウを節約する

必要なフィールドだけを取得すること。全フィールドを取得するとコンテキストウィンドウを浪費する。

```bash
# ドキュメント一覧から名前とIDだけ取得
psd --output json --fields documentId,name file list

# ドキュメントのサイズ情報だけ取得
psd --output json --fields width,height,resolution file info --doc-id 1
```

### 4. `--dry-run` で事前検証する

変更操作を実行する前に `--dry-run` で検証すること。
バリデーションエラーを事前に検出し、不要な Photoshop 操作を防ぐ。

```bash
# まず dry-run で検証
psd --output json file open --dry-run /path/to/file.psd

# 成功を確認してから実行
psd --output json file open /path/to/file.psd
```

### 5. エラーハンドリング

exit code を確認し、適切に対処すること:

| Exit Code | 意味 | 対処 |
|---|---|---|
| 0 | 成功 | 続行 |
| 1 | 一般エラー | エラーメッセージを確認し、ユーザーに報告 |
| 2 | 接続エラー | Photoshop/プラグインの起動状態を確認するようユーザーに案内 |
| 3 | タイムアウト | `--timeout` を延長して再試行 |
| 4 | バリデーションエラー | 入力パラメータを修正して再試行 |

### 6. スキーマイントロスペクション

コマンドの引数やオプションが不明な場合は `psd schema` で確認すること。
ハルシネーションでパラメータを推測してはいけない。

```bash
# file.open の引数を確認
psd --output json schema file.open
```
```

---

### 2.5 P2: `--dry-run` フラグ

#### 2.5.1 設計方針

- **変更操作のみ**: `file open`, `file close`, `file save` に適用
- **読み取り操作**: `file list`, `file info` は dry-run 不要（そもそも副作用がない）
- **動作**: ローカルバリデーションのみ実行し、Photoshop への送信をスキップ
- **出力**: 「送信予定のコマンド」を JSON で返す

#### 2.5.2 `cli/main.py` — グローバルオプション追加

```python
@click.option("--dry-run", is_flag=True, default=False,
              help="Validate inputs and show the command that would be sent, without executing")
```

`ctx.obj["dry_run"]` に格納。

#### 2.5.3 `cli/commands/file.py` — dry-run 対応

変更コマンドに共通のパターンを適用:

```python
@file_cmd.command("open")
@click.argument("path")
@click.pass_context
def file_open(ctx, path: str):
    fmt = ctx.obj.get("output", "text") if ctx.obj else "text"
    timeout = ctx.obj.get("timeout", 30.0) if ctx.obj else 30.0
    dry_run = ctx.obj.get("dry_run", False) if ctx.obj else False
    fields = ctx.obj.get("fields") if ctx.obj else None

    # バリデーション（dry-run でも実行する）
    try:
        resolved = validate_file_path(path)
        path = str(resolved)
    except ValidationError as e:
        click.echo(
            OutputFormatter.format_error(str(e), fmt, code=e.code or "VALIDATION_ERROR"),
            err=True,
        )
        ctx.exit(4)
        return

    # dry-run: バリデーション通過後、送信予定のコマンドを表示して終了
    if dry_run:
        dry_run_output = {
            "dry_run": True,
            "command": "file.open",
            "params": {"path": path},
            "timeout": timeout,
            "message": "Validation passed. This command would open the file in Photoshop.",
        }
        click.echo(OutputFormatter.format(dry_run_output, fmt, fields=fields))
        return

    # 以降は既存の実行ロジック
    ...
```

`file_close` と `file_save` も同様のパターン:

```python
# file_close の dry-run 出力例
{
    "dry_run": True,
    "command": "file.close",
    "params": {"documentId": 1, "save": true},
    "timeout": 30.0,
    "message": "Validation passed. This command would close document 1."
}
```

**設計判断:**
- dry-run はグローバルオプションだが、読み取り操作では無視される（警告も出さない — エージェントが全コマンドに一律で付けても壊れない設計）
- バリデーションは dry-run でも実行する（dry-run の主目的がバリデーション確認のため）

---

### 2.6 P2: `psd schema <command>` サブコマンド

#### 2.6.1 `cli/schema_gen.py`（新規）

Click コマンドツリーを走査して JSON Schema を生成するユーティリティ:

```python
"""Click コマンドツリーから JSON Schema を生成する"""

from typing import Any

import click

from photoshop_sdk.schema import DocumentInfo

# コマンドごとの response schema マッピング
# Pydantic モデルから自動生成
_RESPONSE_SCHEMAS: dict[str, Any] = {
    "file.list": {
        "type": "array",
        "items": DocumentInfo.model_json_schema(),
        "description": "List of open documents",
    },
    "file.info": DocumentInfo.model_json_schema(),
    "file.open": {
        "type": "object",
        "properties": {
            "documentId": {"type": "integer", "description": "Opened document ID"},
            "name": {"type": "string", "description": "Document name"},
        },
    },
    "file.close": {
        "type": "object",
        "properties": {
            "closed": {"type": "boolean"},
        },
    },
    "file.save": {
        "type": "object",
        "properties": {
            "saved": {"type": "boolean"},
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

        if param.help:
            param_info["description"] = param.help

        enum_values = _click_type_to_enum(param.type)
        if enum_values:
            param_info["enum"] = enum_values

        if param.default is not None and param.default != ():
            param_info["default"] = param.default

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
```

#### 2.6.2 `cli/commands/schema.py`（新規）

```python
"""psd schema サブコマンド"""

import click

from cli.output import OutputFormatter
from cli.schema_gen import generate_command_schema, list_available_commands


@click.command("schema")
@click.argument("command_path", required=False)
@click.pass_context
def schema_cmd(ctx, command_path: str | None):
    """Show JSON schema for a command. Use 'psd schema' to list all commands."""
    fmt = ctx.obj.get("output", "text") if ctx.obj else "text"
    fields = ctx.obj.get("fields") if ctx.obj else None

    # ルートグループを取得
    root = ctx.find_root().command

    if command_path is None:
        # コマンド一覧を表示
        commands = list_available_commands(root)
        data = {"available_commands": commands}
        click.echo(OutputFormatter.format(data, fmt, fields=fields))
        return

    schema = generate_command_schema(command_path, root)
    if schema is None:
        click.echo(
            OutputFormatter.format_error(
                f"Unknown command: {command_path}",
                fmt,
                code="UNKNOWN_COMMAND",
                suggestions=list_available_commands(root),
            ),
            err=True,
        )
        ctx.exit(1)
        return

    click.echo(OutputFormatter.format(schema, fmt, fields=fields))
```

#### 2.6.3 `cli/main.py` への登録

```python
from cli.commands.schema import schema_cmd
cli.add_command(schema_cmd)
```

**設計判断:**
- `psd schema file.open` のようにドット記法を使用（`psd schema file open` だと Click のサブコマンド解析と競合するため）
- 引数なしで `psd schema` を実行すると利用可能なコマンド一覧を返す
- response schema は `_RESPONSE_SCHEMAS` に手動マッピングが必要だが、Pydantic の `model_json_schema()` を活用することで型情報は自動生成される
- 将来 MCP Server の tool schema 生成にも `schema_gen.py` を再利用可能

---

## 3. エラーハンドリング方針

### 3.1 exit code 体系（変更なし — 後方互換）

| Code | 意味 | 対応する例外 |
|---|---|---|
| 0 | 成功 | — |
| 1 | 一般エラー / SDK エラー | `PhotoshopSDKError`, `HandlerError` |
| 2 | 接続エラー | `ConnectionError` |
| 3 | タイムアウト | `TimeoutError` |
| 4 | バリデーションエラー | `ValidationError` |

### 3.2 JSON エラー出力の統一

全エラーは `OutputFormatter.format_error()` 経由で出力。JSON モードでは以下の構造:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "File path must not contain path traversal sequences (..)",
    "details": {
      "field": "path",
      "rule": "no_traversal"
    }
  }
}
```

`details` フィールドは `ValidationError` 固有の追加情報。既存の `format_error` に `details` パラメータを追加する:

```python
@staticmethod
def format_error(
    message: str,
    mode: str = "text",
    *,
    code: str = "ERROR",
    command: str | None = None,
    suggestions: list[str] | None = None,
    details: dict[str, Any] | None = None,  # 追加
) -> str:
```

---

## 4. テスト戦略

### 4.1 新規テストファイル

| ファイル | テスト内容 | 件数（目安） |
|---|---|---|
| `tests/unit/sdk/test_validators.py` | パスバリデーション純関数 | 10-12 |
| `tests/unit/cli/test_fields.py` | `--fields` フィルタリング | 6-8 |
| `tests/unit/cli/test_dry_run.py` | `--dry-run` の動作 | 5-6 |
| `tests/unit/cli/test_schema_cmd.py` | `psd schema` の出力 | 5-6 |

### 4.2 テストケース詳細

#### `test_validators.py`

```python
# validate_file_path
- test_valid_absolute_path           # 正常系: 存在するファイル
- test_empty_string_raises           # 空文字列 → ValidationError
- test_whitespace_only_raises        # 空白のみ → ValidationError
- test_control_chars_raises          # 制御文字含む → ValidationError
- test_null_byte_raises              # NULL バイト → ValidationError
- test_path_traversal_raises         # "../etc/passwd" → ValidationError
- test_nested_traversal_raises       # "foo/../../bar" → ValidationError
- test_file_not_found_raises         # 存在しないパス → ValidationError
- test_directory_not_file_raises     # ディレクトリ → ValidationError
- test_returns_resolved_path         # 正規化された Path が返る
- test_relative_path_resolved        # 相対パスが絶対パスに解決される
- test_tilde_expansion               # ~/file.psd が展開される（要確認）
```

#### `test_fields.py`

```python
# OutputFormatter._filter_fields
- test_filter_dict_fields            # dict から指定フィールドのみ抽出
- test_filter_list_of_dicts          # list[dict] の各要素をフィルタ
- test_filter_nonexistent_field      # 存在しないフィールド → サイレント無視
- test_filter_none_returns_all       # fields=None → フィルタなし

# CLI 統合テスト
- test_cli_fields_option_json        # psd --fields id,name --output json file list
- test_cli_fields_option_text        # psd --fields id,name --output text file list
- test_cli_fields_option_table       # psd --fields id,name --output table file list
- test_cli_fields_empty_string       # --fields "" → 全フィールド返す
```

#### `test_dry_run.py`

```python
- test_dry_run_file_open             # --dry-run で Photoshop に送信されない
- test_dry_run_file_close            # close の dry-run 出力
- test_dry_run_file_save             # save の dry-run 出力
- test_dry_run_validation_error      # バリデーション失敗は dry-run でも exit 4
- test_dry_run_list_ignored          # file list に --dry-run しても通常実行
- test_dry_run_output_json_format    # dry-run 出力の JSON 構造を検証
```

#### `test_schema_cmd.py`

```python
- test_schema_file_open              # psd schema file.open → JSON Schema
- test_schema_file_list              # psd schema file.list → response 含む
- test_schema_unknown_command        # psd schema foo.bar → エラー
- test_schema_list_all               # psd schema → コマンド一覧
- test_schema_includes_response      # response schema が含まれる
```

### 4.3 既存テストへの影響

- **既存64件は変更不要** — 新機能はすべてオプトイン（`--fields`, `--dry-run` はデフォルトで無効）
- `file_open` のバリデーション追加により、既存の `test_file_open_success` はモックパスを使っているため影響なし（バリデーションはモッククライアントの前に実行されるが、テスト内ではパスが存在しないため要調整）
  - **対応**: `test_file_open_success` で `tmp_path` fixture を使って実ファイルを作成するか、バリデーション部分をモック化する

### 4.4 テスト実行

```bash
# 全テスト実行（既存 + 新規）
python -m pytest tests/ -v

# 新規テストのみ
python -m pytest tests/unit/sdk/test_validators.py tests/unit/cli/test_fields.py tests/unit/cli/test_dry_run.py tests/unit/cli/test_schema_cmd.py -v
```

---

## 5. 実装順序

優先度と依存関係を考慮した実装順序:

| Step | 機能 | 依存先 | TDD |
|---|---|---|---|
| 1 | `photoshop_sdk/validators.py` | なし | Yes |
| 2 | `cli/commands/file.py` にバリデーション統合 | Step 1 | Yes |
| 3 | `cli/output.py` の `_filter_fields` 実装 | なし | Yes |
| 4 | `cli/main.py` に `--fields` オプション追加 | Step 3 | Yes |
| 5 | `cli/main.py` に `--dry-run` オプション追加 | Step 2 | Yes |
| 6 | `cli/commands/file.py` に dry-run 対応 | Step 5 | Yes |
| 7 | `cli/schema_gen.py` 実装 | なし | Yes |
| 8 | `cli/commands/schema.py` 実装 | Step 7 | Yes |
| 9 | SKILL.md 更新 | Step 1-8 完了後 | No |
| 10 | 全テスト実行・デグレ確認 | 全 Step | — |

---

## 6. 不確実な点・要確認事項

1. **`~` を含むパスの扱い**: `Path("~/file.psd").resolve()` は Python 3.10+ では `~` を展開しない（`expanduser()` が必要）。`validate_file_path` 内で `Path(path).expanduser().resolve()` とすべきか？
   - **推奨**: `expanduser()` を入れる。エージェントが `~/Documents/file.psd` のようなパスを渡す可能性は高い

2. **既存テスト `test_file_open_success` の修正**: バリデーション追加後、モックパス `/path/to/new.psd` が存在しないためテストが失敗する。以下の2案:
   - **案A**: テスト内で `tmp_path` を使って実ファイルを作成
   - **案B**: `validate_file_path` をモック化
   - **推奨**: 案A（実際のバリデーション動作も確認できる）

3. **`--fields` で空結果になった場合**: 全フィールドが除外された場合に `{}` を返すか、警告を出すか
   - **推奨**: `{}` をサイレントに返す（エージェントは JSON パーサブルな出力を期待している）

4. **`--dry-run` と読み取り操作の組み合わせ**: `psd --dry-run file list` はどう振る舞うか
   - **推奨**: `--dry-run` を無視して通常実行する（読み取り操作に副作用はないため）

5. **`psd schema` の response schema メンテナンス**: `_RESPONSE_SCHEMAS` は手動マッピング。新コマンド追加時に更新を忘れるリスク
   - **推奨**: テストで「全コマンドに response schema が定義されている」ことを検証する assertion を入れる

---

## 7. Phase 2 (MCP) への考慮

今回の設計で Phase 2 の MCP 実装を意識している点:

- `validators.py` は SDK 層に配置 → MCP Server からも `from photoshop_sdk.validators import validate_file_path` で呼び出し可能
- `schema_gen.py` の `generate_command_schema()` は Click 依存だが、`_RESPONSE_SCHEMAS` は独立して MCP の tool schema 生成に転用可能
- `OutputFormatter` の `_filter_fields` は MCP 側では不要（MCP は JSON 固定のため）だが、バリデーションロジックは共通化済み
- エラー構造体（`code` + `message` + `details`）は MCP のエラーレスポンスにもそのまま使える
