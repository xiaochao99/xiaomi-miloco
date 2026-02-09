# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Exception definitions
Provides unified exception handling mechanism, distinguishing HTTP exceptions and business exceptions
"""

from fastapi import status


class BaseAPIException(Exception):
    """Base API exception class"""
    def __init__(self, message: str, code: int, http_status: int = status.HTTP_200_OK):
        self.message = message
        self.code = code
        self.http_status = http_status
        super().__init__(self.message)



class BusinessException(BaseAPIException):
    """Base business exception class - returns 500 + business error code 2000+"""
    def __init__(self, message: str, code: int = 2000):
        super().__init__(message, code, http_status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ModelManagerException(BusinessException):
    """Resource not found exception - 2001"""
    def __init__(self, message: str):
        super().__init__(message, code=2001)


class ModelSchedulerException(BusinessException):
    """Resource conflict exception (such as name duplication, etc.) - 2002"""
    def __init__(self, message: str):
        super().__init__(message, code=2002)


class CoreNormalException(BusinessException):
    """External service exception - 3000"""

    def __init__(self, message: str):
        super().__init__(message, code=3000)

class CoreResponeException(BusinessException):
    """External service exception - 3000"""
    def __init__(self, message: str):
        super().__init__(message, code=3001)


class InvalidArgException(BusinessException):
    """LLM service exception - 3100"""
    def __init__(self, message: str):
        super().__init__(message)
        self.code = 3100
