# Agent DX Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** エージェントが photoshop-cli を安全かつ効率的に操作できるよう、入力バリデーション・`--fields`・`--dry-run`・`psd schema`・SKILL.md 不変条件の5機能を追加する
**Architecture:** SDK層に純関数バリデータ (`validators.py`) を配置し CLI/MCP 両方から再利用。出力フィルタリングは OutputFormatter 層で実施。スキーマ生成は Click イントロスペクション + Pydantic ハイブリッド方式。
**Tech Stack:** Python 3.12, Click, Pydantic, pytest, ruff

---

## Task 1: `photoshop_sdk/validators.py` — パスバリデーション純関数

**Files:**
- Create: `photoshop_sdk/validators.py`
- Test: `tests/unit/sdk/test_validators.py`

**Step 1: 失敗するテストを書く**

`tests/unit/sdk/test_validators.py`:
```python
"""validate_file_path のユニットテスト"""

import os

import pytest

from photoshop_sdk.exceptions import ValidationError
from photoshop_sdk.validators import validate_file_path


class TestValidateFilePath:
    """validate_file_path の正常系・異常系テスト"""

    def test_valid_absolute_path(self, tmp_path):
        """正常系: 存在するファイルの絶対パスを渡すと resolved Path が返る"""
        f = tmp_path / "test.psd"
        f.write_text("dummy")
        result = validate_file_path(str(f))
        assert result == f.resolve()
        assert result.is_absolute()

    def test_returns_resolved_path(self, tmp_path):
        """正規化された Path が返る（シンボリックリンク等も解決）"""
        f = tmp_path / "test.psd"
        f.write_text("dummy")
        result = validate_file_path(str(f))
        assert result == f.resolve()

    def test_relative_path_resolved(self, tmp_path, monkeypatch):
        """相対パスが絶対パスに解決される"""
        f = tmp_path / "relative.psd"
        f.write_text("dummy")
        monkeypatch.chdir(tmp_path)
        result = validate_file_path("relative.psd")
        assert result.is_absolute()
        assert result == f.resolve()

    def test_tilde_expansion(self, tmp_path, monkeypatch):
        """~ を含むパスが expanduser で展開される"""
        f = tmp_path / "file.psd"
        f.write_text("dummy")
        monkeypatch.setenv("HOME", str(tmp_path))
        result = validate_file_path("~/file.psd")
        assert result == f.resolve()

    def test_empty_string_raises(self):
        """空文字列 → ValidationError"""
        with pytest.raises(ValidationError, match="must not be empty"):
            validate_file_path("")

    def test_whitespace_only_raises(self):
        """空白のみ → ValidationError"""
        with pytest.raises(ValidationError, match="must not be empty"):
            validate_file_path("   ")

    def test_control_chars_raises(self):
        """制御文字を含む → ValidationError"""
        with pytest.raises(ValidationError, match="control characters"):
            validate_file_path("/path/to/\x00file.psd")

    def test_null_byte_raises(self):
        """NULL バイト → ValidationError"""
        with pytest.raises(ValidationError, match="control characters"):
            validate_file_path("/path/\x00/file.psd")

    def test_tab_in_path_raises(self):
        """タブ文字 → ValidationError"""
        with pytest.raises(ValidationError, match="control characters"):
            validate_file_path("/path/to/\tfile.psd")

    def test_path_traversal_raises(self):
        """.. を含むパス → ValidationError"""
        with pytest.raises(ValidationError, match="traversal"):
            validate_file_path("../etc/passwd")

    def test_nested_traversal_raises(self):
        """ネストされた .. → ValidationError"""
        with pytest.raises(ValidationError, match="traversal"):
            validate_file_path("foo/../../bar")

    def test_file_not_found_raises(self, tmp_path):
        """存在しないパス → ValidationError"""
        nonexistent = str(tmp_path / "nonexistent.psd")
        with pytest.raises(ValidationError, match="File not found"):
            validate_file_path(nonexistent)

    def test_directory_not_file_raises(self, tmp_path):
        """ディレクトリ → ValidationError"""
        with pytest.raises(ValidationError, match="not a file"):
            validate_file_path(str(tmp_path))

    def test_error_details_contain_field_and_rule(self):
        """ValidationError の details に field と rule が含まれる"""
        with pytest.raises(ValidationError) as exc_info:
            validate_file_path("")
        assert exc_info.value.details["field"] == "path"
        assert exc_info.value.details["rule"] == "non_empty"
```

**Step 2: 失敗を確認**

Run: `python -m pytest tests/unit/sdk/test_validators.py -v`
Expected: FAIL (ModuleNotFoundError: No module named 'photoshop_sdk.validators')

**Step 3: 最小限の実装**

`photoshop_sdk/validators.py`:
```python
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
```

**Step 4: 通過を確認**

Run: `python -m pytest tests/unit/sdk/test_validators.py -v`
Expected: PASS (14 tests)

**Step 5: デグレ確認**

Run: `python -m pytest tests/ -v && python -m ruff check .`
Expected: ALL PASS

**Step 6: コミット**

```bash
git add photoshop_sdk/validators.py tests/unit/sdk/test_validators.py
git commit -m "feat: add file path validation pure functions (agent safety)"
```

---

## Task 2: `_handle_client_error` に ValidationError ケースを追加

**Files:**
- Modify: `cli/commands/file.py`
- Test: `tests/unit/cli/test_file_commands.py` (既存テストで確認)

**Step 1: 失敗するテストを書く**

`tests/unit/cli/test_file_commands.py` に追記:
```python
from photoshop_sdk.exceptions import ValidationError as PSValidationError


def test_handle_validation_error():
    """ValidationError が exit code 4 で処理される"""
    runner = CliRunner()
    mock_client = make_mock_client({
        "file_list": PSValidationError("Invalid input", code="VALIDATION_ERROR"),
    })

    with patch("cli.commands.file.PhotoshopClient", return_value=mock_client):
        result = runner.invoke(cli, ["--output", "json", "file", "list"])

    assert result.exit_code == 4
    error = json.loads(result.output)
    assert error["error"]["code"] == "VALIDATION_ERROR"
```

**Step 2: 失敗を確認**

Run: `python -m pytest tests/unit/cli/test_file_commands.py::test_handle_validation_error -v`
Expected: FAIL (exit_code == 1, not 4 -- ValidationError は PhotoshopSDKError のサブクラスなので SDK_ERROR として処理される)

**Step 3: 最小限の実装**

`cli/commands/file.py` の import と `_handle_client_error` を修正:

import セクションを以下に変更:
```python
from photoshop_sdk.exceptions import (
    ConnectionError as PSConnectionError,
    PhotoshopSDKError,
    TimeoutError as PSTimeoutError,
    ValidationError as PSValidationError,
)
```

`_handle_client_error` 関数を以下に変更:
```python
def _handle_client_error(ctx, e: Exception, fmt: str) -> None:
    """共通エラーハンドリング（exit code 付き）"""
    if isinstance(e, PSValidationError):
        click.echo(
            OutputFormatter.format_error(str(e), fmt, code="VALIDATION_ERROR"),
            err=True,
        )
        ctx.exit(4)
    elif isinstance(e, PSConnectionError):
        click.echo(
            OutputFormatter.format_error(str(e), fmt, code="CONNECTION_ERROR"),
            err=True,
        )
        ctx.exit(2)
    elif isinstance(e, PSTimeoutError):
        click.echo(
            OutputFormatter.format_error(str(e), fmt, code="TIMEOUT_ERROR"),
            err=True,
        )
        ctx.exit(3)
    elif isinstance(e, PhotoshopSDKError):
        click.echo(
            OutputFormatter.format_error(str(e), fmt, code=e.code or "SDK_ERROR"),
            err=True,
        )
        ctx.exit(1)
    else:
        click.echo(
            OutputFormatter.format_error(str(e), fmt, code="ERROR"),
            err=True,
        )
        ctx.exit(1)
```

**注意:** `PSValidationError` は `PhotoshopSDKError` のサブクラスなので、isinstance チェックの順序が重要。ValidationError を PhotoshopSDKError より **前** に置くこと。

**Step 4: 通過を確認**

Run: `python -m pytest tests/unit/cli/test_file_commands.py -v`
Expected: PASS

**Step 5: デグレ確認**

Run: `python -m pytest tests/ -v && python -m ruff check .`
Expected: ALL PASS

**Step 6: コミット**

```bash
git add cli/commands/file.py tests/unit/cli/test_file_commands.py
git commit -m "feat: handle ValidationError with exit code 4 in CLI error handler"
```

---

## Task 3: `file open` にバリデーション統合 + 既存テスト修正

**Files:**
- Modify: `cli/commands/file.py`
- Modify: `tests/unit/cli/test_file_commands.py`

**Step 1: 失敗するテストを書く**

`tests/unit/cli/test_file_commands.py` に追記:
```python
def test_file_open_validation_empty_path():
    """file open に空文字列 → exit code 4"""
    runner = CliRunner()
    result = runner.invoke(cli, ["--output", "json", "file", "open", ""])
    assert result.exit_code == 4


def test_file_open_validation_traversal():
    """file open にパストラバーサル → exit code 4"""
    runner = CliRunner()
    result = runner.invoke(cli, ["--output", "json", "file", "open", "../etc/passwd"])
    assert result.exit_code == 4


def test_file_open_validation_nonexistent():
    """file open に存在しないファイル → exit code 4"""
    runner = CliRunner()
    result = runner.invoke(cli, ["--output", "json", "file", "open", "/nonexistent/file.psd"])
    assert result.exit_code == 4


def test_file_open_with_valid_file(tmp_path):
    """file open に存在するファイル → バリデーション通過して Photoshop に送信"""
    f = tmp_path / "valid.psd"
    f.write_text("dummy")
    runner = CliRunner()
    mock_client = make_mock_client({
        "file_open": {"documentId": 3, "name": "valid.psd"}
    })

    with patch("cli.commands.file.PhotoshopClient", return_value=mock_client):
        result = runner.invoke(cli, ["--output", "json", "file", "open", str(f)])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["documentId"] == 3
```

**Step 2: 失敗を確認**

Run: `python -m pytest tests/unit/cli/test_file_commands.py::test_file_open_validation_empty_path tests/unit/cli/test_file_commands.py::test_file_open_with_valid_file -v`
Expected: FAIL (バリデーションがまだ統合されていない)

**Step 3: 最小限の実装**

`cli/commands/file.py` の `file_open` を修正:

```python
from photoshop_sdk.validators import validate_file_path

@file_cmd.command("open")
@click.argument("path")
@click.pass_context
def file_open(ctx, path: str):
    """Open a PSD file in Photoshop"""
    fmt = ctx.obj.get("output", "text") if ctx.obj else "text"
    timeout = ctx.obj.get("timeout", 30.0) if ctx.obj else 30.0

    # ローカルバリデーション（Photoshop に送信する前に検証）
    try:
        resolved = validate_file_path(path)
        path = str(resolved)
    except PSValidationError as e:
        click.echo(
            OutputFormatter.format_error(str(e), fmt, code=e.code or "VALIDATION_ERROR"),
            err=True,
        )
        ctx.exit(4)
        return

    async def _run():
        client = PhotoshopClient()
        try:
            await client.start()
            result = await client.file_open(path=path, timeout=timeout)
            click.echo(OutputFormatter.format(result, fmt))
        except Exception as e:
            _handle_client_error(ctx, e, fmt)
        finally:
            await client.stop()

    _run_async(_run())
```

**既存テスト `test_file_open_success` を修正** -- `tmp_path` で実ファイルを作成するように変更:

```python
def test_file_open_success(tmp_path):
    """file open に存在するファイル → 成功"""
    f = tmp_path / "new.psd"
    f.write_text("dummy")
    runner = CliRunner()
    mock_client = make_mock_client({
        "file_open": {"documentId": 3, "name": "new.psd"}
    })

    with patch("cli.commands.file.PhotoshopClient", return_value=mock_client):
        result = runner.invoke(cli, ["--output", "json", "file", "open", str(f)])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["documentId"] == 3
```

**Step 4: 通過を確認**

Run: `python -m pytest tests/unit/cli/test_file_commands.py -v`
Expected: PASS

**Step 5: デグレ確認**

Run: `python -m pytest tests/ -v && python -m ruff check .`
Expected: ALL PASS

**Step 6: コミット**

```bash
git add cli/commands/file.py tests/unit/cli/test_file_commands.py
git commit -m "feat: integrate file path validation into file open command"
```

---

## Task 4: `OutputFormatter._filter_fields` 実装

**Files:**
- Modify: `cli/output.py`
- Test: `tests/unit/cli/test_fields.py`

**Step 1: 失敗するテストを書く**

`tests/unit/cli/test_fields.py`:
```python
"""--fields フィルタリングのユニットテスト"""

import json
from unittest.mock import AsyncMock, patch

from click.testing import CliRunner

from cli.main import cli
from cli.output import OutputFormatter
from photoshop_sdk.schema import DocumentInfo


# --- OutputFormatter._filter_fields 単体テスト ---


class TestFilterFields:
    """OutputFormatter._filter_fields のユニットテスト"""

    def test_filter_dict_fields(self):
        """dict から指定フィールドのみ抽出"""
        data = {"id": 1, "name": "photo.psd", "width": 1920, "height": 1080}
        result = OutputFormatter._filter_fields(data, ["id", "name"])
        assert result == {"id": 1, "name": "photo.psd"}

    def test_filter_list_of_dicts(self):
        """list[dict] の各要素をフィルタ"""
        data = [
            {"id": 1, "name": "a.psd", "width": 100},
            {"id": 2, "name": "b.psd", "width": 200},
        ]
        result = OutputFormatter._filter_fields(data, ["id", "name"])
        assert result == [
            {"id": 1, "name": "a.psd"},
            {"id": 2, "name": "b.psd"},
        ]

    def test_filter_nonexistent_field(self):
        """存在しないフィールド → サイレント無視"""
        data = {"id": 1, "name": "photo.psd"}
        result = OutputFormatter._filter_fields(data, ["id", "nonexistent"])
        assert result == {"id": 1}

    def test_filter_all_excluded(self):
        """全フィールドが除外 → {} をサイレントに返す"""
        data = {"id": 1, "name": "photo.psd"}
        result = OutputFormatter._filter_fields(data, ["nonexistent"])
        assert result == {}

    def test_filter_non_dict_passthrough(self):
        """dict/list でないデータ → そのまま返す"""
        assert OutputFormatter._filter_fields("hello", ["id"]) == "hello"
        assert OutputFormatter._filter_fields(42, ["id"]) == 42

    def test_format_with_fields_json(self):
        """format() に fields を渡すとフィルタリングされる"""
        data = {"id": 1, "name": "photo.psd", "width": 1920}
        result = OutputFormatter.format(data, "json", fields=["id", "name"])
        parsed = json.loads(result)
        assert parsed == {"id": 1, "name": "photo.psd"}

    def test_format_with_fields_none(self):
        """fields=None → フィルタなし"""
        data = {"id": 1, "name": "photo.psd"}
        result = OutputFormatter.format(data, "json", fields=None)
        parsed = json.loads(result)
        assert parsed == {"id": 1, "name": "photo.psd"}


# --- CLI 統合テスト ---

MOCK_DOC_1 = DocumentInfo(documentId=1, name="photo.psd", path="/Users/test/photo.psd", width=1920, height=1080)
MOCK_DOC_2 = DocumentInfo(documentId=2, name="design.psd", path="/Users/test/design.psd", width=800, height=600)


def _make_mock_client(responses: dict):
    """PhotoshopClient のモックを作成するヘルパー"""
    mock = AsyncMock()
    mock.__aenter__ = AsyncMock(return_value=mock)
    mock.__aexit__ = AsyncMock(return_value=False)
    mock.start = AsyncMock()
    mock.stop = AsyncMock()
    for method_name, return_val in responses.items():
        if isinstance(return_val, Exception):
            getattr(mock, method_name).side_effect = return_val
        else:
            getattr(mock, method_name).return_value = return_val
    return mock


def test_cli_fields_option_json():
    """psd --fields documentId,name --output json file list"""
    runner = CliRunner()
    mock_client = _make_mock_client({"file_list": [MOCK_DOC_1, MOCK_DOC_2]})

    with patch("cli.commands.file.PhotoshopClient", return_value=mock_client):
        result = runner.invoke(cli, ["--output", "json", "--fields", "documentId,name", "file", "list"])

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert len(data) == 2
    # フィルタされたフィールドのみ
    assert set(data[0].keys()) == {"documentId", "name"}
    assert data[0]["documentId"] == 1
    assert data[0]["name"] == "photo.psd"


def test_cli_fields_option_text():
    """psd --fields documentId,name --output text file list"""
    runner = CliRunner()
    mock_client = _make_mock_client({"file_list": [MOCK_DOC_1, MOCK_DOC_2]})

    with patch("cli.commands.file.PhotoshopClient", return_value=mock_client):
        result = runner.invoke(cli, ["--output", "text", "--fields", "documentId,name", "file", "list"])

    assert result.exit_code == 0
    # text 出力にも fields が適用される（width, height が含まれない）
    assert "width" not in result.output
    assert "documentId" in result.output


def test_cli_fields_with_info():
    """psd --fields name,width --output json file info"""
    runner = CliRunner()
    mock_client = _make_mock_client({"file_info": MOCK_DOC_1})

    with patch("cli.commands.file.PhotoshopClient", return_value=mock_client):
        result = runner.invoke(cli, ["--output", "json", "--fields", "name,width", "file", "info", "--doc-id", "1"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert set(data.keys()) == {"name", "width"}
```

**Step 2: 失敗を確認**

Run: `python -m pytest tests/unit/cli/test_fields.py -v`
Expected: FAIL (AttributeError: type object 'OutputFormatter' has no attribute '_filter_fields')

**Step 3: 最小限の実装**

`cli/output.py` の `format` メソッドと `_filter_fields` を修正/追加:

`format` メソッドを以下に変更:
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
```

`_filter_fields` を追加（`_format_text` の前に配置）:
```python
@staticmethod
def _filter_fields(data: Any, fields: list[str]) -> Any:
    """指定されたフィールドのみを残す"""
    if isinstance(data, dict):
        return {k: v for k, v in data.items() if k in fields}
    elif isinstance(data, list):
        return [OutputFormatter._filter_fields(item, fields) for item in data]
    return data
```

**Step 4: 通過を確認**

Run: `python -m pytest tests/unit/cli/test_fields.py -v`
Expected: FAIL (CLI 統合テストは `--fields` オプションがまだ main.py に追加されていないため失敗する。_filter_fields 単体テストのみ PASS)

Run: `python -m pytest tests/unit/cli/test_fields.py::TestFilterFields -v`
Expected: PASS (7 tests)

**Step 5: デグレ確認**

Run: `python -m pytest tests/ -v && python -m ruff check .`
Expected: ALL PASS (既存テストは fields=None がデフォルトなので影響なし)

**Step 6: コミット**

```bash
git add cli/output.py tests/unit/cli/test_fields.py
git commit -m "feat: add _filter_fields to OutputFormatter for --fields support"
```

---

## Task 5: `cli/main.py` に `--fields` グローバルオプション追加 + 各コマンドで fields 受け渡し

**Files:**
- Modify: `cli/main.py`
- Modify: `cli/commands/file.py`

**Step 1: 失敗するテストを書く**

Task 4 で作成済みの CLI 統合テストが失敗している状態を確認:

Run: `python -m pytest tests/unit/cli/test_fields.py::test_cli_fields_option_json -v`
Expected: FAIL (Error: No such option: --fields)

**Step 2: 失敗を確認**

Run: `python -m pytest tests/unit/cli/test_fields.py::test_cli_fields_option_json -v`
Expected: FAIL

**Step 3: 最小限の実装**

`cli/main.py` を以下に変更:
```python
import logging
import os

import click


def resolve_output_format(output: str | None) -> str:
    if output is not None:
        return output
    # TTY でなければ json、TTY なら text
    import sys
    return "json" if not sys.stdout.isatty() else "text"


def resolve_timeout(timeout: float | None) -> float:
    return timeout if timeout is not None else 30.0


@click.group()
@click.version_option(version="0.1.0", prog_name="psd")
@click.option(
    "--output",
    "-o",
    type=click.Choice(["json", "text", "table"]),
    default=None,
    help="Output format (default: json for non-TTY, text for TTY)",
)
@click.option(
    "--fields",
    "-f",
    type=str,
    default=None,
    help="Comma-separated list of fields to include in output (e.g. 'id,name')",
)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.option(
    "--timeout",
    "-t",
    type=float,
    default=None,
    help="Default command timeout in seconds",
)
@click.pass_context
def cli(ctx, output, fields, verbose, timeout):
    """Adobe Photoshop CLI - control Photoshop from the command line."""
    ctx.ensure_object(dict)
    ctx.obj["output"] = resolve_output_format(output)
    ctx.obj["fields"] = [f.strip() for f in fields.split(",") if f.strip()] if fields else None
    ctx.obj["verbose"] = verbose or bool(os.environ.get("PS_VERBOSE"))
    ctx.obj["timeout"] = resolve_timeout(timeout)

    if ctx.obj["verbose"]:
        logging.basicConfig(level=logging.DEBUG, force=True)
    elif ctx.obj["output"] == "json":
        logging.basicConfig(level=logging.ERROR, force=True)
    else:
        logging.basicConfig(level=logging.WARNING, force=True)


# コマンドグループの登録
from cli.commands.file import file_cmd  # noqa: E402

cli.add_command(file_cmd)
```

`cli/commands/file.py` の各コマンドで `fields` を `OutputFormatter.format()` に渡す。

`file_list` を修正:
```python
@file_cmd.command("list")
@click.pass_context
def file_list(ctx):
    """List all open Photoshop documents"""
    fmt = ctx.obj.get("output", "text") if ctx.obj else "text"
    timeout = ctx.obj.get("timeout", 30.0) if ctx.obj else 30.0
    fields = ctx.obj.get("fields") if ctx.obj else None

    async def _run():
        client = PhotoshopClient()
        try:
            await client.start()
            docs = await client.file_list(timeout=timeout)
            data = [doc.model_dump() for doc in docs]
            click.echo(OutputFormatter.format(data, fmt, fields=fields))
        except Exception as e:
            _handle_client_error(ctx, e, fmt)
        finally:
            await client.stop()

    _run_async(_run())
```

`file_info` を修正:
```python
@file_cmd.command("info")
@click.option("--doc-id", required=True, type=int, help="Document ID")
@click.pass_context
def file_info(ctx, doc_id: int):
    """Get info for a specific document"""
    fmt = ctx.obj.get("output", "text") if ctx.obj else "text"
    timeout = ctx.obj.get("timeout", 30.0) if ctx.obj else 30.0
    fields = ctx.obj.get("fields") if ctx.obj else None

    async def _run():
        client = PhotoshopClient()
        try:
            await client.start()
            doc = await client.file_info(doc_id=doc_id, timeout=timeout)
            click.echo(OutputFormatter.format(doc.model_dump(), fmt, fields=fields))
        except Exception as e:
            _handle_client_error(ctx, e, fmt)
        finally:
            await client.stop()

    _run_async(_run())
```

`file_open` を修正 (fields 追加):
```python
@file_cmd.command("open")
@click.argument("path")
@click.pass_context
def file_open(ctx, path: str):
    """Open a PSD file in Photoshop"""
    fmt = ctx.obj.get("output", "text") if ctx.obj else "text"
    timeout = ctx.obj.get("timeout", 30.0) if ctx.obj else 30.0
    fields = ctx.obj.get("fields") if ctx.obj else None

    # ローカルバリデーション
    try:
        resolved = validate_file_path(path)
        path = str(resolved)
    except PSValidationError as e:
        click.echo(
            OutputFormatter.format_error(str(e), fmt, code=e.code or "VALIDATION_ERROR"),
            err=True,
        )
        ctx.exit(4)
        return

    async def _run():
        client = PhotoshopClient()
        try:
            await client.start()
            result = await client.file_open(path=path, timeout=timeout)
            click.echo(OutputFormatter.format(result, fmt, fields=fields))
        except Exception as e:
            _handle_client_error(ctx, e, fmt)
        finally:
            await client.stop()

    _run_async(_run())
```

`file_close` を修正:
```python
@file_cmd.command("close")
@click.option("--doc-id", required=True, type=int, help="Document ID to close")
@click.option("--save", is_flag=True, default=False, help="Save before closing")
@click.pass_context
def file_close(ctx, doc_id: int, save: bool):
    """Close a document"""
    fmt = ctx.obj.get("output", "text") if ctx.obj else "text"
    timeout = ctx.obj.get("timeout", 30.0) if ctx.obj else 30.0
    fields = ctx.obj.get("fields") if ctx.obj else None

    async def _run():
        client = PhotoshopClient()
        try:
            await client.start()
            result = await client.file_close(doc_id=doc_id, save=save, timeout=timeout)
            click.echo(OutputFormatter.format(result, fmt, fields=fields))
        except Exception as e:
            _handle_client_error(ctx, e, fmt)
        finally:
            await client.stop()

    _run_async(_run())
```

`file_save` を修正:
```python
@file_cmd.command("save")
@click.option("--doc-id", required=True, type=int, help="Document ID to save")
@click.pass_context
def file_save(ctx, doc_id: int):
    """Save a document"""
    fmt = ctx.obj.get("output", "text") if ctx.obj else "text"
    timeout = ctx.obj.get("timeout", 30.0) if ctx.obj else 30.0
    fields = ctx.obj.get("fields") if ctx.obj else None

    async def _run():
        client = PhotoshopClient()
        try:
            await client.start()
            result = await client.file_save(doc_id=doc_id, timeout=timeout)
            click.echo(OutputFormatter.format(result, fmt, fields=fields))
        except Exception as e:
            _handle_client_error(ctx, e, fmt)
        finally:
            await client.stop()

    _run_async(_run())
```

**Step 4: 通過を確認**

Run: `python -m pytest tests/unit/cli/test_fields.py -v`
Expected: PASS (全テスト)

**Step 5: デグレ確認**

Run: `python -m pytest tests/ -v && python -m ruff check .`
Expected: ALL PASS

**Step 6: コミット**

```bash
git add cli/main.py cli/commands/file.py
git commit -m "feat: add --fields global option for output field filtering"
```

---

## Task 6: `--dry-run` グローバルオプション + 変更コマンド対応

**Files:**
- Modify: `cli/main.py`
- Modify: `cli/commands/file.py`
- Test: `tests/unit/cli/test_dry_run.py`

**Step 1: 失敗するテストを書く**

`tests/unit/cli/test_dry_run.py`:
```python
"""--dry-run のユニットテスト"""

import json
from unittest.mock import AsyncMock, patch

from click.testing import CliRunner

from cli.main import cli
from photoshop_sdk.schema import DocumentInfo

MOCK_DOC_1 = DocumentInfo(documentId=1, name="photo.psd", path="/Users/test/photo.psd", width=1920, height=1080)


def _make_mock_client(responses: dict):
    """PhotoshopClient のモックを作成するヘルパー"""
    mock = AsyncMock()
    mock.__aenter__ = AsyncMock(return_value=mock)
    mock.__aexit__ = AsyncMock(return_value=False)
    mock.start = AsyncMock()
    mock.stop = AsyncMock()
    for method_name, return_val in responses.items():
        if isinstance(return_val, Exception):
            getattr(mock, method_name).side_effect = return_val
        else:
            getattr(mock, method_name).return_value = return_val
    return mock


def test_dry_run_file_open(tmp_path):
    """--dry-run で file open → Photoshop に送信されず dry_run 出力が返る"""
    f = tmp_path / "test.psd"
    f.write_text("dummy")
    runner = CliRunner()
    mock_client = _make_mock_client({"file_open": {"documentId": 1, "name": "test.psd"}})

    with patch("cli.commands.file.PhotoshopClient", return_value=mock_client):
        result = runner.invoke(cli, ["--output", "json", "--dry-run", "file", "open", str(f)])

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["dry_run"] is True
    assert data["command"] == "file.open"
    assert "path" in data["params"]
    # PhotoshopClient.file_open が呼ばれていないことを確認
    mock_client.file_open.assert_not_called()


def test_dry_run_file_close():
    """--dry-run で file close → dry_run 出力"""
    runner = CliRunner()
    mock_client = _make_mock_client({"file_close": {"closed": True}})

    with patch("cli.commands.file.PhotoshopClient", return_value=mock_client):
        result = runner.invoke(cli, ["--output", "json", "--dry-run", "file", "close", "--doc-id", "1"])

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["dry_run"] is True
    assert data["command"] == "file.close"
    assert data["params"]["doc_id"] == 1
    mock_client.file_close.assert_not_called()


def test_dry_run_file_save():
    """--dry-run で file save → dry_run 出力"""
    runner = CliRunner()
    mock_client = _make_mock_client({"file_save": {"saved": True}})

    with patch("cli.commands.file.PhotoshopClient", return_value=mock_client):
        result = runner.invoke(cli, ["--output", "json", "--dry-run", "file", "save", "--doc-id", "1"])

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["dry_run"] is True
    assert data["command"] == "file.save"
    mock_client.file_save.assert_not_called()


def test_dry_run_validation_error():
    """--dry-run でもバリデーション失敗は exit 4"""
    runner = CliRunner()
    result = runner.invoke(cli, ["--output", "json", "--dry-run", "file", "open", "../etc/passwd"])
    assert result.exit_code == 4


def test_dry_run_list_ignored():
    """file list に --dry-run しても通常実行される（読み取り操作なので無視）"""
    runner = CliRunner()
    mock_client = _make_mock_client({"file_list": [MOCK_DOC_1]})

    with patch("cli.commands.file.PhotoshopClient", return_value=mock_client):
        result = runner.invoke(cli, ["--output", "json", "--dry-run", "file", "list"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    # dry_run 出力ではなく、通常のドキュメントリストが返る
    assert isinstance(data, list)
    assert data[0]["name"] == "photo.psd"


def test_dry_run_info_ignored():
    """file info に --dry-run しても通常実行される"""
    runner = CliRunner()
    mock_client = _make_mock_client({"file_info": MOCK_DOC_1})

    with patch("cli.commands.file.PhotoshopClient", return_value=mock_client):
        result = runner.invoke(cli, ["--output", "json", "--dry-run", "file", "info", "--doc-id", "1"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["name"] == "photo.psd"


def test_dry_run_output_json_format(tmp_path):
    """dry-run 出力の JSON 構造を検証"""
    f = tmp_path / "test.psd"
    f.write_text("dummy")
    runner = CliRunner()

    with patch("cli.commands.file.PhotoshopClient", return_value=_make_mock_client({})):
        result = runner.invoke(cli, ["--output", "json", "--dry-run", "file", "open", str(f)])

    assert result.exit_code == 0
    data = json.loads(result.output)
    # 必須フィールドの検証
    assert "dry_run" in data
    assert "command" in data
    assert "params" in data
    assert "timeout" in data
    assert "message" in data
```

**Step 2: 失敗を確認**

Run: `python -m pytest tests/unit/cli/test_dry_run.py -v`
Expected: FAIL (Error: No such option: --dry-run)

**Step 3: 最小限の実装**

`cli/main.py` に `--dry-run` オプションを追加:

`@click.option("--timeout", ...)` の後に追加:
```python
@click.option("--dry-run", is_flag=True, default=False,
              help="Validate inputs and show the command that would be sent, without executing")
```

`cli` 関数のシグネチャを変更:
```python
def cli(ctx, output, fields, verbose, timeout, dry_run):
```

`ctx.obj` に追加:
```python
ctx.obj["dry_run"] = dry_run
```

`cli/commands/file.py` の変更コマンドに dry-run 対応を追加:

`file_open` に dry-run 対応を追加（バリデーション後、`_run()` の前）:
```python
    dry_run = ctx.obj.get("dry_run", False) if ctx.obj else False

    # ... バリデーション ...

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
```

`file_close` に dry-run 対応を追加:
```python
    dry_run = ctx.obj.get("dry_run", False) if ctx.obj else False
    fields = ctx.obj.get("fields") if ctx.obj else None

    if dry_run:
        dry_run_output = {
            "dry_run": True,
            "command": "file.close",
            "params": {"doc_id": doc_id, "save": save},
            "timeout": timeout,
            "message": f"Validation passed. This command would close document {doc_id}.",
        }
        click.echo(OutputFormatter.format(dry_run_output, fmt, fields=fields))
        return
```

`file_save` に dry-run 対応を追加:
```python
    dry_run = ctx.obj.get("dry_run", False) if ctx.obj else False
    fields = ctx.obj.get("fields") if ctx.obj else None

    if dry_run:
        dry_run_output = {
            "dry_run": True,
            "command": "file.save",
            "params": {"doc_id": doc_id},
            "timeout": timeout,
            "message": f"Validation passed. This command would save document {doc_id}.",
        }
        click.echo(OutputFormatter.format(dry_run_output, fmt, fields=fields))
        return
```

`file_list` と `file_info` は dry-run を無視する（変更不要 -- 読み取り操作なのでそのまま実行）。

完全な `cli/commands/file.py`:
```python
"""psd file サブコマンド群（open / close / save / info / list）"""

import asyncio
import logging

import click

from cli.output import OutputFormatter
from photoshop_sdk.client import PhotoshopClient
from photoshop_sdk.exceptions import (
    ConnectionError as PSConnectionError,
    PhotoshopSDKError,
    TimeoutError as PSTimeoutError,
    ValidationError as PSValidationError,
)
from photoshop_sdk.validators import validate_file_path

logger = logging.getLogger(__name__)


def _run_async(coro):
    """CLI から async 関数を実行するヘルパー"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _handle_client_error(ctx, e: Exception, fmt: str) -> None:
    """共通エラーハンドリング（exit code 付き）"""
    if isinstance(e, PSValidationError):
        click.echo(
            OutputFormatter.format_error(str(e), fmt, code="VALIDATION_ERROR"),
            err=True,
        )
        ctx.exit(4)
    elif isinstance(e, PSConnectionError):
        click.echo(
            OutputFormatter.format_error(str(e), fmt, code="CONNECTION_ERROR"),
            err=True,
        )
        ctx.exit(2)
    elif isinstance(e, PSTimeoutError):
        click.echo(
            OutputFormatter.format_error(str(e), fmt, code="TIMEOUT_ERROR"),
            err=True,
        )
        ctx.exit(3)
    elif isinstance(e, PhotoshopSDKError):
        click.echo(
            OutputFormatter.format_error(str(e), fmt, code=e.code or "SDK_ERROR"),
            err=True,
        )
        ctx.exit(1)
    else:
        click.echo(
            OutputFormatter.format_error(str(e), fmt, code="ERROR"),
            err=True,
        )
        ctx.exit(1)


@click.group(name="file")
def file_cmd():
    """File operations (open, close, save, info, list)"""
    pass


@file_cmd.command("list")
@click.pass_context
def file_list(ctx):
    """List all open Photoshop documents"""
    fmt = ctx.obj.get("output", "text") if ctx.obj else "text"
    timeout = ctx.obj.get("timeout", 30.0) if ctx.obj else 30.0
    fields = ctx.obj.get("fields") if ctx.obj else None

    async def _run():
        client = PhotoshopClient()
        try:
            await client.start()
            docs = await client.file_list(timeout=timeout)
            data = [doc.model_dump() for doc in docs]
            click.echo(OutputFormatter.format(data, fmt, fields=fields))
        except Exception as e:
            _handle_client_error(ctx, e, fmt)
        finally:
            await client.stop()

    _run_async(_run())


@file_cmd.command("info")
@click.option("--doc-id", required=True, type=int, help="Document ID")
@click.pass_context
def file_info(ctx, doc_id: int):
    """Get info for a specific document"""
    fmt = ctx.obj.get("output", "text") if ctx.obj else "text"
    timeout = ctx.obj.get("timeout", 30.0) if ctx.obj else 30.0
    fields = ctx.obj.get("fields") if ctx.obj else None

    async def _run():
        client = PhotoshopClient()
        try:
            await client.start()
            doc = await client.file_info(doc_id=doc_id, timeout=timeout)
            click.echo(OutputFormatter.format(doc.model_dump(), fmt, fields=fields))
        except Exception as e:
            _handle_client_error(ctx, e, fmt)
        finally:
            await client.stop()

    _run_async(_run())


@file_cmd.command("open")
@click.argument("path")
@click.pass_context
def file_open(ctx, path: str):
    """Open a PSD file in Photoshop"""
    fmt = ctx.obj.get("output", "text") if ctx.obj else "text"
    timeout = ctx.obj.get("timeout", 30.0) if ctx.obj else 30.0
    fields = ctx.obj.get("fields") if ctx.obj else None
    dry_run = ctx.obj.get("dry_run", False) if ctx.obj else False

    # ローカルバリデーション（Photoshop に送信する前に検証）
    try:
        resolved = validate_file_path(path)
        path = str(resolved)
    except PSValidationError as e:
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

    async def _run():
        client = PhotoshopClient()
        try:
            await client.start()
            result = await client.file_open(path=path, timeout=timeout)
            click.echo(OutputFormatter.format(result, fmt, fields=fields))
        except Exception as e:
            _handle_client_error(ctx, e, fmt)
        finally:
            await client.stop()

    _run_async(_run())


@file_cmd.command("close")
@click.option("--doc-id", required=True, type=int, help="Document ID to close")
@click.option("--save", is_flag=True, default=False, help="Save before closing")
@click.pass_context
def file_close(ctx, doc_id: int, save: bool):
    """Close a document"""
    fmt = ctx.obj.get("output", "text") if ctx.obj else "text"
    timeout = ctx.obj.get("timeout", 30.0) if ctx.obj else 30.0
    fields = ctx.obj.get("fields") if ctx.obj else None
    dry_run = ctx.obj.get("dry_run", False) if ctx.obj else False

    if dry_run:
        dry_run_output = {
            "dry_run": True,
            "command": "file.close",
            "params": {"doc_id": doc_id, "save": save},
            "timeout": timeout,
            "message": f"Validation passed. This command would close document {doc_id}.",
        }
        click.echo(OutputFormatter.format(dry_run_output, fmt, fields=fields))
        return

    async def _run():
        client = PhotoshopClient()
        try:
            await client.start()
            result = await client.file_close(doc_id=doc_id, save=save, timeout=timeout)
            click.echo(OutputFormatter.format(result, fmt, fields=fields))
        except Exception as e:
            _handle_client_error(ctx, e, fmt)
        finally:
            await client.stop()

    _run_async(_run())


@file_cmd.command("save")
@click.option("--doc-id", required=True, type=int, help="Document ID to save")
@click.pass_context
def file_save(ctx, doc_id: int):
    """Save a document"""
    fmt = ctx.obj.get("output", "text") if ctx.obj else "text"
    timeout = ctx.obj.get("timeout", 30.0) if ctx.obj else 30.0
    fields = ctx.obj.get("fields") if ctx.obj else None
    dry_run = ctx.obj.get("dry_run", False) if ctx.obj else False

    if dry_run:
        dry_run_output = {
            "dry_run": True,
            "command": "file.save",
            "params": {"doc_id": doc_id},
            "timeout": timeout,
            "message": f"Validation passed. This command would save document {doc_id}.",
        }
        click.echo(OutputFormatter.format(dry_run_output, fmt, fields=fields))
        return

    async def _run():
        client = PhotoshopClient()
        try:
            await client.start()
            result = await client.file_save(doc_id=doc_id, timeout=timeout)
            click.echo(OutputFormatter.format(result, fmt, fields=fields))
        except Exception as e:
            _handle_client_error(ctx, e, fmt)
        finally:
            await client.stop()

    _run_async(_run())
```

完全な `cli/main.py`:
```python
import logging
import os

import click


def resolve_output_format(output: str | None) -> str:
    if output is not None:
        return output
    # TTY でなければ json、TTY なら text
    import sys
    return "json" if not sys.stdout.isatty() else "text"


def resolve_timeout(timeout: float | None) -> float:
    return timeout if timeout is not None else 30.0


@click.group()
@click.version_option(version="0.1.0", prog_name="psd")
@click.option(
    "--output",
    "-o",
    type=click.Choice(["json", "text", "table"]),
    default=None,
    help="Output format (default: json for non-TTY, text for TTY)",
)
@click.option(
    "--fields",
    "-f",
    type=str,
    default=None,
    help="Comma-separated list of fields to include in output (e.g. 'id,name')",
)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.option(
    "--timeout",
    "-t",
    type=float,
    default=None,
    help="Default command timeout in seconds",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Validate inputs and show the command that would be sent, without executing",
)
@click.pass_context
def cli(ctx, output, fields, verbose, timeout, dry_run):
    """Adobe Photoshop CLI - control Photoshop from the command line."""
    ctx.ensure_object(dict)
    ctx.obj["output"] = resolve_output_format(output)
    ctx.obj["fields"] = [f.strip() for f in fields.split(",") if f.strip()] if fields else None
    ctx.obj["verbose"] = verbose or bool(os.environ.get("PS_VERBOSE"))
    ctx.obj["timeout"] = resolve_timeout(timeout)
    ctx.obj["dry_run"] = dry_run

    if ctx.obj["verbose"]:
        logging.basicConfig(level=logging.DEBUG, force=True)
    elif ctx.obj["output"] == "json":
        logging.basicConfig(level=logging.ERROR, force=True)
    else:
        logging.basicConfig(level=logging.WARNING, force=True)


# コマンドグループの登録
from cli.commands.file import file_cmd  # noqa: E402

cli.add_command(file_cmd)
```

**Step 4: 通過を確認**

Run: `python -m pytest tests/unit/cli/test_dry_run.py -v`
Expected: PASS (8 tests)

**Step 5: デグレ確認**

Run: `python -m pytest tests/ -v && python -m ruff check .`
Expected: ALL PASS

**Step 6: コミット**

```bash
git add cli/main.py cli/commands/file.py tests/unit/cli/test_dry_run.py
git commit -m "feat: add --dry-run global option for write operations (agent safety)"
```

---

## Task 7: `cli/schema_gen.py` — Click → JSON Schema 変換ロジック

**Files:**
- Create: `cli/schema_gen.py`
- Test: `tests/unit/cli/test_schema_cmd.py` (schema_gen の単体テストも含む)

**Step 1: 失敗するテストを書く**

`tests/unit/cli/test_schema_cmd.py`:
```python
"""psd schema サブコマンドのユニットテスト"""

import json

from click.testing import CliRunner

from cli.main import cli
from cli.schema_gen import generate_command_schema, list_available_commands


class TestSchemaGen:
    """schema_gen モジュールの単体テスト"""

    def test_generate_file_open_schema(self):
        """file.open のスキーマが生成される"""
        schema = generate_command_schema("file.open", cli)
        assert schema is not None
        assert schema["title"] == "file.open"
        assert "params" in schema["properties"]
        params = schema["properties"]["params"]
        assert "path" in params["properties"]
        assert params["properties"]["path"]["_cli_type"] == "argument"

    def test_generate_file_list_schema(self):
        """file.list のスキーマが生成される"""
        schema = generate_command_schema("file.list", cli)
        assert schema is not None
        assert schema["title"] == "file.list"

    def test_generate_file_info_schema(self):
        """file.info のスキーマが生成される"""
        schema = generate_command_schema("file.info", cli)
        assert schema is not None
        assert "doc_id" in schema["properties"]["params"]["properties"]

    def test_generate_unknown_command_returns_none(self):
        """存在しないコマンド → None"""
        schema = generate_command_schema("foo.bar", cli)
        assert schema is None

    def test_response_schema_included(self):
        """response schema が定義済みコマンドに含まれる"""
        schema = generate_command_schema("file.list", cli)
        assert schema is not None
        assert "response" in schema

    def test_response_schema_for_file_open(self):
        """file.open の response schema が含まれる"""
        schema = generate_command_schema("file.open", cli)
        assert schema is not None
        assert "response" in schema

    def test_list_available_commands(self):
        """利用可能なコマンド一覧が返る"""
        commands = list_available_commands(cli)
        assert "file.list" in commands
        assert "file.open" in commands
        assert "file.close" in commands
        assert "file.save" in commands
        assert "file.info" in commands

    def test_list_includes_schema_command(self):
        """schema コマンド自体もリストに含まれる"""
        commands = list_available_commands(cli)
        assert "schema" in commands

    def test_all_commands_have_response_schema(self):
        """全コマンドに response schema が定義されている"""
        from cli.schema_gen import _RESPONSE_SCHEMAS

        commands = list_available_commands(cli)
        # schema コマンド自体は response schema 不要
        file_commands = [c for c in commands if c.startswith("file.")]
        for cmd in file_commands:
            assert cmd in _RESPONSE_SCHEMAS, f"Missing response schema for {cmd}"


class TestSchemaCommand:
    """psd schema サブコマンドの CLI 統合テスト"""

    def test_schema_file_open(self):
        """psd schema file.open → JSON Schema が返る"""
        runner = CliRunner()
        result = runner.invoke(cli, ["--output", "json", "schema", "file.open"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["title"] == "file.open"
        assert "$schema" in data

    def test_schema_file_list_with_response(self):
        """psd schema file.list → response schema 含む"""
        runner = CliRunner()
        result = runner.invoke(cli, ["--output", "json", "schema", "file.list"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "response" in data

    def test_schema_unknown_command(self):
        """psd schema foo.bar → エラー"""
        runner = CliRunner()
        result = runner.invoke(cli, ["--output", "json", "schema", "foo.bar"])
        assert result.exit_code == 1
        error = json.loads(result.output)
        assert error["error"]["code"] == "UNKNOWN_COMMAND"

    def test_schema_list_all(self):
        """psd schema (引数なし) → コマンド一覧"""
        runner = CliRunner()
        result = runner.invoke(cli, ["--output", "json", "schema"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "available_commands" in data
        assert "file.open" in data["available_commands"]

    def test_schema_with_fields(self):
        """psd --fields title schema file.open → title フィールドのみ"""
        runner = CliRunner()
        result = runner.invoke(cli, ["--output", "json", "--fields", "title", "schema", "file.open"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "title" in data
        assert "properties" not in data
```

**Step 2: 失敗を確認**

Run: `python -m pytest tests/unit/cli/test_schema_cmd.py -v`
Expected: FAIL (ModuleNotFoundError: No module named 'cli.schema_gen')

**Step 3: 最小限の実装**

`cli/schema_gen.py`:
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

**Step 4: 通過を確認**

Run: `python -m pytest tests/unit/cli/test_schema_cmd.py::TestSchemaGen -v`
Expected: PASS (schema_gen 単体テスト)

CLI 統合テストは schema コマンドがまだ登録されていないため FAIL:

Run: `python -m pytest tests/unit/cli/test_schema_cmd.py::TestSchemaCommand -v`
Expected: FAIL (Usage: psd [OPTIONS] COMMAND -- schema は未登録)

**Step 5: デグレ確認**

Run: `python -m pytest tests/ -v && python -m ruff check .`
Expected: ALL PASS (CLI 統合テスト以外)

**Step 6: コミット**

```bash
git add cli/schema_gen.py tests/unit/cli/test_schema_cmd.py
git commit -m "feat: add schema generation from Click command tree + Pydantic models"
```

---

## Task 8: `cli/commands/schema.py` + main.py 登録

**Files:**
- Create: `cli/commands/schema.py`
- Modify: `cli/main.py`

**Step 1: 失敗するテストを書く**

Task 7 で作成済みの `TestSchemaCommand` が失敗している状態を確認。

Run: `python -m pytest tests/unit/cli/test_schema_cmd.py::TestSchemaCommand -v`
Expected: FAIL

**Step 2: 失敗を確認**

Run: `python -m pytest tests/unit/cli/test_schema_cmd.py::TestSchemaCommand::test_schema_file_open -v`
Expected: FAIL

**Step 3: 最小限の実装**

`cli/commands/schema.py`:
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

`cli/main.py` に schema コマンドを登録（末尾に追加）:

```python
from cli.commands.schema import schema_cmd  # noqa: E402

cli.add_command(schema_cmd)
```

完全な `cli/main.py`:
```python
import logging
import os

import click


def resolve_output_format(output: str | None) -> str:
    if output is not None:
        return output
    # TTY でなければ json、TTY なら text
    import sys
    return "json" if not sys.stdout.isatty() else "text"


def resolve_timeout(timeout: float | None) -> float:
    return timeout if timeout is not None else 30.0


@click.group()
@click.version_option(version="0.1.0", prog_name="psd")
@click.option(
    "--output",
    "-o",
    type=click.Choice(["json", "text", "table"]),
    default=None,
    help="Output format (default: json for non-TTY, text for TTY)",
)
@click.option(
    "--fields",
    "-f",
    type=str,
    default=None,
    help="Comma-separated list of fields to include in output (e.g. 'id,name')",
)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
@click.option(
    "--timeout",
    "-t",
    type=float,
    default=None,
    help="Default command timeout in seconds",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Validate inputs and show the command that would be sent, without executing",
)
@click.pass_context
def cli(ctx, output, fields, verbose, timeout, dry_run):
    """Adobe Photoshop CLI - control Photoshop from the command line."""
    ctx.ensure_object(dict)
    ctx.obj["output"] = resolve_output_format(output)
    ctx.obj["fields"] = [f.strip() for f in fields.split(",") if f.strip()] if fields else None
    ctx.obj["verbose"] = verbose or bool(os.environ.get("PS_VERBOSE"))
    ctx.obj["timeout"] = resolve_timeout(timeout)
    ctx.obj["dry_run"] = dry_run

    if ctx.obj["verbose"]:
        logging.basicConfig(level=logging.DEBUG, force=True)
    elif ctx.obj["output"] == "json":
        logging.basicConfig(level=logging.ERROR, force=True)
    else:
        logging.basicConfig(level=logging.WARNING, force=True)


# コマンドグループの登録
from cli.commands.file import file_cmd  # noqa: E402
from cli.commands.schema import schema_cmd  # noqa: E402

cli.add_command(file_cmd)
cli.add_command(schema_cmd)
```

**Step 4: 通過を確認**

Run: `python -m pytest tests/unit/cli/test_schema_cmd.py -v`
Expected: PASS (全テスト)

**Step 5: デグレ確認**

Run: `python -m pytest tests/ -v && python -m ruff check .`
Expected: ALL PASS

**Step 6: コミット**

```bash
git add cli/commands/schema.py cli/main.py
git commit -m "feat: add psd schema command for agent introspection"
```

---

## Task 9: `OutputFormatter.format_error` に `details` パラメータ追加

**Files:**
- Modify: `cli/output.py`
- Test: `tests/unit/cli/test_output.py` (既存テストに追記)

**Step 1: 失敗するテストを書く**

`tests/unit/cli/test_output.py` に追記:
```python
def test_format_error_with_details_json():
    """format_error に details を渡すと JSON 出力に含まれる"""
    result = OutputFormatter.format_error(
        "Validation failed",
        "json",
        code="VALIDATION_ERROR",
        details={"field": "path", "rule": "non_empty"},
    )
    data = json.loads(result)
    assert data["error"]["details"]["field"] == "path"
    assert data["error"]["details"]["rule"] == "non_empty"


def test_format_error_without_details_json():
    """details なしの場合は details キーが含まれない"""
    result = OutputFormatter.format_error("Some error", "json", code="ERROR")
    data = json.loads(result)
    assert "details" not in data["error"]
```

**Step 2: 失敗を確認**

Run: `python -m pytest tests/unit/cli/test_output.py::test_format_error_with_details_json -v`
Expected: FAIL (TypeError: format_error() got an unexpected keyword argument 'details')

**Step 3: 最小限の実装**

`cli/output.py` の `format_error` メソッドを修正:
```python
@staticmethod
def format_error(
    message: str,
    mode: str = "text",
    *,
    code: str = "ERROR",
    command: str | None = None,
    suggestions: list[str] | None = None,
    details: dict[str, Any] | None = None,
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
        if details:
            error_obj["details"] = details
        return json.dumps({"error": error_obj})
    return f"Error: {message}"
```

**Step 4: 通過を確認**

Run: `python -m pytest tests/unit/cli/test_output.py -v`
Expected: PASS

**Step 5: デグレ確認**

Run: `python -m pytest tests/ -v && python -m ruff check .`
Expected: ALL PASS

**Step 6: コミット**

```bash
git add cli/output.py tests/unit/cli/test_output.py
git commit -m "feat: add details parameter to format_error for structured validation errors"
```

---

## Task 10: SKILL.md にエージェント不変条件セクション追加

**Files:**
- Modify: `plugin/skills/photoshop-cli/SKILL.md`

**Step 1: SKILL.md の末尾に追加**

`plugin/skills/photoshop-cli/SKILL.md` の末尾に以下を追加:

```markdown

## エージェント不変条件（Agent Invariants）

以下のルールは **必ず** 遵守すること。違反するとデータ損失やユーザーの信頼を損なう。

### 1. 変更操作の前にユーザー確認を取る

`file open`, `file close`, `file save` は Photoshop の状態を変更する。
実行前に必ずユーザーに確認を取ること。

```
NG: psd file close --doc-id 1
OK: 「Document 1 (photo.psd) を閉じてもよいですか？」→ 承認後に実行
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

# 全コマンド一覧
psd --output json schema
```
```

**Step 2: コミット**

```bash
git add plugin/skills/photoshop-cli/SKILL.md
git commit -m "docs: add agent invariants section to SKILL.md"
```

---

## Task 11: 全テスト実行・デグレ確認

**Step 1: 全テスト + lint 実行**

Run: `python -m pytest tests/ -v && python -m ruff check .`
Expected: ALL PASS, 0 lint errors

**Step 2: テスト件数確認**

期待されるテスト件数:
- 既存: 64 tests
- 新規 test_validators.py: 14 tests
- 新規 test_fields.py: 10 tests (7 unit + 3 CLI integration)
- 新規 test_dry_run.py: 8 tests
- 新規 test_schema_cmd.py: 14 tests (9 unit + 5 CLI integration)
- 既存 test_file_commands.py 追加分: 4 tests
- 既存 test_output.py 追加分: 2 tests
- **合計: 約 116 tests**

**Step 3: 最終確認**

Run: `python -m pytest tests/ -v --tb=short`
Expected: ALL PASS

---

## 実装順序のサマリー

| Task | 内容 | 新規ファイル | 修正ファイル |
|------|------|-------------|-------------|
| 1 | パスバリデーション純関数 | `photoshop_sdk/validators.py`, `tests/unit/sdk/test_validators.py` | - |
| 2 | ValidationError ハンドリング | - | `cli/commands/file.py`, `tests/unit/cli/test_file_commands.py` |
| 3 | file open にバリデーション統合 | - | `cli/commands/file.py`, `tests/unit/cli/test_file_commands.py` |
| 4 | OutputFormatter._filter_fields | `tests/unit/cli/test_fields.py` | `cli/output.py` |
| 5 | --fields グローバルオプション | - | `cli/main.py`, `cli/commands/file.py` |
| 6 | --dry-run グローバルオプション | `tests/unit/cli/test_dry_run.py` | `cli/main.py`, `cli/commands/file.py` |
| 7 | schema_gen モジュール | `cli/schema_gen.py`, `tests/unit/cli/test_schema_cmd.py` | - |
| 8 | schema コマンド登録 | `cli/commands/schema.py` | `cli/main.py` |
| 9 | format_error に details 追加 | - | `cli/output.py`, `tests/unit/cli/test_output.py` |
| 10 | SKILL.md 更新 | - | `plugin/skills/photoshop-cli/SKILL.md` |
| 11 | 全テスト・デグレ確認 | - | - |
