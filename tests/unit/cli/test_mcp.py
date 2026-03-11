"""Tests for cli/commands/mcp.py"""

import json
from unittest.mock import patch

from click.testing import CliRunner

from cli.main import cli


class TestMcpInstall:
    def test_install_creates_config(self, tmp_path):
        config_path = tmp_path / "claude_desktop_config.json"
        runner = CliRunner()

        with patch("cli.commands.mcp._get_claude_config_path", return_value=config_path):
            with patch("cli.commands.mcp._resolve_psd_mcp_command", return_value="/usr/local/bin/psd-mcp"):
                result = runner.invoke(cli, ["mcp", "install"])

        assert result.exit_code == 0
        assert "installed" in result.output.lower() or "MCP server installed" in result.output

        config = json.loads(config_path.read_text())
        assert "photoshop-cli" in config["mcpServers"]
        assert config["mcpServers"]["photoshop-cli"]["command"] == "/usr/local/bin/psd-mcp"

    def test_install_does_not_overwrite_without_force(self, tmp_path):
        config_path = tmp_path / "claude_desktop_config.json"
        config_path.write_text(json.dumps({
            "mcpServers": {
                "photoshop-cli": {"command": "old-command", "args": []}
            }
        }))
        runner = CliRunner()

        with patch("cli.commands.mcp._get_claude_config_path", return_value=config_path):
            result = runner.invoke(cli, ["mcp", "install"])

        assert result.exit_code == 0
        assert "already installed" in result.output.lower()
        config = json.loads(config_path.read_text())
        assert config["mcpServers"]["photoshop-cli"]["command"] == "old-command"

    def test_install_overwrites_with_force(self, tmp_path):
        config_path = tmp_path / "claude_desktop_config.json"
        config_path.write_text(json.dumps({
            "mcpServers": {
                "photoshop-cli": {"command": "old-command", "args": []}
            }
        }))
        runner = CliRunner()

        with patch("cli.commands.mcp._get_claude_config_path", return_value=config_path):
            with patch("cli.commands.mcp._resolve_psd_mcp_command", return_value="/new/psd-mcp"):
                result = runner.invoke(cli, ["mcp", "install", "--force"])

        assert result.exit_code == 0
        config = json.loads(config_path.read_text())
        assert config["mcpServers"]["photoshop-cli"]["command"] == "/new/psd-mcp"

    def test_install_preserves_other_servers(self, tmp_path):
        config_path = tmp_path / "claude_desktop_config.json"
        config_path.write_text(json.dumps({
            "mcpServers": {
                "lightroom-cli": {"command": "lr-mcp", "args": []}
            }
        }))
        runner = CliRunner()

        with patch("cli.commands.mcp._get_claude_config_path", return_value=config_path):
            with patch("cli.commands.mcp._resolve_psd_mcp_command", return_value="/usr/local/bin/psd-mcp"):
                runner.invoke(cli, ["mcp", "install"])

        config = json.loads(config_path.read_text())
        assert "lightroom-cli" in config["mcpServers"]
        assert "photoshop-cli" in config["mcpServers"]


class TestMcpUninstall:
    def test_uninstall_removes_entry(self, tmp_path):
        config_path = tmp_path / "claude_desktop_config.json"
        config_path.write_text(json.dumps({
            "mcpServers": {
                "photoshop-cli": {"command": "psd-mcp", "args": []}
            }
        }))
        runner = CliRunner()

        with patch("cli.commands.mcp._get_claude_config_path", return_value=config_path):
            result = runner.invoke(cli, ["mcp", "uninstall"])

        assert result.exit_code == 0
        assert "uninstalled" in result.output.lower()
        config = json.loads(config_path.read_text())
        assert "photoshop-cli" not in config.get("mcpServers", {})

    def test_uninstall_when_not_installed(self, tmp_path):
        config_path = tmp_path / "claude_desktop_config.json"
        config_path.write_text(json.dumps({"mcpServers": {}}))
        runner = CliRunner()

        with patch("cli.commands.mcp._get_claude_config_path", return_value=config_path):
            result = runner.invoke(cli, ["mcp", "uninstall"])

        assert result.exit_code == 0
        assert "not installed" in result.output.lower()


class TestMcpStatus:
    def test_status_when_installed(self, tmp_path):
        config_path = tmp_path / "claude_desktop_config.json"
        config_path.write_text(json.dumps({
            "mcpServers": {
                "photoshop-cli": {"command": "/usr/local/bin/psd-mcp", "args": []}
            }
        }))
        runner = CliRunner()

        with patch("cli.commands.mcp._get_claude_config_path", return_value=config_path):
            result = runner.invoke(cli, ["mcp", "status"])

        assert result.exit_code == 0
        assert "Installed" in result.output
        assert "/usr/local/bin/psd-mcp" in result.output

    def test_status_when_not_installed(self, tmp_path):
        config_path = tmp_path / "claude_desktop_config.json"
        config_path.write_text(json.dumps({}))
        runner = CliRunner()

        with patch("cli.commands.mcp._get_claude_config_path", return_value=config_path):
            result = runner.invoke(cli, ["mcp", "status"])

        assert result.exit_code == 0
        assert "Not installed" in result.output


class TestMcpTest:
    def test_test_success(self):
        runner = CliRunner()

        async def mock_aenter(self):
            return self

        async def mock_aexit(self, *a):
            pass

        async def mock_ping(self):
            return {"status": "ok"}

        MockClient = type("MockClient", (), {
            "__aenter__": mock_aenter,
            "__aexit__": mock_aexit,
            "ping": mock_ping,
        })
        mock_client = MockClient()

        with patch("cli.commands.mcp._create_test_client", return_value=mock_client):
            result = runner.invoke(cli, ["mcp", "test"])

        assert result.exit_code == 0
        assert "OK" in result.output or "ok" in result.output.lower()

    def test_test_failure(self):
        runner = CliRunner()

        with patch("cli.commands.mcp._create_test_client", side_effect=Exception("Connection refused")):
            result = runner.invoke(cli, ["mcp", "test"])

        assert result.exit_code != 0
