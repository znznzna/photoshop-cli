import pytest
from pydantic import ValidationError as PydanticValidationError

from photoshop_sdk.schema import (
    DocumentInfo,
    PhotoshopCommand,
    PhotoshopResponse,
)


def test_command_requires_id_and_command():
    cmd = PhotoshopCommand(id="abc-123", command="file.open", params={"path": "/foo.psd"})
    assert cmd.id == "abc-123"
    assert cmd.command == "file.open"
    assert cmd.params == {"path": "/foo.psd"}


def test_command_params_defaults_to_empty():
    cmd = PhotoshopCommand(id="abc-123", command="file.list")
    assert cmd.params == {}


def test_command_missing_id_raises():
    with pytest.raises(PydanticValidationError):
        PhotoshopCommand(command="file.list")


def test_response_success_true():
    resp = PhotoshopResponse(id="abc-123", success=True, result={"documentId": 1})
    assert resp.success is True
    assert resp.result == {"documentId": 1}
    assert resp.error is None


def test_response_success_false():
    resp = PhotoshopResponse(
        id="abc-123",
        success=False,
        error={"code": "DOCUMENT_NOT_FOUND", "message": "Not found"},
    )
    assert resp.success is False
    assert resp.error == {"code": "DOCUMENT_NOT_FOUND", "message": "Not found"}
    assert resp.result is None


def test_document_info_fields():
    doc = DocumentInfo(
        documentId=1,
        name="test.psd",
        path="/Users/test/test.psd",
        width=1920,
        height=1080,
    )
    assert doc.documentId == 1
    assert doc.name == "test.psd"
    assert doc.width == 1920
    assert doc.height == 1080


def test_document_info_optional_path():
    doc = DocumentInfo(documentId=2, name="untitled.psd", width=800, height=600)
    assert doc.path is None
