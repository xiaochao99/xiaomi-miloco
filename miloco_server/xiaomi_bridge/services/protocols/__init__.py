# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Protocol services module.

Reference: open-xiaoai-bridge/core/services/protocols/__init__.py
"""

from miloco_server.xiaomi_bridge.services.protocols.websocket_protocol import WebSocketProtocol
from miloco_server.xiaomi_bridge.services.protocols.typing import DeviceState, EventType, MessageType, VoiceMessage, StreamInfo

__all__ = [
    "WebSocketProtocol",
    "DeviceState",
    "EventType",
    "MessageType",
    "VoiceMessage",
    "StreamInfo",
]