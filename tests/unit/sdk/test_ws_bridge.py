import asyncio
import json
import tempfile
from pathlib import Path

import pytest
import websockets

from photoshop_sdk.ws_bridge import ResilientWSBridge, ConnectionState
from photoshop_sdk.exceptions import ConnectionError as PSConnectionError, TimeoutError as PSTimeoutError


@pytest.fixture
async def bridge(tmp_path):
    """テスト用 WSBridge（ランダムポート）"""
    port_file = str(tmp_path / "test_ws_port.txt")
    b = ResilientWSBridge(port_file=port_file, heartbeat_interval=0)
    yield b
    await b.stop()


@pytest.fixture
async def running_bridge(tmp_path):
    """起動済み WSBridge fixture"""
    port_file = str(tmp_path / "test_ws_port.txt")
    b = ResilientWSBridge(port_file=port_file, heartbeat_interval=0)
    await b.start()
    yield b
    await b.stop()


async def test_initial_state_is_waiting():
    b = ResilientWSBridge(port_file="/tmp/nonexistent_test_port.txt", heartbeat_interval=0)
    assert b.state == ConnectionState.WAITING_FOR_PLUGIN


async def test_start_writes_port_file(tmp_path):
    port_file = tmp_path / "port.txt"
    b = ResilientWSBridge(port_file=str(port_file), heartbeat_interval=0)
    await b.start()
    assert port_file.exists()
    port = int(port_file.read_text().strip())
    assert 1024 <= port <= 65535
    await b.stop()


async def test_state_connected_when_plugin_connects(running_bridge):
    """UXP Plugin（モック）が接続したら CONNECTED になる"""
    port = int(Path(running_bridge._port_file).read_text().strip())
    async with websockets.connect(f"ws://localhost:{port}"):
        await asyncio.sleep(0.1)
        assert running_bridge.state == ConnectionState.CONNECTED


async def test_state_reverts_to_waiting_on_disconnect(running_bridge):
    """UXP Plugin が切断したら WAITING_FOR_PLUGIN に戻る"""
    port = int(Path(running_bridge._port_file).read_text().strip())
    async with websockets.connect(f"ws://localhost:{port}"):
        await asyncio.sleep(0.1)
    await asyncio.sleep(0.1)
    assert running_bridge.state == ConnectionState.WAITING_FOR_PLUGIN


async def test_send_command_raises_when_not_connected(bridge):
    """未接続時の send_command は ConnectionError"""
    with pytest.raises(PSConnectionError):
        await bridge.send_command("file.list", timeout=1.0)


async def test_send_command_and_receive_response(running_bridge):
    """コマンド送信 → UXP からの応答を受信できる"""
    port = int(Path(running_bridge._port_file).read_text().strip())

    async def fake_plugin():
        async with websockets.connect(f"ws://localhost:{port}") as ws:
            # コマンドを受信
            raw = await ws.recv()
            msg = json.loads(raw)
            assert msg["command"] == "file.list"
            # 応答を返す
            resp = {"id": msg["id"], "success": True, "result": {"documents": []}}
            await ws.send(json.dumps(resp))
            # 接続維持
            await asyncio.sleep(1.0)

    plugin_task = asyncio.create_task(fake_plugin())
    await asyncio.sleep(0.1)  # Plugin接続待ち

    result = await running_bridge.send_command("file.list", timeout=3.0)
    assert result == {"documents": []}

    plugin_task.cancel()
    try:
        await plugin_task
    except (asyncio.CancelledError, Exception):
        pass


async def test_send_command_timeout(running_bridge):
    """応答のない UXP に対してタイムアウト"""
    port = int(Path(running_bridge._port_file).read_text().strip())

    async def unresponsive_plugin():
        async with websockets.connect(f"ws://localhost:{port}") as ws:
            await asyncio.sleep(10.0)

    task = asyncio.create_task(unresponsive_plugin())
    await asyncio.sleep(0.1)

    with pytest.raises(PSTimeoutError):
        await running_bridge.send_command("file.open", timeout=0.3)

    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass


async def test_stop_removes_port_file(tmp_path):
    port_file = tmp_path / "port.txt"
    b = ResilientWSBridge(port_file=str(port_file), heartbeat_interval=0)
    await b.start()
    assert port_file.exists()
    await b.stop()
    assert not port_file.exists()
