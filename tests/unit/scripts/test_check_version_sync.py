"""Tests for scripts/check_version_sync.py"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


class TestReadInitPyVersion:
    def test_reads_version(self, tmp_path):
        sdk_dir = tmp_path / "photoshop_sdk"
        sdk_dir.mkdir()
        (sdk_dir / "__init__.py").write_text('__version__ = "1.0.0"\n')

        from check_version_sync import read_init_py_version

        with patch("check_version_sync.ROOT", tmp_path):
            assert read_init_py_version() == "1.0.0"

    def test_returns_none_when_not_found(self, tmp_path):
        sdk_dir = tmp_path / "photoshop_sdk"
        sdk_dir.mkdir()
        (sdk_dir / "__init__.py").write_text("# no version\n")

        from check_version_sync import read_init_py_version

        with patch("check_version_sync.ROOT", tmp_path):
            assert read_init_py_version() is None


class TestReadCliMainVersion:
    def test_reads_version_option(self, tmp_path):
        cli_dir = tmp_path / "cli"
        cli_dir.mkdir()
        (cli_dir / "main.py").write_text('@click.version_option(version="1.0.0", prog_name="psd")\n')

        from check_version_sync import read_cli_main_version

        with patch("check_version_sync.ROOT", tmp_path):
            assert read_cli_main_version() == "1.0.0"

    def test_returns_none_when_not_found(self, tmp_path):
        cli_dir = tmp_path / "cli"
        cli_dir.mkdir()
        (cli_dir / "main.py").write_text("# no version\n")

        from check_version_sync import read_cli_main_version

        with patch("check_version_sync.ROOT", tmp_path):
            assert read_cli_main_version() is None


class TestReadUxpPluginVersions:
    def test_reads_manifest_and_package(self, tmp_path):
        uxp_dir = tmp_path / "uxp-plugin"
        uxp_dir.mkdir()
        (uxp_dir / "manifest.json").write_text(json.dumps({"version": "1.0.0"}))
        (uxp_dir / "package.json").write_text(json.dumps({"version": "1.0.0"}))

        from check_version_sync import read_uxp_plugin_versions

        with patch("check_version_sync.ROOT", tmp_path):
            result = read_uxp_plugin_versions()

        assert result["uxp-plugin/manifest.json"] == "1.0.0"
        assert result["uxp-plugin/package.json"] == "1.0.0"


class TestReadClaudePluginVersions:
    def test_reads_marketplace_and_plugin(self, tmp_path):
        claude_dir = tmp_path / ".claude-plugin"
        claude_dir.mkdir()
        (claude_dir / "marketplace.json").write_text(
            json.dumps({"plugins": [{"name": "photoshop-cli", "version": "1.0.0"}]})
        )

        plugin_dir = tmp_path / "plugin" / ".claude-plugin"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.json").write_text(json.dumps({"version": "1.0.0"}))

        from check_version_sync import read_claude_plugin_versions

        with patch("check_version_sync.ROOT", tmp_path):
            result = read_claude_plugin_versions()

        assert result[".claude-plugin/marketplace.json"] == "1.0.0"
        assert result["plugin/.claude-plugin/plugin.json"] == "1.0.0"


class TestMain:
    def test_returns_zero_when_all_synced(self, tmp_path):
        self._setup_all_files(tmp_path, "1.0.0")

        from check_version_sync import main

        with patch("check_version_sync.ROOT", tmp_path):
            assert main() == 0

    def test_returns_one_when_mismatch(self, tmp_path):
        self._setup_all_files(tmp_path, "1.0.0")
        # Break one version
        sdk_dir = tmp_path / "photoshop_sdk"
        (sdk_dir / "__init__.py").write_text('__version__ = "0.9.0"\n')

        from check_version_sync import main

        with patch("check_version_sync.ROOT", tmp_path):
            assert main() == 1

    def _setup_all_files(self, tmp_path, version):
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text(f'[project]\nversion = "{version}"\n')

        sdk_dir = tmp_path / "photoshop_sdk"
        sdk_dir.mkdir(exist_ok=True)
        (sdk_dir / "__init__.py").write_text(f'__version__ = "{version}"\n')

        cli_dir = tmp_path / "cli"
        cli_dir.mkdir(exist_ok=True)
        (cli_dir / "main.py").write_text(f'@click.version_option(version="{version}", prog_name="psd")\n')

        uxp_dir = tmp_path / "uxp-plugin"
        uxp_dir.mkdir(exist_ok=True)
        (uxp_dir / "manifest.json").write_text(json.dumps({"version": version}))
        (uxp_dir / "package.json").write_text(json.dumps({"version": version}))

        claude_dir = tmp_path / ".claude-plugin"
        claude_dir.mkdir(exist_ok=True)
        (claude_dir / "marketplace.json").write_text(
            json.dumps({"plugins": [{"name": "photoshop-cli", "version": version}]})
        )

        plugin_dir = tmp_path / "plugin" / ".claude-plugin"
        plugin_dir.mkdir(parents=True, exist_ok=True)
        (plugin_dir / "plugin.json").write_text(json.dumps({"version": version}))
