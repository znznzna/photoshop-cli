"""Tests for scripts/sync_version.py"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

# scripts/ はパッケージではないため、sys.path に追加してインポート
SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


class TestReadPyprojectVersion:
    def test_reads_version_from_pyproject(self, tmp_path):
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nversion = "1.2.3"\n')

        from sync_version import read_pyproject_version

        with patch("sync_version.ROOT", tmp_path):
            result = read_pyproject_version()
        assert result == "1.2.3"


class TestSyncInitPy:
    def test_updates_version_in_init_py(self, tmp_path):
        sdk_dir = tmp_path / "photoshop_sdk"
        sdk_dir.mkdir()
        init_py = sdk_dir / "__init__.py"
        init_py.write_text('__version__ = "0.0.0"\n')

        from sync_version import sync_init_py

        with patch("sync_version.ROOT", tmp_path):
            changed = sync_init_py("1.0.0")

        assert changed is True
        assert '__version__ = "1.0.0"' in init_py.read_text()

    def test_no_change_when_already_synced(self, tmp_path):
        sdk_dir = tmp_path / "photoshop_sdk"
        sdk_dir.mkdir()
        init_py = sdk_dir / "__init__.py"
        init_py.write_text('__version__ = "1.0.0"\n')

        from sync_version import sync_init_py

        with patch("sync_version.ROOT", tmp_path):
            changed = sync_init_py("1.0.0")

        assert changed is False


class TestSyncCliMainPy:
    def test_updates_version_option(self, tmp_path):
        cli_dir = tmp_path / "cli"
        cli_dir.mkdir()
        main_py = cli_dir / "main.py"
        main_py.write_text('@click.version_option(version="0.1.0", prog_name="psd")\n')

        from sync_version import sync_cli_main_py

        with patch("sync_version.ROOT", tmp_path):
            changed = sync_cli_main_py("1.0.0")

        assert changed is True
        assert '@click.version_option(version="1.0.0"' in main_py.read_text()

    def test_no_change_when_already_synced(self, tmp_path):
        cli_dir = tmp_path / "cli"
        cli_dir.mkdir()
        main_py = cli_dir / "main.py"
        main_py.write_text('@click.version_option(version="1.0.0", prog_name="psd")\n')

        from sync_version import sync_cli_main_py

        with patch("sync_version.ROOT", tmp_path):
            changed = sync_cli_main_py("1.0.0")

        assert changed is False


class TestSyncUxpPluginJson:
    def test_updates_manifest_and_package_json(self, tmp_path):
        uxp_dir = tmp_path / "uxp-plugin"
        uxp_dir.mkdir()
        manifest = uxp_dir / "manifest.json"
        manifest.write_text(json.dumps({"version": "0.0.0", "name": "test"}, indent=2))
        package = uxp_dir / "package.json"
        package.write_text(json.dumps({"version": "0.0.0", "name": "test"}, indent=2))

        from sync_version import sync_uxp_plugin_json

        with patch("sync_version.ROOT", tmp_path):
            changed = sync_uxp_plugin_json("1.0.0")

        assert changed is True
        assert json.loads(manifest.read_text())["version"] == "1.0.0"
        assert json.loads(package.read_text())["version"] == "1.0.0"

    def test_no_change_when_already_synced(self, tmp_path):
        uxp_dir = tmp_path / "uxp-plugin"
        uxp_dir.mkdir()
        manifest = uxp_dir / "manifest.json"
        manifest.write_text(json.dumps({"version": "1.0.0"}, indent=2))
        package = uxp_dir / "package.json"
        package.write_text(json.dumps({"version": "1.0.0"}, indent=2))

        from sync_version import sync_uxp_plugin_json

        with patch("sync_version.ROOT", tmp_path):
            changed = sync_uxp_plugin_json("1.0.0")

        assert changed is False


class TestSyncClaudePluginJson:
    def test_updates_marketplace_and_plugin_json(self, tmp_path):
        claude_dir = tmp_path / ".claude-plugin"
        claude_dir.mkdir()
        marketplace = claude_dir / "marketplace.json"
        marketplace.write_text(json.dumps({
            "plugins": [{"name": "photoshop-cli", "version": "0.0.0"}]
        }, indent=2))

        plugin_dir = tmp_path / "plugin" / ".claude-plugin"
        plugin_dir.mkdir(parents=True)
        plugin_json = plugin_dir / "plugin.json"
        plugin_json.write_text(json.dumps({"version": "0.0.0"}, indent=2))

        from sync_version import sync_claude_plugin_json

        with patch("sync_version.ROOT", tmp_path):
            changed = sync_claude_plugin_json("1.0.0")

        assert changed is True
        data = json.loads(marketplace.read_text())
        assert data["plugins"][0]["version"] == "1.0.0"
        assert json.loads(plugin_json.read_text())["version"] == "1.0.0"


class TestMain:
    def test_main_returns_zero(self, tmp_path):
        # Setup all required files
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nversion = "1.0.0"\n')

        sdk_dir = tmp_path / "photoshop_sdk"
        sdk_dir.mkdir()
        (sdk_dir / "__init__.py").write_text('__version__ = "1.0.0"\n')

        cli_dir = tmp_path / "cli"
        cli_dir.mkdir()
        (cli_dir / "main.py").write_text('@click.version_option(version="1.0.0", prog_name="psd")\n')

        uxp_dir = tmp_path / "uxp-plugin"
        uxp_dir.mkdir()
        (uxp_dir / "manifest.json").write_text(json.dumps({"version": "1.0.0"}, indent=2))
        (uxp_dir / "package.json").write_text(json.dumps({"version": "1.0.0"}, indent=2))

        from sync_version import main

        with patch("sync_version.ROOT", tmp_path):
            assert main() == 0
