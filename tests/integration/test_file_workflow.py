"""
統合テスト: PhotoshopClient + MockUXPClient を使用して
実際の WS 通信を検証する（Photoshop 不要）
"""

import asyncio

import pytest

from photoshop_sdk.client import PhotoshopClient
from photoshop_sdk.exceptions import ConnectionError as PSConnectionError
from photoshop_sdk.schema import DocumentInfo
from tests.fixtures.mock_uxp_client import MockUXPClient


@pytest.fixture
async def client_and_mock(tmp_path):
    """PhotoshopClient + MockUXPClient を起動する fixture"""
    port_file = str(tmp_path / "ps_port.txt")
    client = PhotoshopClient(port_file=port_file)
    await client.start()

    mock = MockUXPClient(port_file=port_file)
    await mock.connect()
    await asyncio.sleep(0.15)  # WS 接続確立待ち

    yield client, mock

    await mock.disconnect()
    await asyncio.sleep(0.05)
    await client.stop()


async def test_file_list_e2e(client_and_mock):
    """file.list コマンドのエンドツーエンドテスト"""
    client, mock = client_and_mock
    mock.register_response("file.list", {
        "documents": [
            {"documentId": 1, "name": "photo.psd", "path": "/Users/test/photo.psd", "width": 1920, "height": 1080},
            {"documentId": 2, "name": "design.psd", "path": "/Users/test/design.psd", "width": 800, "height": 600},
        ]
    })

    docs = await client.file_list()
    assert len(docs) == 2
    assert docs[0].name == "photo.psd"
    assert docs[0].width == 1920
    assert docs[1].name == "design.psd"
    assert docs[1].documentId == 2


async def test_file_info_e2e(client_and_mock):
    """file.info コマンドのエンドツーエンドテスト"""
    client, mock = client_and_mock
    mock.register_response("file.info", {
        "documentId": 1,
        "name": "photo.psd",
        "path": "/Users/test/photo.psd",
        "width": 1920,
        "height": 1080,
        "colorMode": "RGB",
        "resolution": 72.0,
    })

    doc = await client.file_info(doc_id=1)
    assert isinstance(doc, DocumentInfo)
    assert doc.documentId == 1
    assert doc.name == "photo.psd"
    assert doc.colorMode == "RGB"


async def test_file_open_e2e(client_and_mock):
    """file.open コマンドのエンドツーエンドテスト"""
    client, mock = client_and_mock
    mock.register_response("file.open", {
        "documentId": 3,
        "name": "new.psd",
        "path": "/path/to/new.psd",
        "width": 2560,
        "height": 1440,
    })

    result = await client.file_open(path="/path/to/new.psd")
    assert result["documentId"] == 3
    assert result["name"] == "new.psd"


async def test_file_list_empty_e2e(client_and_mock):
    """ドキュメントなし時の file.list"""
    client, mock = client_and_mock
    mock.register_response("file.list", {"documents": []})

    docs = await client.file_list()
    assert docs == []


async def test_error_propagation_e2e(client_and_mock):
    """UXP からのエラーが適切に例外に変換される"""
    from photoshop_sdk.exceptions import DocumentNotFoundError

    client, mock = client_and_mock
    mock.register_response("file.info", {
        "error": {"code": "DOCUMENT_NOT_FOUND", "message": "Document 99 not found"}
    })

    with pytest.raises(DocumentNotFoundError):
        await client.file_info(doc_id=99)


async def test_connection_required_before_commands():
    """MockUXP が接続する前は ConnectionError"""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        port_file = f"{tmp}/ps_port.txt"
        client = PhotoshopClient(port_file=port_file)
        await client.start()

        with pytest.raises(PSConnectionError):
            await client.file_list()

        await client.stop()
