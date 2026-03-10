import pytest
from click.testing import CliRunner

from cli.main import cli


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "Photoshop" in result.output or "psd" in result.output.lower()


def test_cli_version():
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_cli_output_option_json():
    runner = CliRunner()
    result = runner.invoke(cli, ["--output", "json", "--help"])
    assert result.exit_code == 0


def test_cli_output_option_invalid():
    runner = CliRunner()
    result = runner.invoke(cli, ["--output", "invalid_mode", "file", "list"])
    assert result.exit_code != 0


def test_cli_file_subgroup_exists():
    runner = CliRunner()
    result = runner.invoke(cli, ["file", "--help"])
    assert result.exit_code == 0
    assert "open" in result.output
    assert "list" in result.output
    assert "info" in result.output
