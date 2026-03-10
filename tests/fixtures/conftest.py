import asyncio
import pytest_asyncio

from photoshop_sdk.client import PhotoshopClient
from tests.fixtures.mock_uxp_client import MockUXPClient


@pytest_asyncio.fixture
async def ps_client(tmp_path):
    """起動済み PhotoshopClient fixture"""
    port_file = str(tmp_path / "ps_port.txt")
    client = PhotoshopClient(port_file=port_file)
    await client.start()
    yield client
    await client.stop()


@pytest_asyncio.fixture
async def mock_uxp(ps_client):
    """ps_client に接続した MockUXPClient fixture"""
    mock = MockUXPClient(port_file=ps_client._bridge._port_file)
    await mock.connect()
    await asyncio.sleep(0.1)  # 接続確立を待つ
    yield mock
    await mock.disconnect()
