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

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from miloco_server.xiaomi_bridge.config import BridgeConfig
from miloco_server.xiaomi_bridge.conversation import MilocoConversationController, ConversationState
from miloco_server.xiaomi_bridge.vad import VADManager
from miloco_server.xiaomi_bridge.kws import KWSManager
from miloco_server.xiaomi_bridge.asr import ASRManager
from miloco_server.xiaomi_bridge.tts import TTSService
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
        self._tts: Optional[TTSService] = None

        # Controllers
        self._conversation_controller = MilocoConversationController.instance()
        self._audio_stream_manager: Optional[AudioStreamManager] = None

        # WebSocket server
        self._ws_server: Optional[uvicorn.Server] = None
        self._ws_server_task: Optional[asyncio.Task] = None

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
    def tts(self) -> Optional[TTSService]:
        return self._tts

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

        # Initialize TTS
        self._tts = TTSService(
            engine=self._config.tts.engine,
            app_id=self._config.tts.app_id,
            access_key=self._config.tts.access_key,
            api_key=self._config.tts.api_key,
            api_base_url=self._config.tts.api_base_url,
            default_speaker=self._config.tts.default_speaker,
            audio_format=self._config.tts.audio_format,
            stream=self._config.tts.stream,
            speed=self._config.tts.speed,
        )
        await self._tts.initialize()
        # Set singleton instance for global access
        TTSService.set_instance(self._tts)

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

        # Start WebSocket server on port 4399
        await self._start_ws_server()

        logger.info(
            "Xiaomi bridge initialized (tts=%s, wakeup=%s, asr=%s, ws_port=%d)",
            self._config.tts.engine,
            self._config.kws.keywords,
            self._config.asr.model,
            self._config.ws_port,
        )

    async def _start_ws_server(self):
        """Start the standalone WebSocket server for Xiaomi speaker connection."""
        if self._ws_server is not None:
            logger.warning("WebSocket server already running")
            return

        # Create FastAPI app for WebSocket
        ws_app = FastAPI()

        @ws_app.websocket("/")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket endpoint for Xiaomi speaker audio streaming."""
            # Generate client ID from query params or create new
            import uuid
            client_id = websocket.query_params.get("client_id", str(uuid.uuid4()))
            
            # Get device info from query params
            device_name = websocket.query_params.get("device_name", "Unknown")
            
            # Get IP address and port
            ip_address = "Unknown"
            remote_port = "Unknown"
            try:
                if hasattr(websocket.client, 'host'):
                    ip_address = websocket.client.host
                if hasattr(websocket.client, 'port'):
                    remote_port = websocket.client.port
            except Exception:
                pass

            # Get local port
            local_port = self._config.ws_port
            
            logger.info(f"[XiaoAI Bridge WS] Device connected on port {local_port}: client_id={client_id}, device_name={device_name}, ip={ip_address}, remote_port={remote_port}")

            # Register device in audio stream manager
            if self._audio_stream_manager:
                await self._audio_stream_manager.handle_connection(websocket, client_id)
            else:
                logger.error("Audio stream manager not available")
                try:
                    await websocket.close()
                except Exception:
                    pass

        # Create uvicorn server
        config = uvicorn.Config(
            ws_app,
            host=self._config.ws_host,
            port=self._config.ws_port,
            log_level="info",
            access_log=False,
        )
        self._ws_server = uvicorn.Server(config)

        # Start server in background task
        self._ws_server_task = asyncio.create_task(self._ws_server.serve())
        
        # Wait briefly for server to start
        await asyncio.sleep(0.5)
        
        # Check if server is running
        if self._ws_server.started:
            logger.info(f"[XiaoAI Bridge] Standalone WebSocket server started successfully on ws://{self._config.ws_host}:{self._config.ws_port}")
        else:
            logger.error(f"[XiaoAI Bridge] Failed to start WebSocket server on port {self._config.ws_port}")

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

        # Stop WebSocket server
        if self._ws_server:
            await self._ws_server.shutdown()
            if self._ws_server_task:
                await self._ws_server_task
            self._ws_server = None
            self._ws_server_task = None
            logger.info("WebSocket server stopped")

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

        if not self._tts or not self._tts.is_initialized:
            logger.warning("TTS service not available")
            logger.info("TTS text (not played): %s", text[:100])
            return

        try:
            await self._tts.speak(text)
            logger.info("TTS played: %s", text[:50])
        except Exception as e:
            logger.error("TTS playback failed: %s", e)

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
        # This is now handled by TTSService
        logger.warning("set_tts_speaker is deprecated, use TTSService directly")

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