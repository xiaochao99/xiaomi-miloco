# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Xiaomi Bridge Manager
Manages the lifecycle of the Xiaomi speaker bridge integration.

Coordinates: Audio Stream → VAD → KWS → ASR → Miloco → TTS

Reference: open-xiaoai-bridge/core/app.py MainApp
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional, Callable, Awaitable

from miloco_server.xiaomi_bridge.config import BridgeConfig
from miloco_server.xiaomi_bridge.conversation import MilocoConversationController, ConversationState
from miloco_server.xiaomi_bridge.vad import VADManager
from miloco_server.xiaomi_bridge.kws import KWSManager
from miloco_server.xiaomi_bridge.asr import ASRManager
from miloco_server.xiaomi_bridge.audio_stream import get_audio_stream_manager, AudioStreamManager

logger = logging.getLogger(__name__)


class BridgeManager:
    """
    Manages the Xiaomi speaker bridge integration.
    Coordinates KWS → VAD → ASR → Miloco → TTS pipeline.

    Reference: open-xiaoai-bridge MainApp
    """

    _instance: Optional[BridgeManager] = None

    def __init__(self):
        self._config = BridgeConfig()
        self._initialized = False

        # Audio components
        self._vad: Optional[VADManager] = None
        self._kws: Optional[KWSManager] = None
        self._asr: Optional[ASRManager] = None

        # Controllers
        self._conversation_controller = MilocoConversationController.instance()
        self._audio_stream_manager: Optional[AudioStreamManager] = None

        # TTS
        self._tts_speaker_id: Optional[str] = None

        # Callbacks
        self._process_text_callback: Optional[Callable[[str], Awaitable[str]]] = None

    @classmethod
    def instance(cls) -> BridgeManager:
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def is_enabled(self) -> bool:
        return self._config.enabled

    @property
    def conversation_controller(self) -> MilocoConversationController:
        return self._conversation_controller

    @property
    def vad(self) -> Optional[VADManager]:
        return self._vad

    @property
    def kws(self) -> Optional[KWSManager]:
        return self._kws

    @property
    def asr(self) -> Optional[ASRManager]:
        return self._asr

    @property
    def audio_stream_manager(self) -> Optional[AudioStreamManager]:
        return self._audio_stream_manager

    def set_process_text_callback(self, callback: Callable[[str], Awaitable[str]]):
        """Set callback for processing text with Miloco model."""
        self._process_text_callback = callback

    async def initialize(self, config: BridgeConfig | None = None):
        """Initialize the bridge manager."""
        if config is not None:
            self._config = config

        if not self._config.enabled:
            logger.info("Xiaomi bridge disabled")
            return

        logger.info("Initializing Xiaomi bridge...")

        # Initialize VAD
        self._vad = VADManager(
            model_path=self._config.vad.model_path,
            threshold=self._config.vad.threshold,
            min_speech_duration_ms=self._config.vad.min_speech_duration_ms,
            min_silence_duration_ms=self._config.vad.min_silence_duration_ms,
            sample_rate=self._config.sample_rate,
        )

        # Initialize KWS
        if self._config.kws.model_dir:
            self._kws = KWSManager(
                model_dir=self._config.kws.model_dir,
                keywords_score=self._config.kws.keywords_score,
                keywords_threshold=self._config.kws.keywords_threshold,
                sample_rate=self._config.sample_rate,
            )
            self._kws.initialize(self._config.kws.keywords)

        # Initialize ASR
        self._asr = ASRManager(
            backend=self._config.asr.model,
            model_dir=self._config.asr.model_dir,
            use_int8=self._config.asr.int8,
            num_threads=self._config.asr.num_threads,
        )
        self._asr.initialize()

        # Initialize audio stream manager
        self._audio_stream_manager = get_audio_stream_manager()
        await self._audio_stream_manager.start()

        # Connect audio stream to audio processing
        self._audio_stream_manager.set_audio_handler(self.handle_audio_frame)

        # Configure conversation controller
        async def on_tts(text: str):
            await self._speak(text)

        self._conversation_controller.set_audio_components(vad=self._vad, asr=self._asr)
        self._conversation_controller.configure(
            wakeup_keywords=self._config.kws.keywords,
            exit_keywords=self._config.exit_keywords,
            timeout=self._config.wakeup_timeout,
            process_text_callback=self._process_text_callback,
            tts_callback=on_tts,
        )

        self._initialized = True
        logger.info(
            "Xiaomi bridge initialized (tts=%s, wakeup=%s, asr=%s, ws_port=%d)",
            self._config.tts.engine,
            self._config.kws.keywords,
            self._config.asr.model,
            self._config.ws_port,
        )

    async def start(self):
        """Start the bridge."""
        if not self._config.enabled:
            return
        if not self._initialized:
            await self.initialize()
        logger.info("Xiaomi bridge started")

    async def stop(self):
        """Stop the bridge."""
        await self._conversation_controller.stop()

        if self._audio_stream_manager:
            await self._audio_stream_manager.stop()

        if self._vad:
            self._vad.reset()

        if self._kws:
            self._kws.reset()

        logger.info("Xiaomi bridge stopped")

    async def handle_audio_frame(self, audio_data: bytes):
        """
        Handle incoming audio frame from speaker microphone.
        Routes audio through VAD → KWS pipeline.

        Reference: open-xiaoai-bridge XiaoAI audio processing
        """
        if not self._config.enabled:
            return

        # Apply audio gain
        gain = self._config.audio_input.gain
        if gain != 1.0:
            import numpy as np
            samples = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32)
            samples = samples * gain
            samples = np.clip(samples, -32768, 32767).astype(np.int16)
            audio_data = samples.tobytes()

        # If conversation is active, feed to VAD
        if self._conversation_controller.is_active and self._vad:
            self._vad.process_chunk(audio_data)
            return

        # Otherwise, check for wake word via KWS
        if self._kws and self._kws.is_initialized:
            detected = self._kws.detect(audio_data)
            if detected:
                # Check if detected keyword matches any configured wakeup keyword
                matched = self._kws.is_keyword_match(detected, self._config.kws.keywords)
                if matched:
                    logger.info("Wake word detected: %s", matched)
                    self._kws.reset()
                    await self._conversation_controller.on_wakeup(matched)

    async def _speak(self, text: str):
        """Speak text through speaker (TTS)."""
        if not text:
            return

        tts_config = self._config.tts

        if tts_config.engine == "xiaoai":
            # Xiaoai native TTS - would call speaker API
            logger.info("Playing via Xiaoai TTS: %s", text[:50])
            return

        # Doubao TTS
        if not tts_config.app_id or not tts_config.access_key:
            logger.warning("Doubao TTS not configured, logging text only")
            logger.info("TTS text: %s", text[:100])
            return

        try:
            speaker_id = self._tts_speaker_id or tts_config.default_speaker

            if tts_config.stream:
                # Stream TTS playback
                await self._stream_tts(text, speaker_id, tts_config)
            else:
                # Non-streaming TTS
                await self._batch_tts(text, speaker_id, tts_config)

        except Exception as e:
            logger.error("TTS playback failed: %s", e)

    async def _stream_tts(self, text: str, speaker_id: str, config):
        """Stream TTS audio for real-time playback."""
        try:
            import httpx
            import base64

            url = "https://openspeech.bytedance.com/api/v1/tts"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer;{config.access_key}",
            }
            payload = {
                "app": {"appid": config.app_id, "token": config.access_key, "cluster": "volcano_tts"},
                "user": {"uid": "miloco_server"},
                "audio": {
                    "voice_type": speaker_id,
                    "encoding": config.audio_format,
                    "speed_ratio": config.speed,
                    "volume_ratio": 1.0,
                    "sample_rate": 24000,
                },
                "request": {"text": text, "operation": "query"},
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("code") == 0 and data.get("data"):
                        audio_data = base64.b64decode(data["data"])
                        logger.info("TTS synthesized %d bytes", len(audio_data))
                        # Send to speaker via audio stream
                        if self._audio_stream_manager:
                            await self._audio_stream_manager.broadcast_audio(audio_data)
                else:
                    logger.error("TTS HTTP error: %d", response.status_code)

        except Exception as e:
            logger.error("Stream TTS failed: %s", e)

    async def _batch_tts(self, text: str, speaker_id: str, config):
        """Batch TTS synthesis and playback."""
        await self._stream_tts(text, speaker_id, config)

    async def speak(self, text: str) -> bool:
        """
        Speak text through the speaker.
        Used for one-shot TTS playback (e.g., from API or rules).
        """
        if not text:
            return False
        await self._speak(text)
        return True

    def set_tts_speaker(self, speaker_id: str):
        """Set TTS speaker ID for voice switching."""
        self._tts_speaker_id = speaker_id

    async def send_audio_to_speaker(self, client_id: str, audio_data: bytes):
        """Send audio to a specific speaker client."""
        if self._audio_stream_manager:
            await self._audio_stream_manager.send_audio(client_id, audio_data)

    async def broadcast_audio_to_speakers(self, audio_data: bytes):
        """Broadcast audio to all connected speakers."""
        if self._audio_stream_manager:
            await self._audio_stream_manager.broadcast_audio(audio_data)


# Global singleton
_manager: Optional[BridgeManager] = None


def get_bridge_manager() -> BridgeManager:
    """Get the global bridge manager instance."""
    global _manager
    if _manager is None:
        _manager = BridgeManager.instance()
    return _manager


async def init_bridge(config: BridgeConfig | None = None):
    """Initialize the bridge from config."""
    manager = get_bridge_manager()
    await manager.initialize(config)
    await manager.start()
    return manager