# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Authentication controller
Handles user authentication, registration, and language settings
"""

from fastapi import APIRouter, Response
from miloco_server.service.manager import get_manager
from miloco_server.schema.auth_schema import LoginRequest, RegisterRequest, UserLanguageData
from miloco_server.schema.common_schema import NormalResponse
import logging

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/auth", tags=["authentication"])

manager = get_manager()

# Registration interface
@router.post("/register", summary="Admin registration", response_model=NormalResponse)
async def register(register_data: RegisterRequest):
    """Admin registration interface"""
    data = manager.auth_service.register_admin_user(register_data)
    return NormalResponse(
        code=0,
        message="Admin registration successful",
        data=data
    )

# Check registration status interface
@router.get("/register-status", summary="Check registration status", response_model=NormalResponse)
async def check_register_status():
    """Check if admin is registered"""
    data = manager.auth_service.check_register_status()
    return NormalResponse(
        code=0,
        message="Admin registered" if data.is_registered else "Admin not registered",
        data=data
    )

# Login interface
@router.post("/login", summary="User login", response_model=NormalResponse)
async def login(login_data: LoginRequest, response: Response):
    """
    User login interface
    - Verify username and password
    - Set JWT access token to Cookie
    """
    data = manager.auth_service.login_user(login_data, response)
    return NormalResponse(
        code=0,
        message="Login successful",
        data=data
    )

# Logout interface
@router.get("/logout", summary="User logout", response_model=NormalResponse)
async def logout(response: Response):
    """User logout, clear Cookie and invalidate all tokens"""
    manager.auth_service.logout_user(response)
    return NormalResponse(
        code=0,
        message="Logout successful"
    )

# Get user language interface
@router.get("/language", summary="Get user language setting", response_model=NormalResponse)
async def get_user_language():
    """Get current user language setting"""
    data = manager.auth_service.get_user_language()
    return NormalResponse(
        code=0,
        message="User language settings retrieved successfully",
        data=data
    )

# Set user language interface
@router.post("/language", summary="Set user language", response_model=NormalResponse)
async def set_user_language(language_request: UserLanguageData):
    """Set user language preference"""
    data = manager.auth_service.set_user_language(language_request)
    return NormalResponse(
        code=0,
        message="User language settings updated successfully",
        data=data
    )


