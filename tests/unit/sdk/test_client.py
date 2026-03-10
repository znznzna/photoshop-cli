from pathlib import Path

import pytest

from photoshop_sdk.client import PhotoshopClient
from photoshop_sdk.exceptions import (
    ConnectionError as PSConnectionError,
)


@pytest.fixture
async def running_client(tmp_path):
    """ws_bridge を起動した PhotoshopClient fixture（fake plugin接続なし）"""
    port_file = str(tmp_path / "ps_port.txt")
    client = PhotoshopClient(port_file=port_file)
    await client.start()
    yield client
    await client.stop()


async def test_client_start_creates_port_file(tmp_path):
    port_file = tmp_path / "ps_port.txt"
    client = PhotoshopClient(port_file=str(port_file))
    await client.start()
    assert port_file.exists()
    await client.stop()


async def test_client_context_manager(tmp_path):
    port_file = str(tmp_path / "ps_port.txt")
    async with PhotoshopClient(port_file=port_file) as _client:
        assert Path(port_file).exists()
    # stop後はポートファイルが消える
    assert not Path(port_file).exists()


async def test_file_list_no_connection(running_client):
    """UXP Plugin未接続時は ConnectionError"""
    with pytest.raises(PSConnectionError):
        await running_client.file_list()


async def test_file_info_no_connection(running_client):
    """UXP Plugin未接続時は ConnectionError"""
    with pytest.raises(PSConnectionError):
        await running_client.file_info(doc_id=1)
