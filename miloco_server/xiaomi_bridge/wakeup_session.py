# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Wakeup session management for Xiaomi Bridge.

Reference: open-xiaoai-bridge/core/wakeup_session.py
"""

import asyncio
from typing import Callable, Optional

from miloco_server.xiaomi_bridge.utils.logger import logger


class EventManager:
    """Event manager for wakeup events."""
    
    on_speech: Optional[Callable[[bytes], None]] = None
    on_silence: Optional[Callable[[], None]] = None


class WakeupSession:
    """Manages a wakeup session from keyword detection to speech capture."""

    def __init__(self):
        """Initialize wakeup session."""
        self._active = False
        self._loop = None
        self._vad_future: Optional[asyncio.Future] = None

    async def start(self) -> bytes | None:
        """
        Start wakeup session and wait for speech.
        
        Returns:
            Captured speech audio bytes, or None on timeout
        """
        from miloco_server.xiaomi_bridge.ref import get_vad
        
        vad = get_vad()
        if not vad:
            logger.error("[Wakeup] VAD not available")
            return None

        self._active = True
        self._loop = asyncio.get_running_loop()
        self._vad_future = self._loop.create_future()

        # Store original callbacks
        original_on_speech = EventManager.on_speech
        original_on_silence = EventManager.on_silence

        recording_frames: list[bytes] = []
        is_recording = False

        def _on_speech_hook(speech_buffer: bytes):
            """Handle speech detected event."""
            nonlocal is_recording
            recording_frames.append(speech_buffer)
            is_recording = True
            logger.debug("[Wakeup] Speech detected, starting recording")
            vad.resume("silence")

        def _on_silence_hook():
            """Handle silence detected event."""
            nonlocal is_recording
            is_recording = False
            logger.debug("[Wakeup] Silence detected, stopping recording")
            if self._vad_future and not self._vad_future.done():
                self._loop.call_soon_threadsafe(
                    self._vad_future.set_result, b"".join(recording_frames)
                )

        # Set up hooks
        EventManager.on_speech = _on_speech_hook
        EventManager.on_silence = _on_silence_hook

        try:
            # Get timeout from config
            from miloco_server.xiaomi_bridge.utils.config import ConfigManager
            config = ConfigManager.instance()
            timeout = config.get_app_config("wakeup.timeout", 20)

            vad.resume("speech")
            result = await asyncio.wait_for(self._vad_future, timeout=timeout)
            return result

        except asyncio.TimeoutError:
            logger.debug("[Wakeup] Wakeup timeout, no speech detected")
            vad.pause()
            return None

        finally:
            # Restore original callbacks
            EventManager.on_speech = original_on_speech
            EventManager.on_silence = original_on_silence
            self._vad_future = None
            self._active = False

    def stop(self):
        """Stop wakeup session."""
        if self._vad_future and not self._vad_future.done():
            self._loop.call_soon_threadsafe(self._vad_future.cancel)
        self._active = False

    def is_active(self) -> bool:
        """Check if session is active."""
        return self._active