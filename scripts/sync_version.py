#!/usr/bin/env python3
"""Sync version from pyproject.toml to all version files."""

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


def sync_init_py(version: str) -> bool:
    path = ROOT / "photoshop_sdk" / "__init__.py"
    content = path.read_text()
    new_content = re.sub(r'__version__\s*=\s*"[^"]*"', f'__version__ = "{version}"', content)
    if content != new_content:
        path.write_text(new_content)
        print(f"Updated: {path.relative_to(ROOT)}")
        return True
    return False


def sync_cli_main_py(version: str) -> bool:
    """cli/main.py の version_option を同期。"""
    path = ROOT / "cli" / "main.py"
    content = path.read_text()
    new_content = re.sub(
        r'@click\.version_option\(version="[^"]*"',
        f'@click.version_option(version="{version}"',
        content,
    )
    if content != new_content:
        path.write_text(new_content)
        print(f"Updated: {path.relative_to(ROOT)}")
        return True
    return False


def sync_uxp_plugin_json(version: str) -> bool:
    """uxp-plugin/manifest.json と package.json の version を同期。"""
    paths = [
        ROOT / "uxp-plugin" / "manifest.json",
        ROOT / "uxp-plugin" / "package.json",
    ]
    changed = False
    for path in paths:
        if not path.exists():
            continue
        data = json.loads(path.read_text())
        if data.get("version") != version:
            data["version"] = version
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
            print(f"Updated: {path.relative_to(ROOT)}")
            changed = True
    return changed


def sync_claude_plugin_json(version: str) -> bool:
    """.claude-plugin/marketplace.json と plugin/.claude-plugin/plugin.json の version を同期。"""
    paths = [
        ROOT / ".claude-plugin" / "marketplace.json",
        ROOT / "plugin" / ".claude-plugin" / "plugin.json",
    ]
    changed = False
    for path in paths:
        if not path.exists():
            continue
        data = json.loads(path.read_text())
        updated = False
        if "version" in data and data["version"] != version:
            data["version"] = version
            updated = True
        for plugin in data.get("plugins", []):
            if "version" in plugin and plugin["version"] != version:
                plugin["version"] = version
                updated = True
        if updated:
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
            print(f"Updated: {path.relative_to(ROOT)}")
            changed = True
    return changed


def main() -> int:
    version = read_pyproject_version()
    print(f"Source version (pyproject.toml): {version}")

    changed = False
    changed |= sync_init_py(version)
    changed |= sync_cli_main_py(version)
    changed |= sync_uxp_plugin_json(version)
    changed |= sync_claude_plugin_json(version)

    if not changed:
        print("All files already in sync.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
