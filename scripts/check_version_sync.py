#!/usr/bin/env python3
"""Check that all version files match pyproject.toml."""

import json
import re
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parent.parent


def read_pyproject_version() -> str:
    with open(ROOT / "pyproject.toml", "rb") as f:
        data = tomllib.load(f)
    return data["project"]["version"]


def read_init_py_version() -> str | None:
    path = ROOT / "photoshop_sdk" / "__init__.py"
    m = re.search(r'__version__\s*=\s*"([^"]*)"', path.read_text())
    return m.group(1) if m else None


def read_cli_main_version() -> str | None:
    """cli/main.py から version_option のバージョンを読み取る。"""
    path = ROOT / "cli" / "main.py"
    m = re.search(r'@click\.version_option\(version="([^"]*)"', path.read_text())
    return m.group(1) if m else None


def read_uxp_plugin_versions() -> dict[str, str | None]:
    """uxp-plugin の manifest.json と package.json からバージョンを読み取る。"""
    results = {}
    for name in ("manifest.json", "package.json"):
        path = ROOT / "uxp-plugin" / name
        if path.exists():
            data = json.loads(path.read_text())
            results[f"uxp-plugin/{name}"] = data.get("version")
    return results


def read_claude_plugin_versions() -> dict[str, str | None]:
    results = {}
    marketplace = ROOT / ".claude-plugin" / "marketplace.json"
    if marketplace.exists():
        data = json.loads(marketplace.read_text())
        for plugin in data.get("plugins", []):
            results[".claude-plugin/marketplace.json"] = plugin.get("version")
            break
    plugin_json = ROOT / "plugin" / ".claude-plugin" / "plugin.json"
    if plugin_json.exists():
        data = json.loads(plugin_json.read_text())
        results["plugin/.claude-plugin/plugin.json"] = data.get("version")
    return results


def main() -> int:
    source = read_pyproject_version()
    checks = {
        "photoshop_sdk/__init__.py": read_init_py_version(),
        "cli/main.py": read_cli_main_version(),
        **read_uxp_plugin_versions(),
        **read_claude_plugin_versions(),
    }

    mismatches = []
    for file, version in checks.items():
        if version != source:
            mismatches.append((file, version))

    if mismatches:
        print(f"Version mismatch! Source (pyproject.toml): {source}")
        for file, version in mismatches:
            print(f"  {file}: {version or 'NOT FOUND'}")
        print("\nRun: python scripts/sync_version.py")
        return 1

    print(f"All versions in sync: {source}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
