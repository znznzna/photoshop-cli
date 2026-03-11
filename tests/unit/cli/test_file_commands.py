import json
from unittest.mock import AsyncMock, patch

from click.testing import CliRunner

from cli.main import cli
from photoshop_sdk.exceptions import ConnectionError as PSConnectionError, ValidationError as PSValidationError
from photoshop_sdk.schema import DocumentInfo

# テスト用のモックドキュメント
MOCK_DOC_1 = DocumentInfo(documentId=1, name="photo.psd", path="/Users/test/photo.psd", width=1920, height=1080)
MOCK_DOC_2 = DocumentInfo(documentId=2, name="design.psd", path="/Users/test/design.psd", width=800, height=600)


def make_mock_client(responses: dict):
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


def test_file_list_success():
    runner = CliRunner()
    mock_client = make_mock_client({"file_list": [MOCK_DOC_1, MOCK_DOC_2]})

    with patch("cli.commands.file.PhotoshopClient", return_value=mock_client):
        result = runner.invoke(cli, ["--output", "json", "file", "list"])

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert len(data) == 2
    assert data[0]["name"] == "photo.psd"
    assert data[1]["name"] == "design.psd"


def test_file_list_empty():
    runner = CliRunner()
    mock_client = make_mock_client({"file_list": []})

    with patch("cli.commands.file.PhotoshopClient", return_value=mock_client):
        result = runner.invoke(cli, ["--output", "json", "file", "list"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data == []


def test_file_list_connection_error():
    runner = CliRunner()
    mock_client = make_mock_client({"file_list": PSConnectionError("Plugin not connected")})

    with patch("cli.commands.file.PhotoshopClient", return_value=mock_client):
        result = runner.invoke(cli, ["--output", "json", "file", "list"])

    assert result.exit_code == 2  # CONNECTION_ERROR exit code
    error = json.loads(result.output)
    assert error["error"]["code"] == "CONNECTION_ERROR"


def test_file_info_success():
    runner = CliRunner()
    mock_client = make_mock_client({"file_info": MOCK_DOC_1})

    with patch("cli.commands.file.PhotoshopClient", return_value=mock_client):
        result = runner.invoke(cli, ["--output", "json", "file", "info", "--doc-id", "1"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["documentId"] == 1
    assert data["name"] == "photo.psd"
    assert data["width"] == 1920


def test_file_info_missing_doc_id():
    runner = CliRunner()
    result = runner.invoke(cli, ["file", "info"])
    assert result.exit_code != 0


def test_file_open_success(tmp_path):
    """file open に存在するファイル → 成功"""
    f = tmp_path / "new.psd"
    f.write_text("dummy")
    runner = CliRunner()
    mock_client = make_mock_client({"file_open": {"documentId": 3, "name": "new.psd"}})

    with patch("cli.commands.file.PhotoshopClient", return_value=mock_client):
        result = runner.invoke(cli, ["--output", "json", "file", "open", str(f)])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["documentId"] == 3


def test_file_open_missing_path():
    runner = CliRunner()
    result = runner.invoke(cli, ["file", "open"])
    assert result.exit_code != 0


def test_file_close_success():
    runner = CliRunner()
    mock_client = make_mock_client({"file_close": {"closed": True}})

    with patch("cli.commands.file.PhotoshopClient", return_value=mock_client):
        result = runner.invoke(cli, ["--output", "json", "file", "close", "--doc-id", "1"])

    assert result.exit_code == 0


def test_file_save_success():
    runner = CliRunner()
    mock_client = make_mock_client({"file_save": {"saved": True}})

    with patch("cli.commands.file.PhotoshopClient", return_value=mock_client):
        result = runner.invoke(cli, ["--output", "json", "file", "save", "--doc-id", "1"])

    assert result.exit_code == 0


def test_handle_validation_error():
    """ValidationError が exit code 4 で処理される"""
    runner = CliRunner()
    mock_client = make_mock_client(
        {
            "file_list": PSValidationError("Invalid input", code="VALIDATION_ERROR"),
        }
    )

    with patch("cli.commands.file.PhotoshopClient", return_value=mock_client):
        result = runner.invoke(cli, ["--output", "json", "file", "list"])

    assert result.exit_code == 4
    error = json.loads(result.output)
    assert error["error"]["code"] == "VALIDATION_ERROR"


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
    mock_client = make_mock_client({"file_open": {"documentId": 3, "name": "valid.psd"}})

    with patch("cli.commands.file.PhotoshopClient", return_value=mock_client):
        result = runner.invoke(cli, ["--output", "json", "file", "open", str(f)])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["documentId"] == 3
