"""--dry-run のユニットテスト

file.py は auto_commands ベースに変更されたため、
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


def test_dry_run_file_open(tmp_path):
    """--dry-run で file open → Photoshop に送信されず dry_run 出力が返る"""
    f = tmp_path / "test.psd"
    f.write_text("dummy")
    runner = CliRunner()

    with patch("cli.auto_commands._get_connection_manager") as mock_get_cm:
        result = runner.invoke(cli, ["--output", "json", "--dry-run", "file", "open", "--path", str(f)])

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["dry_run"] is True
    assert data["command"] == "file.open"
    assert "path" in data["params"]
    mock_get_cm.assert_not_called()


def test_dry_run_file_close():
    """--dry-run で file close → dry_run 出力"""
    runner = CliRunner()

    with patch("cli.auto_commands._get_connection_manager") as mock_get_cm:
        result = runner.invoke(cli, ["--output", "json", "--dry-run", "file", "close", "--doc-id", "1"])

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["dry_run"] is True
    assert data["command"] == "file.close"
    assert data["params"]["documentId"] == 1
    mock_get_cm.assert_not_called()


def test_dry_run_file_save():
    """--dry-run で file save → dry_run 出力"""
    runner = CliRunner()

    with patch("cli.auto_commands._get_connection_manager") as mock_get_cm:
        result = runner.invoke(cli, ["--output", "json", "--dry-run", "file", "save", "--doc-id", "1"])

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["dry_run"] is True
    assert data["command"] == "file.save"
    mock_get_cm.assert_not_called()


def test_dry_run_validation_error():
    """--dry-run でもバリデーション失敗は exit 4"""
    runner = CliRunner()
    result = runner.invoke(cli, ["--output", "json", "--dry-run", "file", "open", "--path", "../etc/passwd"])
    assert result.exit_code == 4


def test_dry_run_list_ignored():
    """file list に --dry-run しても通常実行される（non-mutating）"""
    runner = CliRunner()
    mock = _mock_cm({"success": True, "documents": [{"name": "photo.psd"}]})

    with patch("cli.auto_commands._get_connection_manager", return_value=mock):
        result = runner.invoke(cli, ["--output", "json", "--dry-run", "file", "list"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["documents"][0]["name"] == "photo.psd"


def test_dry_run_info_ignored():
    """file info に --dry-run しても通常実行される（non-mutating）"""
    runner = CliRunner()
    mock = _mock_cm({"success": True, "documentId": 1, "name": "photo.psd"})

    with patch("cli.auto_commands._get_connection_manager", return_value=mock):
        result = runner.invoke(cli, ["--output", "json", "--dry-run", "file", "info", "--doc-id", "1"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["name"] == "photo.psd"


def test_dry_run_output_json_format(tmp_path):
    """dry-run 出力の JSON 構造を検証"""
    f = tmp_path / "test.psd"
    f.write_text("dummy")
    runner = CliRunner()

    result = runner.invoke(cli, ["--output", "json", "--dry-run", "file", "open", "--path", str(f)])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "dry_run" in data
    assert "command" in data
    assert "params" in data
    assert "timeout" in data
    assert "message" in data
