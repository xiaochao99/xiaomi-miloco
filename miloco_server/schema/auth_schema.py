# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Authentication related data models
Define request and response data structures for authentication module
"""

from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class UserLanguage(str, Enum):
    """User language enumeration"""
    CHINESE = "zh"
    ENGLISH = "en"


class LoginRequest(BaseModel):
    """User login request model"""
    username: str = Field(..., description="Username")
    password: str = Field(..., description="Password")


class RegisterRequest(BaseModel):
    """User registration request model"""
    password: str = Field(..., description="Admin password")


class RegisterData(BaseModel):
    """Registration response data model"""
    username: Optional[str] = Field(None, description="Username")


class LoginResponseData(BaseModel):
    """Login response data model"""
    username: str = Field(..., description="Username")
    access_token: str = Field(..., description="JWT access token for API authentication")
    token_type: str = Field("bearer", description="Token type")


class RegisterStatusData(BaseModel):
    """Registration status response data model"""
    is_registered: bool = Field(..., description="Whether already registered")


class UserLanguageData(BaseModel):
    """User language data model (for requests and responses)"""
    language: UserLanguage = Field(..., description="Language selection: zh(Chinese) or en(English)")
