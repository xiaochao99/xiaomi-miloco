# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
TTS (Text-to-Speech) module for Xiaomi Bridge.
Supports Doubao TTS and Xiaomi native TTS.

Reference: open-xiaoai-bridge/core/services/tts/doubao.py
           open-xiaoai-bridge/core/services/tts/xiaoai.py
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Optional, AsyncIterator

import httpx

logger = logging.getLogger(__name__)


class TTSService:
    """
    TTS service for Xiaomi bridge.
    Supports Doubao (火山引擎) TTS and Xiaomi native TTS.
    """

    _instance = None

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

    @classmethod
    def instance(cls):
        """Get singleton instance of TTSService."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def set_instance(cls, instance: "TTSService"):
        """Set singleton instance."""
        cls._instance = instance

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
        
        elif self._engine == "xiaoai":
            # Xiaomi native TTS doesn't require initialization
            # It sends text directly to the speaker via WebSocket
            self._initialized = True
            logger.info("TTS service initialized: %s (native)", self._engine)
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
            Audio data bytes (PCM format), or text payload for xiaoai engine
        """
        if not self._initialized:
            logger.error("TTS service not initialized")
            return b""

        try:
            if self._engine == "doubao":
                return await self._synthesize_doubao(text, speaker)
            
            elif self._engine == "xiaoai":
                # For xiaoai engine, return the text wrapped in a special format
                # This will be handled by the speak method
                return text.encode('utf-8')
        except Exception as e:
            logger.error("TTS synthesis failed: %s", e)
        
        return b""

    async def synthesize_stream(self, text: str, speaker: str = None) -> AsyncIterator[bytes]:
        """
        Stream-synthesize text to audio chunks.

        For Doubao engine this yields PCM chunks as they arrive from the upstream API.
        For xiaoai engine this yields nothing (native TTS is command-based).
        """
        if not self._initialized:
            logger.error("TTS service not initialized")
            return

        if self._engine == "doubao":
            async for chunk in self._synthesize_doubao_stream(text, speaker):
                if chunk:
                    yield chunk
            return

        # xiaoai: no audio stream available from server side
        return

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

    async def _synthesize_doubao_stream(self, text: str, speaker: str = None) -> AsyncIterator[bytes]:
        """Stream audio chunks from Doubao TTS API."""
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
                return

            async for chunk in response.aiter_bytes(chunk_size=4096):
                if chunk:
                    yield chunk

    async def speak(self, text: str, speaker: str = None) -> bool:
        """
        Synthesize and play text via audio stream.
        
        Args:
            text: Text to speak
            speaker: Speaker name (optional)
        
        Returns:
            True if successful, False otherwise
        """
        if self._engine == "xiaoai":
            # For xiaoai engine, send text directly via WebSocket
            return await self._speak_xiaoai(text)
        
        audio_data = await self.synthesize(text, speaker)
        if not audio_data:
            return False

        # Send audio to connected speaker via WebSocket
        from miloco_server.xiaomi_bridge.audio_stream import get_audio_stream_manager
        stream_manager = get_audio_stream_manager()
        await stream_manager.send_audio_to_clients(audio_data)
        
        return True

    async def speak_stream(self, text: str, speaker: str = None, client_ids: Optional[list[str]] = None) -> bool:
        """
        Stream-synthesize and immediately forward audio chunks to connected Xiaomi speakers.
        """
        if self._engine == "xiaoai":
            # Native TTS is not an audio streaming API.
            return await self._speak_xiaoai(text)

        if not self._initialized:
            ok = await self.initialize()
            if not ok:
                return False

        try:
            from miloco_server.xiaomi_bridge.audio_stream import get_audio_stream_manager
            stream_manager = get_audio_stream_manager()
            sent_any = False
            async for chunk in self.synthesize_stream(text, speaker):
                sent_any = True
                await stream_manager.send_audio_to_clients(chunk, client_ids)
            return sent_any
        except Exception as e:
            logger.error("Stream TTS speak failed: %s", e, exc_info=True)
            return False

    async def _speak_xiaoai(self, text: str) -> bool:
        """
        Speak text using Xiaomi native TTS.
        Sends run_shell command to trigger TTS on the speaker via WebSocket.
        
        Args:
            text: Text to speak
        
        Returns:
            True if successful, False otherwise
        """
        try:
            from miloco_server.xiaomi_bridge.audio_stream import get_audio_stream_manager
            from miloco_server.xiaomi_bridge.shell_utils import build_mibrain_tts_script
            stream_manager = get_audio_stream_manager()

            # Send via open-xiaoai client-rust RPC
            await stream_manager.run_shell(build_mibrain_tts_script(text))
            logger.info("Sent TTS text to Xiaomi speaker: %s", text[:50])
            return True
            
        except Exception as e:
            logger.error("XiaoAI TTS failed: %s", e)
            return False

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    @property
    def engine(self) -> str:
        return self._engine