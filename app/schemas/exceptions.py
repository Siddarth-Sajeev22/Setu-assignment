"""Custom exceptions and error schemas."""
from pydantic import BaseModel
from typing import Optional


class APIException(Exception):
    """Base API exception."""
    def __init__(self, message: str, status_code: int = 400, detail: Optional[str] = None):
        self.message = message
        self.status_code = status_code
        self.detail = detail
        super().__init__(self.message)


class ValidationError(APIException):
    """Validation error exception."""
    def __init__(self, message: str, detail: Optional[str] = None):
        super().__init__(message, status_code=400, detail=detail)


class NotFoundError(APIException):
    """Resource not found exception."""
    def __init__(self, message: str, detail: Optional[str] = None):
        super().__init__(message, status_code=404, detail=detail)


class ConflictError(APIException):
    """Resource conflict exception."""
    def __init__(self, message: str, detail: Optional[str] = None):
        super().__init__(message, status_code=409, detail=detail)


class DatabaseError(APIException):
    """Database operation error exception."""
    def __init__(self, message: str, detail: Optional[str] = None):
        super().__init__(message, status_code=500, detail=detail)
