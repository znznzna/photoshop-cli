from pathlib import Path

from photoshop_sdk.paths import get_port_file, get_ws_port_file


def test_get_port_file_returns_path():
    p = get_port_file()
    assert isinstance(p, Path)


def test_get_port_file_default_on_mac(monkeypatch):
    monkeypatch.delenv("PS_PORT_FILE", raising=False)
    p = get_port_file()
    assert p == Path("/tmp/photoshop_ws_port.txt")


def test_get_port_file_env_override(monkeypatch, tmp_path):
    custom = str(tmp_path / "custom_port.txt")
    monkeypatch.setenv("PS_PORT_FILE", custom)
    p = get_port_file()
    assert p == Path(custom)


def test_get_ws_port_file_alias():
    """get_ws_port_file は get_port_file の別名"""
    assert get_ws_port_file() == get_port_file()
