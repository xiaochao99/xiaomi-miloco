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
import os
import time
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
from miloco_server.utils.speech_plain_text import plain_text_for_tts

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

        # Avoid triggering KWS during our own TTS playback.
        self._tts_playing: bool = False
        # After resume_recording, ignore mic briefly (DAC/room tail still audible).
        self._playback_tail_suppress_until: float = 0.0
        # Last TTS plain text (for ASR echo guard in conversation path).
        self._last_played_tts_plain: str = ""
        self._last_played_tts_at: float = 0.0
        # When MILOCO_TTS_WAIT_CLIENT_PLAYBACK_DRAIN=1, client must send Event playback_drained.
        self._playback_drain_events: Optional[dict[str, asyncio.Event]] = None

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

    def get_default_process_text_callback(self) -> Optional[Callable[[str], Awaitable[str]]]:
        """
        Get the default process_text_callback used by the built-in Miloco flow.
        Wake-up flows may temporarily override it and should restore afterwards.
        """
        return self._process_text_callback

    def restore_conversation_default_process_text_callback(self):
        """Restore conversation controller callback to the bridge default."""
        if self._process_text_callback:
            self._conversation_controller.configure(
                process_text_callback=self._process_text_callback,
                timeout=self._config.wakeup_timeout,
                single_turn=False
            )

    def _create_default_miloco_callback(self) -> Callable[[str], Awaitable[str]]:
        """Create default Miloco AI chat callback using APIChatAdapter."""
        from miloco_server.service.ai_chat_adapter import APIChatAdapter, parse_ai_response
        import uuid

        async def process_miloco_text(text: str) -> str:
            """Process text using Miloco AI chat interface."""
            request_id = str(uuid.uuid4())
            chat_adapter = APIChatAdapter(request_id)

            try:
                response_text = ""
                async for message in chat_adapter.process_query(
                    query=text,
                    camera_ids=[],
                    mcp_list=None  # Use all available MCP services
                ):
                    if message["type"] == "complete":
                        response_text = message["data"].get("response", "")
                        break

                # Extract only <final_answer> content
                parsed_response = parse_ai_response(response_text)
                final_answer = parsed_response.get("final_answer", "").strip()

                if final_answer:
                    logger.info("Miloco response (final_answer): %s", final_answer[:50])
                    return final_answer
                else:
                    logger.warning("No <final_answer> found in response")
                    return ""

            except Exception as e:
                logger.error("Miloco callback error: %s", e)
                return ""

        return process_miloco_text

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
            mimo_tts_model=self._config.tts.mimo_tts_model,
            voice_design_description=self._config.tts.voice_design_description,
        )
        await self._tts.initialize()
        # Set singleton instance for global access
        TTSService.set_instance(self._tts)

        # Initialize audio stream manager
        self._audio_stream_manager = get_audio_stream_manager()
        await self._audio_stream_manager.start()

        # Connect audio stream to audio processing
        self._audio_stream_manager.set_audio_handler(self.handle_audio_frame)
        self._audio_stream_manager.set_playback_drained_handler(self._on_client_playback_drained)

        # Configure conversation controller
        async def on_tts(text: str):
            await self._speak(text)

        # Set default AI chat callback if not provided
        if not self._process_text_callback:
            self._process_text_callback = self._create_default_miloco_callback()

        self._conversation_controller.set_audio_components(vad=self._vad, asr=self._asr)
        self._conversation_controller.configure(
            wakeup_keywords=self._config.kws.keywords,
            exit_keywords=self._config.exit_keywords,
            timeout=self._config.wakeup_timeout,
            process_text_callback=self._process_text_callback,
            tts_callback=on_tts,
            wakeup_opening_reply=self._config.wakeup_opening_reply,
        )

        self._initialized = True

        # Start WebSocket server on port 4399
        await self._start_ws_server()

        logger.info(
            "Xiaomi bridge initialized (tts=%s, wakeup=%s, asr=%s, ws_port=%d, opening_reply=%s)",
            self._config.tts.engine,
            self._config.kws.keywords,
            self._config.asr.model,
            self._config.ws_port,
            bool((self._config.wakeup_opening_reply or "").strip()),
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
        # Avoid a stuck TTS flag blocking KWS/VAD across restarts or partial failures.
        self._tts_playing = False
        self._playback_tail_suppress_until = 0.0
        logger.info("Xiaomi bridge started")

    async def stop(self):
        """Stop the bridge."""
        try:
            await self._conversation_controller.stop()
        except Exception as e:
            logger.warning(f"Failed to stop conversation controller: {e}")

        # Stop WebSocket server with timeout
        if self._ws_server:
            try:
                # Shutdown with timeout to prevent hanging
                shutdown_task = asyncio.create_task(self._ws_server.shutdown())
                await asyncio.wait_for(shutdown_task, timeout=5.0)
            except asyncio.TimeoutError:
                logger.error("WebSocket server shutdown timeout, forcing stop")
                self._ws_server = None
            except Exception as e:
                logger.warning(f"Failed to shutdown WebSocket server: {e}")
            
            if self._ws_server_task:
                try:
                    await asyncio.wait_for(self._ws_server_task, timeout=5.0)
                except (asyncio.TimeoutError, Exception) as e:
                    logger.warning(f"Failed to wait for WebSocket server task: {e}")
                self._ws_server_task = None
            
            self._ws_server = None
            logger.info("WebSocket server stopped")

        if self._audio_stream_manager:
            try:
                await self._audio_stream_manager.stop()
            except Exception as e:
                logger.warning(f"Failed to stop audio stream manager: {e}")

        if self._vad:
            self._vad.reset()

        if self._kws:
            self._kws.reset()

        logger.info("Xiaomi bridge stopped")

    def _on_client_playback_drained(self, client_id: str) -> None:
        pending = self._playback_drain_events
        if pending and client_id in pending:
            pending[client_id].set()
            logger.info("Client reported playback_drained: %s", client_id)

    async def _await_client_playback_drain(
        self,
        client_ids: Optional[list[str]],
        timeout_s: float,
    ) -> bool:
        """Wait until each target client sends one playback_drained Event (or timeout)."""
        mgr = self._audio_stream_manager
        if not mgr:
            return False
        if client_ids:
            ids = list(client_ids)
        else:
            ids = list(mgr.connected_clients)
        if not ids:
            return True
        events = {cid: asyncio.Event() for cid in ids}
        self._playback_drain_events = events
        try:
            tasks = [asyncio.create_task(events[cid].wait()) for cid in ids]
            done, pending_tasks = await asyncio.wait(tasks, timeout=timeout_s)
            for t in pending_tasks:
                t.cancel()
            ok = all(ev.is_set() for ev in events.values())
            if not ok:
                logger.warning(
                    "playback_drained incomplete: %s/%s clients within %.1fs",
                    sum(1 for ev in events.values() if ev.is_set()),
                    len(ids),
                    timeout_s,
                )
            return ok
        finally:
            self._playback_drain_events = None

    async def handle_audio_frame(self, audio_data: bytes):
        """
        Handle incoming audio frame from speaker microphone.
        Routes audio through VAD → KWS pipeline.

        Reference: open-xiaoai-bridge XiaoAI audio processing
        """
        if not self._config.enabled:
            return

        if time.monotonic() < self._playback_tail_suppress_until:
            return

        # Apply audio gain
        gain = self._config.audio_input.gain
        if gain != 1.0:
            import numpy as np
            samples = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32)
            samples = samples * gain
            samples = np.clip(samples, -32768, 32767).astype(np.int16)
            audio_data = samples.tobytes()

        # If conversation is active, feed to VAD only while waiting for user speech (LISTENING).
        # Do NOT gate on _tts_playing here: it can lag state transitions and starve VAD entirely
        # (symptom: wake works once then never hears commands / appears "can't wake").
        # Echo from speaker is mainly during SPEAKING; skip VAD for PROCESSING/SPEAKING.
        if self._conversation_controller.is_active and self._vad:
            st = self._conversation_controller.state
            if st in (ConversationState.PROCESSING, ConversationState.SPEAKING):
                return
            self._vad.process_chunk(audio_data)
            return

        # Otherwise, check for wake word via KWS
        # If we are currently speaking (TTS playback), ignore microphone frames for wake word.
        if self._tts_playing:
            return
        if self._kws and self._kws.is_initialized:
            detected = self._kws.detect(audio_data)
            if detected:
                # Check if detected keyword matches any configured wakeup keyword
                matched = self._kws.is_keyword_match(detected, self._config.kws.keywords)
                if matched:
                    logger.info("Wake word detected: %s", matched)
                    self._kws.reset()
                    # Must NOT await on_wakeup/start here: _process_audio awaits this handler
                    # sequentially; awaiting would block all further mic frames and VAD would
                    # never run → permanent 20s timeout. Run conversation in a background task.
                    asyncio.create_task(self._conversation_controller.on_wakeup(matched))

    async def _speak(self, text: str, client_ids: Optional[list[str]] = None):
        """
        Speak text through speaker (TTS).

        open-xiaoai-client: pause peer recording during playback so the mic path
        does not capture self-playback (especially stream tail). See stop_recording
        / start_recording in client-rust protocol.
        """
        if not text:
            return

        text = plain_text_for_tts(text)
        if not text:
            logger.warning("TTS text empty after plain-text normalization; skip playback")
            return

        if not self._tts or not self._tts.is_initialized:
            logger.warning("TTS service not available")
            logger.info("TTS text (not played): %s", text[:100])
            return

        pause_mic = os.getenv("MILOCO_PAUSE_RECORDING_DURING_TTS", "1").strip().lower() in (
            "1", "true", "yes", "on",
        )
        wait_client_drain = os.getenv("MILOCO_TTS_WAIT_CLIENT_PLAYBACK_DRAIN", "0").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        client_drain_timeout_s = float(os.getenv("MILOCO_CLIENT_PLAYBACK_DRAIN_TIMEOUT_S", "30"))
        # speak() returns when uplink has finished *sending* PCM; the device still has ring
        # buffer + transducer tail. Extra drain avoids mic reopening during audible tail.
        post_play_drain_ms = int(os.getenv("MILOCO_TTS_POST_PLAY_DRAIN_MS", "1100"))
        resume_delay_ms = int(os.getenv("MILOCO_TTS_RESUME_RECORDING_DELAY_MS", "550"))
        tail_ignore_ms = int(os.getenv("MILOCO_PLAYBACK_TAIL_IGNORE_MS", "1000"))
        after_stop_ms = int(os.getenv("MILOCO_AFTER_STOP_RECORDING_MS", "40"))
        # Client-reported drain replaces most fixed server sleep when enabled.
        effective_post_drain_ms = 0 if (pause_mic and wait_client_drain) else post_play_drain_ms

        tts_plain_recorded = False
        try:
            self._tts_playing = True
            if self._audio_stream_manager and pause_mic:
                try:
                    await self._audio_stream_manager.pause_recording_for_playback(client_ids)
                    if after_stop_ms > 0:
                        await asyncio.sleep(after_stop_ms / 1000.0)
                except Exception as e:
                    logger.warning("pause_recording_for_playback: %s", e)
            await self._tts.speak(text, client_ids=client_ids)
            if pause_mic and wait_client_drain:
                drained = await self._await_client_playback_drain(client_ids, client_drain_timeout_s)
                if not drained:
                    logger.warning(
                        "playback_drained wait timed out or incomplete; continuing to resume mic"
                    )
            elif pause_mic and effective_post_drain_ms > 0:
                await asyncio.sleep(effective_post_drain_ms / 1000.0)
            self._last_played_tts_plain = text
            tts_plain_recorded = True
            logger.info("TTS played: %s", text[:50])
        except Exception as e:
            logger.error("TTS playback failed: %s", e)
        finally:
            self._tts_playing = False
            try:
                if pause_mic and resume_delay_ms > 0:
                    await asyncio.sleep(resume_delay_ms / 1000.0)
                if self._audio_stream_manager and pause_mic:
                    await self._audio_stream_manager.resume_recording_after_playback(client_ids)
            except Exception as e:
                logger.warning("resume_recording_after_playback: %s", e)
            if tail_ignore_ms > 0:
                self._playback_tail_suppress_until = time.monotonic() + tail_ignore_ms / 1000.0
            # Filler/echo guards in conversation use time since uplink is accepting mic again.
            if tts_plain_recorded:
                self._last_played_tts_at = time.monotonic()

    async def speak(self, text: str, client_ids: Optional[list[str]] = None) -> bool:
        """
        Speak text through the speaker.
        Used for one-shot TTS playback (e.g., from API or rules).
        """
        if not text:
            return False
        await self._speak(text, client_ids=client_ids)
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

    async def play_tts(
        self,
        text: str,
        device_ids: list[str] | None = None,
        speaker_id: str | None = None
    ) -> bool:
        """
        Play TTS text to specified devices or all devices.

        Args:
            text: Text to speak
            device_ids: Target device IDs (None for all devices)
            speaker_id: Speaker ID for voice selection

        Returns:
            True if playback started successfully
        """
        if not text:
            return False

        try:
            if speaker_id and self._tts:
                original_speaker = self._tts._default_speaker
                self._tts._default_speaker = speaker_id

            await self._speak(text, client_ids=device_ids)

            if speaker_id and self._tts:
                self._tts._default_speaker = original_speaker

            logger.info(f"[BridgeManager] TTS played: {text[:50]}...")
            return True

        except Exception as e:
            logger.error(f"[BridgeManager] TTS playback failed: {e}")
            return False

    async def play_tts_async(
        self,
        text: str,
        device_ids: list[str] | None = None,
        callback: Callable[[dict], None] | None = None
    ) -> bool:
        """
        Play TTS asynchronously with completion callback.

        Args:
            text: Text to speak
            device_ids: Target device IDs (None for all devices)
            callback: Completion callback

        Returns:
            True if playback started
        """
        async def _play_with_callback():
            try:
                await self.play_tts(text, device_ids)
                if callback:
                    callback({"type": "complete", "success": True})
            except Exception as e:
                if callback:
                    callback({"type": "complete", "success": False, "error": str(e)})

        asyncio.create_task(_play_with_callback())
        return True

    async def start_wakeup_listening(
        self,
        session_id: str,
        callback: Callable[[dict], None] | None = None
    ) -> bool:
        """
        Start wakeup keyword listening for a session.

        Args:
            session_id: Session identifier
            callback: Callback when wakeup is detected

        Returns:
            True if listening started
        """
        logger.info(f"[BridgeManager] Starting wakeup listening for session {session_id}")

        try:
            if self._kws and self._kws.is_initialized:
                self._kws.reset()

            # NOTE: The conversation controller in this repo uses a continuous VAD/ASR loop
            # started via `start()`. Older `start_wakeup_mode/stop_wakeup_mode` methods do not exist.
            # To avoid runtime crash, run `start()` in background here.
            if not self._conversation_controller.is_active:
                asyncio.create_task(self._conversation_controller.start())

            # callback is not wired in current implementation; keep for forward compatibility.
            if callback:
                pass

            return True

        except Exception as e:
            logger.error(f"[BridgeManager] Start wakeup listening failed: {e}")
            return False

    async def stop_wakeup_listening(self, session_id: str) -> bool:
        """
        Stop wakeup listening for a session.

        Args:
            session_id: Session identifier

        Returns:
            True if stopped successfully
        """
        logger.info(f"[BridgeManager] Stopping wakeup listening for session {session_id}")

        try:
            await self._conversation_controller.stop()
            return True

        except Exception as e:
            logger.error(f"[BridgeManager] Stop wakeup listening failed: {e}")
            return False

    async def capture_voice(
        self,
        session_id: str,
        timeout: int = 60
    ) -> bytes | None:
        """
        Capture voice audio from microphone.

        Args:
            session_id: Session identifier
            timeout: Capture timeout in seconds

        Returns:
            Audio data bytes or None if capture failed/timeout
        """
        logger.info(f"[BridgeManager] Starting voice capture for session {session_id}")

        try:
            if self._audio_stream_manager:
                audio_data = await self._audio_stream_manager.capture_audio(
                    timeout=timeout
                )
                return audio_data
            return None

        except Exception as e:
            logger.error(f"[BridgeManager] Voice capture failed: {e}")
            return None

    async def speech_to_text(self, audio_data: bytes) -> str | None:
        """
        Convert speech audio to text.

        Args:
            audio_data: Audio data bytes

        Returns:
            Recognized text or None
        """
        if not audio_data or not self._asr:
            return None

        try:
            text = await self._asr.recognize(audio_data)
            logger.info(f"[BridgeManager] STT result: {text[:50] if text else 'None'}...")
            return text

        except Exception as e:
            logger.error(f"[BridgeManager] STT failed: {e}")
            return None


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