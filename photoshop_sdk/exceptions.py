from typing import Any, Dict, Optional


class PhotoshopSDKError(Exception):
    """Base exception for Photoshop SDK errors"""

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.code = code
        self.details = details or {}


class ConnectionError(PhotoshopSDKError):
    """WebSocket connection errors"""
    pass


class TimeoutError(PhotoshopSDKError):
    """Command timeout errors"""
    pass


class DocumentNotFoundError(PhotoshopSDKError):
    """Document with given ID not found"""

    def __init__(
        self,
        message: Optional[str] = None,
        doc_id: Optional[int] = None,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        if message is None and doc_id is not None:
            message = f"Document with ID '{doc_id}' not found"
        elif message is None:
            message = "Document not found"
        super().__init__(message, code=code or "DOCUMENT_NOT_FOUND", details=details)


class ValidationError(PhotoshopSDKError):
    """Invalid parameter errors"""
    pass


class HandlerError(PhotoshopSDKError):
    """UXP handler execution error"""

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message, code=code or "HANDLER_ERROR", details=details)


# Error code mapping from UXP Plugin responses
ERROR_CODE_MAP: Dict[str, type] = {
    "DOCUMENT_NOT_FOUND": DocumentNotFoundError,
    "CONNECTION_FAILED": ConnectionError,
    "TIMEOUT": TimeoutError,
    "VALIDATION_ERROR": ValidationError,
    "HANDLER_ERROR": HandlerError,
}
