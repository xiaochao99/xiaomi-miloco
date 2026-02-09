# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Unified exception handling middleware
Provides exception handling mechanisms:
1. HTTP middleware: Intercepts all HTTP request exceptions
2. WebSocket exception handling: Handles WebSocket connection exceptions
3. Global handler: Handles all types of exceptions
"""
import logging
from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError, HTTPException as FastAPIHTTPException
from miloco_server.middleware.exceptions import BaseAPIException
from miloco_server.schema.common_schema import NormalResponse

logger = logging.getLogger(__name__)


SYSTEM_ERROR_CODE = 9000


def _create_error_response(status_code: int, code: int, message: str, data=None) -> JSONResponse:
    """
    Create unified error response
    
    Args:
        status_code: HTTP status code
        code: Business error code
        message: Error message
        data: Optional additional data
        
    Returns:
        JSONResponse: Formatted error response
    """
    response_data = NormalResponse(
        code=code,
        message=message,
        data=data
    )
    return JSONResponse(
        status_code=status_code,
        content=response_data.model_dump()
    )



def _handle_base_api_exception(exc: BaseAPIException) -> JSONResponse:
    """
    Common method for handling BaseAPIException
    
    Args:
        exc: BaseAPIException exception object
        
    Returns:
        JSONResponse: Error response
    """
    logger.error("Request failed - %s: %s", type(exc).__name__, exc.message, exc_info=True)

    return _create_error_response(
        status_code=exc.http_status,
        code=exc.code,
        message=exc.message
    )


def handle_exception(request: Request, exc: Exception) -> JSONResponse:  # pylint: disable=unused-argument
    """
    Unified exception handling function - handles all exceptions
    
    This function handles:
    - RequestValidationError (Pydantic validation errors)
    - Custom API exceptions (authentication, authorization, business exceptions, etc.)
    - FastAPI HTTPException
    - Other system-level exceptions
    
    Args:
        exc: Exception object
        request: FastAPI request object
        
    Returns:
        JSONResponse: Unified error response
    """
    # 1. Special handling for RequestValidationError (Pydantic validation errors)
    if isinstance(exc, RequestValidationError):
        logger.warning("Request validation failed: %s", exc)
        return _create_error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code=1002,  # Parameter validation failure error code, consistent with ValidationException
            message="Request parameter validation failed",
            data=exc.errors()
        )

    # 2. Handle other custom API exceptions
    if isinstance(exc, BaseAPIException):
        return _handle_base_api_exception(exc)

    # 3. Handle FastAPI HTTPException (fallback handling)
    if isinstance(exc, FastAPIHTTPException):
        logger.warning("FastAPI HTTP error - %s: %s", exc.status_code, exc.detail)
        return _create_error_response(
            status_code=exc.status_code,
            code=1000,  # General HTTP error code, consistent with HTTPException base class
            message=str(exc.detail)
        )

    # 4. Handle other exceptions (system exceptions) - final fallback
    exc_type = type(exc)
    logger.error("Unhandled system error - %s: %s", exc_type.__name__, str(exc), exc_info=True)
    return _create_error_response(
        status_code=500,
        code=SYSTEM_ERROR_CODE,
        message="Internal server error " + exc_type.__name__ + ": " + str(exc)
    )

