# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Controller module for the Miloco project.
Contains all API route controllers for different services.
"""

from .web_controller import router as web_router
from .auth_controller import router as auth_router
from .miot_controller import router as miot_router
from .ha_controller import router as ha_router
from .chat_controller import router as chat_router
from .trigger_controller import router as trigger_router
from .model_controller import router as model_router
from .mcp_controller import router as mcp_router
from .api_token_controller import router as api_token_router
from .openai_compat_controller import router as openai_compat_router
from .detection_controller import detection_router
from .face_recognition_controller import face_recognition_router
from .xiaomi_bridge_controller import router as xiaomi_bridge_router

__all__ = [
    "web_router",
    "auth_router",
    "miot_router",
    "ha_router",
    "chat_router",
    "trigger_router",
    "model_router",
    "mcp_router",
    "api_token_router",
    "openai_compat_router",
    "detection_router",
    "face_recognition_router",
    "xiaomi_bridge_router",
]
