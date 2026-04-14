# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Type definitions for protocols.

Reference: open-xiaoai-bridge/core/services/protocols/typing.py
"""

from enum import Enum
from typing import Dict, Any, Optional


class DeviceState(Enum):
    """Device connection states."""
    IDLE = "idle"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"


class EventType(Enum):
    """Event types."""
    SCHEDULE_EVENT = "schedule"
    AUDIO_INPUT_READY_EVENT = "audio_input_ready"
    WAKEUP_EVENT = "wakeup"
    SPEECH_DETECTED_EVENT = "speech_detected"
    TTS_COMPLETE_EVENT = "tts_complete"


class MessageType(Enum):
    """WebSocket message types."""
    REQUEST = "req"
    RESPONSE = "res"
    EVENT = "event"


class VoiceMessage:
    """Voice message data."""
    
    def __init__(
        self,
        text: str = "",
        confidence: float = 0.0,
        is_final: bool = False,
        audio_data: bytes = b"",
    ):
        self.text = text
        self.confidence = confidence
        self.is_final = is_final
        self.audio_data = audio_data


class StreamInfo:
    """Audio stream information."""
    
    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        format: str = "pcm",
        bit_depth: int = 16,
    ):
        self.sample_rate = sample_rate
        self.channels = channels
        self.format = format
        self.bit_depth = bit_depth

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "sample_rate": self.sample_rate,
            "channels": self.channels,
            "format": self.format,
            "bit_depth": self.bit_depth,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StreamInfo":
        """Create from dictionary."""
        return cls(
            sample_rate=data.get("sample_rate", 16000),
            channels=data.get("channels", 1),
            format=data.get("format", "pcm"),
            bit_depth=data.get("bit_depth", 16),
        )