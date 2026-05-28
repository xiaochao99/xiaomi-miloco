# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
NVR RecordEngine Module

A high-performance, zero-copy recording engine for Miloco NVR/DVR systems.
Uses PyAV for direct muxing without re-encoding, supporting streaming write
and multi-channel concurrent recording.

Features:
- Zero-copy recording (no re-encoding)
- Streaming write (no memory buffering)
- Multi-channel concurrent recording
- Embedded/edge device friendly
- Keyframe-aligned segment rotation
- Pre-recording buffer support
"""

from .engine import RecordEngine, get_record_engine, init_record_engine
from .channel import ChannelRecorder
from .storage import StorageManager

__all__ = [
    "RecordEngine",
    "ChannelRecorder",
    "StorageManager",
    "get_record_engine",
    "init_record_engine",
]
