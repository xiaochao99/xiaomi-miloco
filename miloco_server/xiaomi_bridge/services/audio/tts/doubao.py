# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Doubao TTS implementation for Xiaomi Bridge.

Reference: open-xiaoai-bridge/core/services/tts/doubao.py
"""

import asyncio
import base64
import json

import httpx

from miloco_server.xiaomi_bridge.utils.logger import logger


class DoubaoTTS:
    """Doubao Text-to-Speech service."""

    _instance = None
    _initialized = False

    # Config
    _app_id = ""
    _access_key = ""
    _default_speaker = "zh_female_vv_uranus_bigtts"
    _audio_format = "pcm"
    _stream = True
    _speed = 1.0

    @classmethod
    def instance(cls) -> "DoubaoTTS":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        """Initialize TTS."""
        self._client = None

    @classmethod
    def set_config(
        cls,
        app_id: str = "",
        access_key: str = "",
        default_speaker: str = "zh_female_vv_uranus_bigtts",
        audio_format: str = "pcm",
        stream: bool = True,
        speed: float = 1.0,
    ):
        """Set TTS configuration."""
        cls._app_id = app_id
        cls._access_key = access_key
        cls._default_speaker = default_speaker
        cls._audio_format = audio_format
        cls._stream = stream
        cls._speed = speed

    @classmethod
    async def initialize(cls):
        """Initialize TTS service."""
        if cls._initialized:
            return

        if not cls._app_id or not cls._access_key:
            logger.warning("[TTS] Doubao TTS credentials not configured")
            cls._initialized = True
            return

        cls._instance._client = httpx.AsyncClient(timeout=30)
        cls._initialized = True
        logger.info("[TTS] Doubao TTS initialized")

    @classmethod
    async def synthesize(
        cls,
        text: str,
        speaker: str = None,
        speed: float = None,
    ) -> bytes:
        """
        Synthesize text to audio.
        
        Args:
            text: Text to synthesize
            speaker: Speaker name (optional, uses default if None)
            speed: Speech speed (optional, uses configured speed if None)
        
        Returns:
            Audio data bytes (PCM format)
        """
        if not cls._initialized:
            await cls.initialize()

        if not cls._app_id or not cls._access_key:
            logger.warning("[TTS] Doubao TTS not configured")
            return b""

        try:
            url = "https://openspeech.bytedance.net/api/text2speech"
            params = {
                "text": text,
                "speaker": speaker or cls._default_speaker,
                "audio_format": cls._audio_format,
                "speed": speed or cls._speed,
                "app_id": cls._app_id,
                "access_key": cls._access_key,
            }

            async with cls._instance._client.stream("GET", url, params=params) as response:
                if response.status_code != 200:
                    logger.error(f"[TTS] Doubao TTS API error: {response.status_code}")
                    return b""

                audio_data = b""
                async for chunk in response.aiter_bytes(chunk_size=4096):
                    audio_data += chunk

                return audio_data

        except Exception as e:
            logger.error(f"[TTS] Synthesis failed: {e}")
            return b""

    @classmethod
    async def stream_synthesize(
        cls,
        text: str,
        speaker: str = None,
        speed: float = None,
    ) -> bytes:
        """
        Stream synthesize text to audio.
        
        Args:
            text: Text to synthesize
            speaker: Speaker name (optional)
            speed: Speech speed (optional)
        
        Returns:
            Audio data bytes
        """
        return await cls.synthesize(text, speaker, speed)

    @classmethod
    def is_initialized(cls) -> bool:
        """Check if TTS is initialized."""
        return cls._initialized

    @classmethod
    def get_speakers(cls) -> list:
        """Get list of available speakers."""
        # Common Doubao speakers
        return [
            "zh_female_xiaohe_uranus_bigtts",
            "zh_female_vv_uranus_bigtts",
            "zh_male_xiaobei_uranus_bigtts",
            "zh_male_vv_uranus_bigtts",
            "zh_female_yaya_uranus_bigtts",
        ]