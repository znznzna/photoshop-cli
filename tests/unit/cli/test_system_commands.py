"""psd system サブコマンドのユニットテスト"""

import json
from unittest.mock import AsyncMock, patch

from click.testing import CliRunner

from cli.main import cli


def test_system_ping_success():
    """system ping が成功レスポンスを返す"""
    runner = CliRunner()
    mock_client = AsyncMock()
    mock_client.ping.return_value = {"status": "ok"}

    with patch("cli.commands.system.PhotoshopClient", return_value=mock_client):
        result = runner.invoke(cli, ["--output", "json", "system", "ping"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["status"] == "ok"


def test_system_ping_connection_error():
    """未接続時にexit code 2を返す"""
    from photoshop_sdk.exceptions import ConnectionError as PSConnectionError

    runner = CliRunner()
    mock_client = AsyncMock()
    mock_client.ping.side_effect = PSConnectionError("Not connected")

    with patch("cli.commands.system.PhotoshopClient", return_value=mock_client):
        result = runner.invoke(cli, ["--output", "json", "system", "ping"])

    assert result.exit_code == 2


def test_system_group_exists():
    """system サブグループが CLI に登録されている"""
    runner = CliRunner()
    result = runner.invoke(cli, ["system", "--help"])
    assert result.exit_code == 0
    assert "ping" in result.output
