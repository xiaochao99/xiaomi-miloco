# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
TTS (Text-to-Speech) module for Xiaomi Bridge.
Supports Doubao TTS and Xiaomi native TTS.

Reference: open-xiaoai-bridge/core/services/tts/doubao.py
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class TTSService:
    """
    TTS service for Xiaomi bridge.
    Supports Doubao (火山引擎) TTS.
    """

    def __init__(
        self,
        engine: str = "doubao",
        app_id: str = "",
        access_key: str = "",
        default_speaker: str = "zh_female_vv_uranus_bigtts",
        audio_format: str = "pcm",
        stream: bool = True,
        speed: float = 1.0,
    ):
        self._engine = engine
        self._app_id = app_id
        self._access_key = access_key
        self._default_speaker = default_speaker
        self._audio_format = audio_format
        self._stream = stream
        self._speed = speed
        self._initialized = False
        self._client = None

    async def initialize(self):
        """Initialize TTS service."""
        if self._engine == "doubao":
            if not self._app_id or not self._access_key:
                logger.warning("Doubao TTS credentials not configured")
                return False
            
            self._client = httpx.AsyncClient(timeout=30)
            self._initialized = True
            logger.info("TTS service initialized: %s", self._engine)
            return True
        
        logger.warning("Unsupported TTS engine: %s", self._engine)
        return False

    async def synthesize(self, text: str, speaker: str = None) -> bytes:
        """
        Synthesize text to audio.
        
        Args:
            text: Text to synthesize
            speaker: Speaker name (optional, uses default if None)
        
        Returns:
            Audio data bytes (PCM format)
        """
        if not self._initialized:
            logger.error("TTS service not initialized")
            return b""

        try:
            if self._engine == "doubao":
                return await self._synthesize_doubao(text, speaker)
        except Exception as e:
            logger.error("TTS synthesis failed: %s", e)
        
        return b""

    async def _synthesize_doubao(self, text: str, speaker: str = None) -> bytes:
        """Synthesize using Doubao TTS API."""
        url = "https://openspeech.bytedance.net/api/text2speech"
        
        params = {
            "text": text,
            "speaker": speaker or self._default_speaker,
            "audio_format": self._audio_format,
            "speed": self._speed,
            "app_id": self._app_id,
            "access_key": self._access_key,
        }

        async with self._client.stream("GET", url, params=params) as response:
            if response.status_code != 200:
                logger.error("Doubao TTS API error: %d", response.status_code)
                return b""
            
            audio_data = b""
            async for chunk in response.aiter_bytes(chunk_size=4096):
                audio_data += chunk
            
            return audio_data

    async def speak(self, text: str, speaker: str = None) -> bool:
        """
        Synthesize and play text via audio stream.
        
        Args:
            text: Text to speak
            speaker: Speaker name (optional)
        
        Returns:
            True if successful, False otherwise
        """
        audio_data = await self.synthesize(text, speaker)
        if not audio_data:
            return False

        # Send audio to connected speaker via WebSocket
        from miloco_server.xiaomi_bridge.audio_stream import get_audio_stream_manager
        stream_manager = get_audio_stream_manager()
        await stream_manager.send_audio_to_clients(audio_data)
        
        return True

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    @property
    def engine(self) -> str:
        return self._engine