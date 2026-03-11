"""file / document コマンドのユニットテスト

file.py と document.py は auto_commands ベースで自動生成されるため、
ConnectionManager.execute をモックしてテストする。
"""

import json
from unittest.mock import AsyncMock, patch

from click.testing import CliRunner

from cli.main import cli


def _mock_cm(return_value):
    """ConnectionManager のモックを作成するヘルパー"""
    mock = AsyncMock()
    mock.execute = AsyncMock(return_value=return_value)
    return mock


# ============================================================
# file list
# ============================================================


def test_file_list_success():
    runner = CliRunner()
    mock = _mock_cm({"success": True, "documents": [{"name": "photo.psd"}, {"name": "design.psd"}]})

    with patch("cli.auto_commands._get_connection_manager", return_value=mock):
        result = runner.invoke(cli, ["--output", "json", "file", "list"])

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["documents"][0]["name"] == "photo.psd"
    assert data["documents"][1]["name"] == "design.psd"


def test_file_list_empty():
    runner = CliRunner()
    mock = _mock_cm({"success": True, "documents": []})

    with patch("cli.auto_commands._get_connection_manager", return_value=mock):
        result = runner.invoke(cli, ["--output", "json", "file", "list"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["documents"] == []


def test_file_list_connection_error():
    runner = CliRunner()
    mock = _mock_cm({
        "success": False,
        "error": {"code": "CONNECTION_ERROR", "message": "Plugin not connected", "category": "connection"},
    })

    with patch("cli.auto_commands._get_connection_manager", return_value=mock):
        result = runner.invoke(cli, ["--output", "json", "file", "list"])

    assert result.exit_code == 2  # CONNECTION_ERROR exit code


# ============================================================
# file info
# ============================================================


def test_file_info_success():
    runner = CliRunner()
    mock = _mock_cm({"success": True, "documentId": 1, "name": "photo.psd", "width": 1920, "height": 1080})

    with patch("cli.auto_commands._get_connection_manager", return_value=mock):
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


# ============================================================
# file open
# ============================================================


def test_file_open_success(tmp_path):
    """file open に存在するファイル → 成功"""
    f = tmp_path / "new.psd"
    f.write_text("dummy")
    runner = CliRunner()
    mock = _mock_cm({"success": True, "documentId": 3, "name": "new.psd"})

    with patch("cli.auto_commands._get_connection_manager", return_value=mock):
        result = runner.invoke(cli, ["--output", "json", "file", "open", "--path", str(f)])

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["documentId"] == 3


def test_file_open_missing_path():
    runner = CliRunner()
    result = runner.invoke(cli, ["file", "open"])
    assert result.exit_code != 0


# ============================================================
# file close / save
# ============================================================


def test_file_close_success():
    runner = CliRunner()
    mock = _mock_cm({"success": True, "closed": True})

    with patch("cli.auto_commands._get_connection_manager", return_value=mock):
        result = runner.invoke(cli, ["--output", "json", "file", "close", "--doc-id", "1"])

    assert result.exit_code == 0


def test_file_save_success():
    runner = CliRunner()
    mock = _mock_cm({"success": True, "saved": True})

    with patch("cli.auto_commands._get_connection_manager", return_value=mock):
        result = runner.invoke(cli, ["--output", "json", "file", "save", "--doc-id", "1"])

    assert result.exit_code == 0


# ============================================================
# validation (file open)
# ============================================================


def test_handle_validation_error():
    """ValidationError が exit code 4 で処理される"""
    runner = CliRunner()
    mock = _mock_cm({
        "success": False,
        "error": {"code": "VALIDATION_ERROR", "message": "Invalid input", "category": "validation"},
    })

    with patch("cli.auto_commands._get_connection_manager", return_value=mock):
        result = runner.invoke(cli, ["--output", "json", "file", "list"])

    assert result.exit_code == 4


def test_file_open_validation_empty_path():
    """file open に空文字列 → exit code 4"""
    runner = CliRunner()
    result = runner.invoke(cli, ["--output", "json", "file", "open", "--path", ""])
    assert result.exit_code == 4


def test_file_open_validation_traversal():
    """file open にパストラバーサル → exit code 4"""
    runner = CliRunner()
    result = runner.invoke(cli, ["--output", "json", "file", "open", "--path", "../etc/passwd"])
    assert result.exit_code == 4


def test_file_open_validation_nonexistent():
    """file open に存在しないファイル → exit code 4"""
    runner = CliRunner()
    result = runner.invoke(cli, ["--output", "json", "file", "open", "--path", "/nonexistent/file.psd"])
    assert result.exit_code == 4


def test_file_open_with_valid_file(tmp_path):
    """file open に存在するファイル → バリデーション通過して Photoshop に送信"""
    f = tmp_path / "valid.psd"
    f.write_text("dummy")
    runner = CliRunner()
    mock = _mock_cm({"success": True, "documentId": 3, "name": "valid.psd"})

    with patch("cli.auto_commands._get_connection_manager", return_value=mock):
        result = runner.invoke(cli, ["--output", "json", "file", "open", "--path", str(f)])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["documentId"] == 3


# ============================================================
# document コマンド（file のエイリアスと同等の動作）
# ============================================================


def test_document_list_success():
    """document list は file list と同等に動作する"""
    runner = CliRunner()
    mock = _mock_cm({"success": True, "documents": [{"name": "photo.psd"}]})

    with patch("cli.auto_commands._get_connection_manager", return_value=mock):
        result = runner.invoke(cli, ["--output", "json", "document", "list"])

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["documents"][0]["name"] == "photo.psd"
    # document.list コマンドとして送信される
    mock.execute.assert_called_once()
    assert mock.execute.call_args[0][0] == "document.list"


def test_document_info_success():
    runner = CliRunner()
    mock = _mock_cm({"success": True, "documentId": 1, "name": "test.psd"})

    with patch("cli.auto_commands._get_connection_manager", return_value=mock):
        result = runner.invoke(cli, ["--output", "json", "document", "info", "--doc-id", "1"])

    assert result.exit_code == 0
    mock.execute.assert_called_once()
    assert mock.execute.call_args[0][0] == "document.info"


def test_document_open_success(tmp_path):
    f = tmp_path / "doc.psd"
    f.write_text("dummy")
    runner = CliRunner()
    mock = _mock_cm({"success": True, "documentId": 5, "name": "doc.psd"})

    with patch("cli.auto_commands._get_connection_manager", return_value=mock):
        result = runner.invoke(cli, ["--output", "json", "document", "open", "--path", str(f)])

    assert result.exit_code == 0
    mock.execute.assert_called_once()
    assert mock.execute.call_args[0][0] == "document.open"


def test_document_close_success():
    runner = CliRunner()
    mock = _mock_cm({"success": True, "closed": True})

    with patch("cli.auto_commands._get_connection_manager", return_value=mock):
        result = runner.invoke(cli, ["--output", "json", "document", "close", "--doc-id", "1"])

    assert result.exit_code == 0
    mock.execute.assert_called_once()
    assert mock.execute.call_args[0][0] == "document.close"


def test_document_save_success():
    runner = CliRunner()
    mock = _mock_cm({"success": True, "saved": True})

    with patch("cli.auto_commands._get_connection_manager", return_value=mock):
        result = runner.invoke(cli, ["--output", "json", "document", "save", "--doc-id", "1"])

    assert result.exit_code == 0
    mock.execute.assert_called_once()
    assert mock.execute.call_args[0][0] == "document.save"


# ============================================================
# file コマンドが file.* として送信されることの確認
# ============================================================


def test_file_list_sends_file_command():
    """file list は file.list コマンドとして送信される"""
    runner = CliRunner()
    mock = _mock_cm({"success": True, "documents": []})

    with patch("cli.auto_commands._get_connection_manager", return_value=mock):
        result = runner.invoke(cli, ["--output", "json", "file", "list"])

    assert result.exit_code == 0
    mock.execute.assert_called_once()
    assert mock.execute.call_args[0][0] == "file.list"
