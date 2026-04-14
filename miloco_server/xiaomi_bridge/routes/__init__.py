# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
API routes module for Xiaomi Bridge.

Reference: open-xiaoai-bridge/core/routes/__init__.py
"""

from miloco_server.xiaomi_bridge.routes.websocket import websocket_router
from miloco_server.xiaomi_bridge.routes.api import api_router

__all__ = [
    "websocket_router",
    "api_router",
]