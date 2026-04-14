# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Audio stream handler for Xiaomi Bridge.

Reference: open-xiaoai-bridge/core/services/audio/stream.py
"""

import asyncio
import threading
from typing import Callable, Optional, Set

from miloco_server.xiaomi_bridge.utils.logger import logger


class AudioStreamHandler:
    """Audio stream handler for managing audio input/output."""

    _instance = None
    _running = False
    _lock = threading.Lock()

    # Audio callbacks
    _on_audio_input: Optional[Callable[[bytes], None]] = None

    # Output buffers
    _output_buffer = b""
    _output_event = asyncio.Event()

    @classmethod
    def instance(cls) -> "AudioStreamHandler":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        """Initialize audio stream handler."""
        self._loop = None

    @classmethod
    def start(cls):
        """Start audio stream handler."""
        if cls._running:
            return

        cls._running = True
        cls._output_buffer = b""
        cls._loop = asyncio.new_event_loop()
        logger.info("[Audio Stream] Audio stream handler started")

    @classmethod
    def stop(cls):
        """Stop audio stream handler."""
        cls._running = False
        cls._output_buffer = b""
        logger.info("[Audio Stream] Audio stream handler stopped")

    @classmethod
    def set_audio_input_callback(cls, callback: Callable[[bytes], None]):
        """Set callback for audio input."""
        cls._on_audio_input = callback

    @classmethod
    def process_audio_input(cls, audio_data: bytes):
        """
        Process incoming audio data.
        
        Args:
            audio_data: PCM audio bytes (int16, 16kHz, mono)
        """
        if not cls._running:
            return

        # Apply gain if configured
        from miloco_server.xiaomi_bridge.utils.config import ConfigManager
        config = ConfigManager.instance()
        gain = config.get_app_config("audio.input_gain", 1.0)
        
        if gain != 1.0:
            import numpy as np
            samples = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32)
            samples = samples * gain
            samples = np.clip(samples, -32768, 32767).astype(np.int16)
            audio_data = samples.tobytes()

        # Call callback if set
        if cls._on_audio_input:
            try:
                cls._on_audio_input(audio_data)
            except Exception as e:
                logger.error(f"[Audio Stream] Audio input callback error: {e}")

    @classmethod
    async def play_audio(cls, audio_data: bytes):
        """
        Queue audio data for playback.
        
        Args:
            audio_data: PCM audio bytes to play
        """
        if not cls._running:
            return

        cls._output_buffer += audio_data
        cls._output_event.set()

    @classmethod
    def is_running(cls) -> bool:
        """Check if audio stream handler is running."""
        return cls._running