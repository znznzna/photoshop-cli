"""--dry-run のユニットテスト"""

import json
from unittest.mock import AsyncMock, patch

from click.testing import CliRunner

from cli.main import cli
from photoshop_sdk.schema import DocumentInfo

MOCK_DOC_1 = DocumentInfo(documentId=1, name="photo.psd", path="/Users/test/photo.psd", width=1920, height=1080)


def _make_mock_client(responses: dict):
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
    """file list に --dry-run しても通常実行される"""
    runner = CliRunner()
    mock_client = _make_mock_client({"file_list": [MOCK_DOC_1]})

    with patch("cli.commands.file.PhotoshopClient", return_value=mock_client):
        result = runner.invoke(cli, ["--output", "json", "--dry-run", "file", "list"])

    assert result.exit_code == 0
    data = json.loads(result.output)
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
    assert "dry_run" in data
    assert "command" in data
    assert "params" in data
    assert "timeout" in data
    assert "message" in data
