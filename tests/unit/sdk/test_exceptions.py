import pytest

from photoshop_sdk.exceptions import (
    PhotoshopSDKError,
    ConnectionError as PSConnectionError,
    TimeoutError as PSTimeoutError,
    DocumentNotFoundError,
    ValidationError,
    ERROR_CODE_MAP,
)


def test_base_error_attributes():
    e = PhotoshopSDKError("test message", code="TEST_CODE", details={"key": "val"})
    assert str(e) == "test message"
    assert e.code == "TEST_CODE"
    assert e.details == {"key": "val"}


def test_base_error_defaults():
    e = PhotoshopSDKError("msg")
    assert e.code is None
    assert e.details == {}


def test_connection_error_is_subclass():
    e = PSConnectionError("conn failed")
    assert isinstance(e, PhotoshopSDKError)


def test_timeout_error_is_subclass():
    e = PSTimeoutError("timed out")
    assert isinstance(e, PhotoshopSDKError)


def test_document_not_found_default_message():
    e = DocumentNotFoundError()
    assert "not found" in str(e).lower()
    assert e.code == "DOCUMENT_NOT_FOUND"


def test_document_not_found_with_doc_id():
    e = DocumentNotFoundError(doc_id=42)
    assert "42" in str(e)
    assert e.code == "DOCUMENT_NOT_FOUND"


def test_validation_error_is_subclass():
    e = ValidationError("bad param")
    assert isinstance(e, PhotoshopSDKError)


def test_error_code_map_contains_known_codes():
    assert "DOCUMENT_NOT_FOUND" in ERROR_CODE_MAP
    assert "CONNECTION_FAILED" in ERROR_CODE_MAP
    assert "TIMEOUT" in ERROR_CODE_MAP
    assert "VALIDATION_ERROR" in ERROR_CODE_MAP


def test_error_code_map_maps_to_correct_classes():
    assert ERROR_CODE_MAP["DOCUMENT_NOT_FOUND"] is DocumentNotFoundError
    assert ERROR_CODE_MAP["CONNECTION_FAILED"] is PSConnectionError
