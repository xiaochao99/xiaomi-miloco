# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Miloco conversation controller for Xiaomi speaker bridge.
Implements continuous dialogue flow: KWS → VAD → ASR → Miloco → TTS

Reference: open-xiaoai-bridge/core/ahaa_agent_conversation.py
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from enum import Enum
from typing import Optional, Callable, Awaitable

logger = logging.getLogger(__name__)


class ConversationState(Enum):
    """Conversation state machine states."""
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"


class MilocoConversationController:
    """
    Controls continuous dialogue with Miloco model via Xiaomi speaker.

    Flow:
    1. KWS detects wakeup keyword → enter conversation mode
    2. VAD detects speech start → begin recording
    3. VAD detects speech end → stop recording
    4. ASR transcribes audio → get text
    5. Check exit keywords, or send to Miloco
    6. Miloco generates response
    7. TTS synthesizes and plays response
    8. Return to step 2 for next turn

    Reference: open-xiaoai-bridge AhaaAgentConversationController
    """

    _instance: Optional[MilocoConversationController] = None

    def __init__(self):
        self._state = ConversationState.IDLE
        self._active = False
        self._task: Optional[asyncio.Task] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        # Callbacks
        self._on_state_change: Optional[Callable[[ConversationState], Awaitable[None]]] = None
        self._process_text_callback: Optional[Callable[[str], Awaitable[str]]] = None
        self._tts_callback: Optional[Callable[[str], Awaitable[None]]] = None

        # Config
        self._exit_keywords: list[str] = ["退出", "结束对话", "停止"]
        self._wakeup_keywords: list[str] = ["小米同学"]
        self._timeout: int = 20  # seconds of silence before auto-exit
        # When enabled, run at most one "continue" turn and then stop.
        # This is required for "主动智能/询问后等待用户一句指令" UX.
        self._single_turn: bool = False
        # Play once after KWS on_wakeup, before first VAD listen (see on_wakeup / _conversation_loop).
        self._wakeup_opening_reply: str = ""
        self._play_opening_after_next_start: bool = False

        # VAD/ASR references (set by manager)
        self._vad = None
        self._asr = None

        # Per-session future for VAD events
        self._vad_future: Optional[asyncio.Future] = None
        self._recording_frames: list[bytes] = []
        self._is_recording: bool = False

    @classmethod
    def instance(cls) -> MilocoConversationController:
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def state(self) -> ConversationState:
        return self._state

    @property
    def is_active(self) -> bool:
        return self._active

    def configure(
        self,
        exit_keywords: list[str] | None = None,
        wakeup_keywords: list[str] | None = None,
        timeout: int | None = None,
        process_text_callback: Optional[Callable[[str], Awaitable[str]]] = None,
        tts_callback: Optional[Callable[[str], Awaitable[None]]] = None,
        on_state_change: Optional[Callable[[ConversationState], Awaitable[None]]] = None,
        single_turn: bool | None = None,
        wakeup_opening_reply: str | None = None,
    ):
        """Configure conversation controller."""
        if exit_keywords is not None:
            self._exit_keywords = exit_keywords
        if wakeup_keywords is not None:
            self._wakeup_keywords = wakeup_keywords
        if wakeup_opening_reply is not None:
            self._wakeup_opening_reply = wakeup_opening_reply
        if timeout is not None:
            self._timeout = timeout
        if process_text_callback is not None:
            self._process_text_callback = process_text_callback
        if tts_callback is not None:
            self._tts_callback = tts_callback
        if on_state_change is not None:
            self._on_state_change = on_state_change
        if single_turn is not None:
            self._single_turn = single_turn

    def set_audio_components(self, vad=None, asr=None):
        """Set VAD and ASR references."""
        self._vad = vad
        self._asr = asr

    async def _set_state(self, new_state: ConversationState):
        """Update state and notify listeners."""
        if self._state != new_state:
            old_state = self._state
            self._state = new_state
            logger.info("Conversation state: %s -> %s", old_state.value, new_state.value)
            if self._on_state_change:
                await self._on_state_change(new_state)

    async def start(self):
        """Start conversation mode."""
        if self._active:
            logger.warning("Conversation already active")
            return

        self._active = True
        self._loop = asyncio.get_event_loop()

        logger.info("Miloco conversation started")

        try:
            await self._set_state(ConversationState.LISTENING)
            await self._conversation_loop()
        except Exception as exc:
            logger.error("Conversation loop error: %s: %s", type(exc).__name__, exc)
        finally:
            await self.stop()

    async def stop(self):
        """Stop conversation mode."""
        if not self._active:
            return

        self._active = False
        self._play_opening_after_next_start = False

        # Cancel pending VAD future
        self._cancel_vad_future()

        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        await self._set_state(ConversationState.IDLE)
        logger.info("Miloco conversation stopped")

    async def on_wakeup(self, text: str = ""):
        """Handle wakeup event (from KWS or API)."""
        logger.info("Wakeup triggered: %s", text)
        opening = (self._wakeup_opening_reply or "").strip()
        if opening:
            self._play_opening_after_next_start = True
        if not self._active:
            await self.start()

    async def _conversation_loop(self):
        """Run VAD → ASR → Miloco → TTS turns until exit."""
        if self._play_opening_after_next_start and (self._wakeup_opening_reply or "").strip():
            self._play_opening_after_next_start = False
            try:
                await self._set_state(ConversationState.SPEAKING)
                if self._tts_callback:
                    await self._tts_callback((self._wakeup_opening_reply or "").strip())
            except Exception as exc:
                logger.error("Wakeup opening TTS failed: %s: %s", type(exc).__name__, exc)
            finally:
                if self._active:
                    await self._set_state(ConversationState.LISTENING)

        while self._active:
            result = await self._run_one_turn()
            # "continue" means we processed user speech and spoke a response.
            # In single-turn mode, we stop after the first successful turn.
            if result == "continue" and self._single_turn:
                break
            if result in ("exit", "timeout", "error"):
                break

    async def _run_one_turn(self) -> str:
        """
        Execute a single conversation turn.

        Returns:
            "continue" - turn completed, loop to next
            "exit"     - user said an exit keyword
            "timeout"  - no speech detected within timeout
            "error"    - unrecoverable error
        """
        if not self._vad:
            logger.error("VAD not available")
            return "error"

        # 1. Wait for speech
        speech_bytes = await self._wait_for_speech()
        if speech_bytes is None:
            logger.info(
                "No speech segment within %ds (VAD timeout); user command did not enter dialogue",
                self._timeout,
            )
            return "timeout"

        logger.debug("Got speech buffer: %d bytes", len(speech_bytes))

        # 2. ASR: convert speech to text
        text = ""
        if self._asr and self._asr.is_initialized:
            try:
                text = self._asr.transcribe(speech_bytes, sample_rate=16000)
            except Exception as e:
                logger.error("ASR transcription failed: %s", e)

        if not text:
            logger.debug("ASR empty, retrying")
            return "continue"

        # Drop likely self-TTS tail picked up by mic (short phrase contained in last playback text).
        echo_guard = os.getenv("MILOCO_ASR_TTS_ECHO_GUARD", "1").strip().lower() in (
            "1", "true", "yes", "on",
        )
        max_echo_chars = int(os.getenv("MILOCO_ASR_TTS_ECHO_MAX_CHARS", "12"))
        echo_window_s = float(os.getenv("MILOCO_ASR_TTS_ECHO_WINDOW_S", "5"))
        if echo_guard and len(text.strip()) <= max_echo_chars:
            try:
                from miloco_server.xiaomi_bridge.manager import get_bridge_manager

                bm = get_bridge_manager()
                plain = getattr(bm, "_last_played_tts_plain", "") or ""
                ts_at = float(getattr(bm, "_last_played_tts_at", 0) or 0)
                if (
                    plain
                    and (time.monotonic() - ts_at) < echo_window_s
                    and text.strip() in plain
                ):
                    logger.info("ASR dropped as likely TTS echo: %r", text[:40])
                    return "continue"
            except Exception:
                pass

        # Short backchannels right after TTS are often speaker tail / room pickup, not a command.
        filler_guard = os.getenv("MILOCO_ASR_POST_TTS_FILLER_GUARD", "1").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        filler_window_s = float(os.getenv("MILOCO_ASR_POST_TTS_FILLER_WINDOW_S", "4"))
        max_filler_chars = int(os.getenv("MILOCO_ASR_POST_TTS_FILLER_MAX_CHARS", "3"))
        if filler_guard and len(text.strip()) <= max_filler_chars:
            try:
                from miloco_server.xiaomi_bridge.manager import get_bridge_manager

                bm = get_bridge_manager()
                ts_at = float(getattr(bm, "_last_played_tts_at", 0) or 0)
                if ts_at > 0 and (time.monotonic() - ts_at) < filler_window_s:
                    t = text.strip()
                    default_fillers = (
                        "嗯",
                        "嗯嗯",
                        "呃",
                        "唔",
                        "哼",
                        "哦",
                        "噢",
                        "额",
                        "诶",
                        "欸",
                    )
                    extra = os.getenv("MILOCO_ASR_POST_TTS_FILLER_EXTRA", "").strip()
                    fillers = set(default_fillers)
                    if extra:
                        for part in extra.split(","):
                            p = part.strip()
                            if p:
                                fillers.add(p)
                    if t in fillers:
                        logger.info("ASR dropped as post-TTS filler/backchannel: %r", t[:40])
                        return "continue"
            except Exception:
                pass

        logger.info("ASR result: %s", text[:50])

        # 3. Check exit keywords
        for kw in self._exit_keywords:
            if kw in text:
                logger.info("Exit keyword detected: %s", kw)
                await self.stop()
                return "exit"

        # 4. Strip wakeup keywords from text
        for kw in self._wakeup_keywords:
            if kw in text:
                text = text.replace(kw, "").strip()
                if not text:
                    return "continue"

        # 5. Process with Miloco
        await self._set_state(ConversationState.PROCESSING)

        try:
            if self._process_text_callback:
                response = await self._process_text_callback(text)
            else:
                response = f"收到: {text}"

            await self._set_state(ConversationState.SPEAKING)

            # 6. TTS playback
            if self._tts_callback and response:
                await self._tts_callback(response)

            await self._set_state(ConversationState.LISTENING)
            return "continue"

        except Exception as e:
            logger.error("Error processing text: %s", e)
            await self._set_state(ConversationState.LISTENING)
            return "continue"

    async def _wait_for_speech(self) -> Optional[bytes]:
        """
        Use VAD to detect speech and collect complete utterance.

        Returns:
            PCM bytes of captured speech, or None on timeout.
        """
        if not self._vad:
            return None

        self._loop = asyncio.get_event_loop()
        self._vad_future = self._loop.create_future()
        self._recording_frames = []
        self._is_recording = False

        # Set up VAD callbacks
        original_on_speech_end = self._vad._on_speech_end

        def _on_speech_end_hook(segment_audio: bytes):
            """VAD detected end of speech."""
            if self._vad_future and not self._vad_future.done():
                self._loop.call_soon_threadsafe(
                    self._vad_future.set_result, segment_audio
                )

        self._vad._on_speech_end = _on_speech_end_hook
        self._vad.resume("speech")

        try:
            result = await asyncio.wait_for(self._vad_future, timeout=self._timeout)
            return result
        except asyncio.TimeoutError:
            logger.debug("VAD future wait_for timed out (no speech_end within %ds)", self._timeout)
            self._vad.pause()
            return None
        finally:
            self._vad._on_speech_end = original_on_speech_end
            self._vad_future = None

    def _cancel_vad_future(self):
        """Cancel any pending VAD future."""
        if self._vad_future and not self._vad_future.done():
            self._loop.call_soon_threadsafe(self._vad_future.cancel)
        self._vad_future = None

    async def process_text(self, text: str) -> Optional[str]:
        """
        Process recognized text from ASR (direct API, not through VAD).
        Returns Miloco response or None if should exit.
        """
        if not self._active:
            return None

        text = text.strip()
        if not text:
            return None

        # Check exit keywords
        for keyword in self._exit_keywords:
            if keyword in text:
                logger.info("Exit keyword detected: %s", keyword)
                await self.stop()
                return None

        # Check wakeup keywords (re-trigger)
        for keyword in self._wakeup_keywords:
            if keyword in text:
                logger.info("Wakeup keyword detected in speech: %s", keyword)
                text = text.replace(keyword, "").strip()
                if not text:
                    return None

        await self._set_state(ConversationState.PROCESSING)

        try:
            # Process with Miloco
            if self._process_text_callback:
                response = await self._process_text_callback(text)
            else:
                response = f"收到: {text}"

            await self._set_state(ConversationState.SPEAKING)

            # TTS playback
            if self._tts_callback and response:
                await self._tts_callback(response)

            await self._set_state(ConversationState.LISTENING)

            return response

        except Exception as e:
            logger.error("Error processing text: %s", e)
            await self._set_state(ConversationState.LISTENING)
            return None