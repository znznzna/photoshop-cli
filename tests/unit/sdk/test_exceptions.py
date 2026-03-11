from photoshop_sdk.exceptions import (
    ERROR_CODE_MAP,
    ConnectionError as PSConnectionError,
    DocumentNotFoundError,
    PhotoshopSDKError,
    TimeoutError as PSTimeoutError,
    ValidationError,
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


# --- Phase 1.4: 新規例外クラス ---

from photoshop_sdk.exceptions import (
    BatchPlayBlockedError,
    ChannelNotFoundError,
    FilterError,
    LayerNotFoundError,
    PathNotFoundError,
    SelectionError,
    UnsupportedOperationError,
)


def test_layer_not_found_is_subclass():
    e = LayerNotFoundError("Layer 5 not found", code="LAYER_NOT_FOUND")
    assert isinstance(e, PhotoshopSDKError)
    assert e.code == "LAYER_NOT_FOUND"


def test_filter_error_is_subclass():
    e = FilterError("Filter failed", code="FILTER_ERROR")
    assert isinstance(e, PhotoshopSDKError)
    assert e.code == "FILTER_ERROR"


def test_channel_not_found_is_subclass():
    e = ChannelNotFoundError("Channel not found", code="CHANNEL_NOT_FOUND")
    assert isinstance(e, PhotoshopSDKError)
    assert e.code == "CHANNEL_NOT_FOUND"


def test_selection_error_is_subclass():
    e = SelectionError("Selection failed", code="SELECTION_ERROR")
    assert isinstance(e, PhotoshopSDKError)
    assert e.code == "SELECTION_ERROR"


def test_path_not_found_is_subclass():
    e = PathNotFoundError("Path not found", code="PATH_NOT_FOUND")
    assert isinstance(e, PhotoshopSDKError)
    assert e.code == "PATH_NOT_FOUND"


def test_unsupported_operation_is_subclass():
    e = UnsupportedOperationError("Not supported", code="UNSUPPORTED_OPERATION")
    assert isinstance(e, PhotoshopSDKError)
    assert e.code == "UNSUPPORTED_OPERATION"


def test_batch_play_blocked_is_subclass():
    e = BatchPlayBlockedError("Blocked descriptor", code="BATCH_PLAY_BLOCKED")
    assert isinstance(e, PhotoshopSDKError)
    assert e.code == "BATCH_PLAY_BLOCKED"


def test_error_code_map_contains_new_codes():
    assert "LAYER_NOT_FOUND" in ERROR_CODE_MAP
    assert "FILTER_ERROR" in ERROR_CODE_MAP
    assert "CHANNEL_NOT_FOUND" in ERROR_CODE_MAP
    assert "SELECTION_ERROR" in ERROR_CODE_MAP
    assert "PATH_NOT_FOUND" in ERROR_CODE_MAP
    assert "UNSUPPORTED_OPERATION" in ERROR_CODE_MAP
    assert "BATCH_PLAY_BLOCKED" in ERROR_CODE_MAP


def test_error_code_map_new_codes_map_correctly():
    assert ERROR_CODE_MAP["LAYER_NOT_FOUND"] is LayerNotFoundError
    assert ERROR_CODE_MAP["FILTER_ERROR"] is FilterError
    assert ERROR_CODE_MAP["CHANNEL_NOT_FOUND"] is ChannelNotFoundError
    assert ERROR_CODE_MAP["SELECTION_ERROR"] is SelectionError
    assert ERROR_CODE_MAP["PATH_NOT_FOUND"] is PathNotFoundError
    assert ERROR_CODE_MAP["UNSUPPORTED_OPERATION"] is UnsupportedOperationError
    assert ERROR_CODE_MAP["BATCH_PLAY_BLOCKED"] is BatchPlayBlockedError
