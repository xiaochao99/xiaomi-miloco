# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Conversation controller for Xiaomi Bridge.

Manages continuous dialogue flow: KWS → VAD → ASR → Miloco → TTS

Reference: open-xiaoai-bridge/core/openclaw_conversation.py
"""

import asyncio
import os

from miloco_server.xiaomi_bridge.ref import get_speaker, get_vad
from miloco_server.xiaomi_bridge.services.audio.asr.sherpa import SherpaASR
from miloco_server.xiaomi_bridge.utils.config import ConfigManager
from miloco_server.xiaomi_bridge.utils.logger import logger


# Load notification sounds
_NOTIFY_SOUND_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "assets", "sounds", "tts_notify.mp3",
)

_SEND_SOUND_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "assets", "sounds", "send_notify.mp3",
)


def _load_notify_sound() -> bytes | None:
    """Load notification sound."""
    if not os.path.isfile(_NOTIFY_SOUND_PATH):
        return None
    try:
        with open(_NOTIFY_SOUND_PATH, "rb") as f:
            return f.read()
    except Exception:
        return None


def _load_send_sound() -> bytes | None:
    """Load send sound."""
    if not os.path.isfile(_SEND_SOUND_PATH):
        return None
    try:
        with open(_SEND_SOUND_PATH, "rb") as f:
            return f.read()
    except Exception:
        return None


_NOTIFY_PCM = _load_notify_sound()
_SEND_PCM = _load_send_sound()


class ConversationController:
    """Manages multi-turn conversation with Miloco."""

    LOCAL_ASR_INPUT = "local_asr"
    XIAOAI_ASR_INPUT = "xiaoai_asr"

    _instance = None

    def __init__(self):
        """Initialize conversation controller."""
        self.config = ConfigManager.instance()
        self.active = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self._playback_token: int | None = None

    @classmethod
    def instance(cls) -> "ConversationController":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ---- Config helpers ----

    def _cfg(self, key: str, default=None):
        """Get config value."""
        return self.config.get_app_config(f"bridge.{key}", default)

    @property
    def exit_keywords(self) -> list[str]:
        """Get exit keywords."""
        return self.config.get_app_config("exit_keywords", ["退出", "停止", "再见"])

    @property
    def timeout(self) -> int:
        """Get conversation timeout."""
        return int(self.config.get_app_config("wakeup.timeout", 20))

    @property
    def input_mode(self) -> str:
        """Get input mode."""
        mode = self._cfg("input_mode", self.LOCAL_ASR_INPUT)
        if not isinstance(mode, str):
            return self.LOCAL_ASR_INPUT
        normalized = mode.strip().lower()
        if normalized in {self.LOCAL_ASR_INPUT, self.XIAOAI_ASR_INPUT}:
            return normalized
        logger.warning(
            f"Unknown input_mode={mode!r}, fallback to {self.LOCAL_ASR_INPUT}",
            module="Conversation"
        )
        return self.LOCAL_ASR_INPUT

    def uses_xiaoai_asr(self) -> bool:
        """Check if using XiaoAI native ASR."""
        return self.input_mode == self.XIAOAI_ASR_INPUT

    # ---- Public API ----

    def is_active(self) -> bool:
        """Check if conversation is active."""
        return self.active

    async def start(self):
        """Enter conversation mode."""
        if self.active:
            logger.warning("[Conversation] Already active, ignoring start()")
            return

        self.active = True
        self._loop = asyncio.get_running_loop()

        logger.info("🎙️ 进入 Miloco 连续对话模式", module="Conversation")

        try:
            await self._conversation_loop()
        except Exception as exc:
            logger.error(
                f"Conversation loop error: {type(exc).__name__}: {exc}",
                module="Conversation"
            )
        finally:
            self.stop()

    def stop(self):
        """Exit conversation mode and clean up."""
        if not self.active:
            return

        self.active = False

        if self._playback_token is not None:
            # Stop TTS playback if active
            self._playback_token = None

        if self.uses_xiaoai_asr():
            speaker = get_speaker()
            if speaker and self._loop:
                try:
                    asyncio.run_coroutine_threadsafe(
                        speaker.wake_up(awake=False),
                        self._loop,
                    )
                except Exception as exc:
                    logger.debug(
                        f"Failed to stop XiaoAI native listening: {exc}",
                        module="Conversation"
                    )

        logger.info("👋 退出 Miloco 连续对话模式", module="Conversation")

    # ---- Conversation loop ----

    async def _conversation_loop(self):
        """Run VAD → ASR → Miloco → TTS turns until exit."""
        await self._stop_recording()
        logger.debug("Recording stopped", module="Conversation")
        await self._play_notify()
        await self._start_recording()
        logger.debug("Ready to listen", module="Conversation")

        while self.active:
            if self.uses_xiaoai_asr():
                result = await self._run_one_turn_with_xiaoai_asr()
            else:
                result = await self._run_one_turn_with_local_asr()

            if result in ("exit", "timeout"):
                if self.uses_xiaoai_asr():
                    await self._stop_xiaoai_native_listening()
                await self._call_after_wakeup()
                break
            elif result == "error":
                break

    async def _run_one_turn_with_local_asr(self) -> str:
        """Execute a single conversation turn using local ASR."""
        vad = get_vad()
        if not vad:
            logger.error("VAD not available", module="Conversation")
            return "error"

        # 1. Wait for speech
        speech_bytes = await self._wait_for_speech(vad)
        if speech_bytes is None:
            return "timeout"

        logger.debug(
            f"Got speech buffer: {len(speech_bytes)} bytes",
            module="Conversation"
        )

        # 2. ASR: convert speech to text
        text = SherpaASR.asr(speech_bytes, sample_rate=16000)
        if not text:
            logger.debug("ASR empty, retrying", module="Conversation")
            return "continue"

        # 3. Check exit keywords
        for kw in self.exit_keywords:
            if kw in text:
                logger.info(f"Exit keyword: {kw}", module="Conversation")
                return "exit"

        # 4. Send to Miloco and get response
        response = await self._send_to_miloco(text)
        if response is None:
            logger.warning("No response from Miloco", module="Conversation")
            speaker = get_speaker()
            if speaker:
                await speaker.play(text="抱歉，我没有收到回复")
            return "continue"

        # 5. Play response
        await self._stop_recording()
        await self._play_tts(str(response))
        await self._play_notify()
        await self._start_recording()
        logger.debug("Ready to listen", module="Conversation")

        return "continue"

    async def _run_one_turn_with_xiaoai_asr(self) -> str:
        """Execute a single conversation turn using XiaoAI native ASR."""
        # This would integrate with XiaoAI native ASR
        # For now, fall back to local ASR
        logger.warning("XiaoAI ASR not implemented, falling back to local ASR")
        return await self._run_one_turn_with_local_asr()

    # ---- VAD integration ----

    async def _wait_for_speech(self, vad) -> bytes | None:
        """Use VAD to detect speech and collect complete utterance."""
        from miloco_server.xiaomi_bridge.wakeup_session import EventManager

        self._vad_future = self._loop.create_future()
        recording_frames: list[bytes] = []
        is_recording = False

        original_on_speech = EventManager.on_speech
        original_on_silence = EventManager.on_silence

        def _on_speech_hook(speech_buffer: bytes):
            """Voice detected."""
            nonlocal is_recording
            recording_frames.append(speech_buffer)
            is_recording = True
            logger.debug(f"VAD speech detected, buffer size: {len(speech_buffer)}", module="Conversation")
            vad.resume("silence")

        def _on_silence_hook():
            """Silence detected."""
            nonlocal is_recording
            is_recording = False
            logger.debug("VAD detected silence, stop recording", module="Conversation")
            if self._vad_future and not self._vad_future.done():
                self._loop.call_soon_threadsafe(
                    self._vad_future.set_result, b"".join(recording_frames)
                )

        # Tap into VAD's audio stream
        _orig_handle_speech = getattr(vad, '_handle_speech_frame', None)
        _orig_handle_silence = getattr(vad, '_handle_silence_frame', None)

        def _recording_speech_frame(frames):
            if is_recording:
                recording_frames.append(bytes(frames))
            if _orig_handle_speech:
                _orig_handle_speech(frames)

        def _recording_silence_frame(frames):
            if is_recording:
                recording_frames.append(bytes(frames))
            if _orig_handle_silence:
                _orig_handle_silence(frames)

        EventManager.on_speech = _on_speech_hook
        EventManager.on_silence = _on_silence_hook
        if hasattr(vad, '_handle_speech_frame'):
            vad._handle_speech_frame = _recording_speech_frame
        if hasattr(vad, '_handle_silence_frame'):
            vad._handle_silence_frame = _recording_silence_frame

        try:
            vad.resume("speech")
            result = await asyncio.wait_for(self._vad_future, timeout=self.timeout)
            return result

        except asyncio.TimeoutError:
            logger.debug("VAD timeout, no speech detected", module="Conversation")
            vad.pause()
            return None

        finally:
            EventManager.on_speech = original_on_speech
            EventManager.on_silence = original_on_silence
            if _orig_handle_speech and hasattr(vad, '_handle_speech_frame'):
                vad._handle_speech_frame = _orig_handle_speech
            if _orig_handle_silence and hasattr(vad, '_handle_silence_frame'):
                vad._handle_silence_frame = _orig_handle_silence
            self._vad_future = None

    # ---- Miloco integration ----

    async def _send_to_miloco(self, text: str) -> str | None:
        """Send text to Miloco and get response."""
        try:
            # This should call the Miloco service
            # For now, return a simple response
            logger.info(f"Sending to Miloco: {text}", module="Conversation")
            return f"收到: {text}"
        except Exception as e:
            logger.error(f"Failed to send to Miloco: {e}", module="Conversation")
            return None

    # ---- Recording control ----

    async def _stop_recording(self):
        """Stop audio recording."""
        try:
            logger.debug("Recording stopped", module="Conversation")
        except Exception as exc:
            logger.debug(f"stop_recording error: {exc}", module="Conversation")

    async def _start_recording(self):
        """Start audio recording."""
        try:
            logger.debug("Recording started", module="Conversation")
        except Exception as exc:
            logger.debug(f"start_recording error: {exc}", module="Conversation")

    async def _stop_xiaoai_native_listening(self):
        """Stop XiaoAI native listening."""
        speaker = get_speaker()
        if not speaker:
            return
        try:
            await speaker.stop_device_audio()
            await speaker.wake_up(awake=False)
            await asyncio.sleep(0.15)
        except Exception as exc:
            logger.debug(
                f"Failed to stop XiaoAI native listening: {exc}",
                module="Conversation"
            )

    # ---- TTS ----

    async def _play_tts(self, text: str):
        """Play text via TTS."""
        try:
            from miloco_server.xiaomi_bridge.services.audio.tts.doubao import DoubaoTTS
            
            tts = DoubaoTTS.instance()
            audio_data = await tts.synthesize(text)
            
            if audio_data:
                # Send to speaker via audio stream
                from miloco_server.xiaomi_bridge.services.audio.stream import AudioStreamHandler
                await AudioStreamHandler.instance().play_audio(audio_data)
            else:
                # Fallback to speaker play
                speaker = get_speaker()
                if speaker:
                    await speaker.play(text=text)

        except Exception as exc:
            logger.error(f"TTS playback error: {exc}", module="Conversation")
            speaker = get_speaker()
            if speaker:
                await speaker.play(text=text)

    async def _play_notify(self):
        """Play the listening-ready notification sound."""
        if not _NOTIFY_PCM:
            return
        speaker = get_speaker()
        if speaker:
            try:
                await speaker.play(buffer=_NOTIFY_PCM)
                duration = len(_NOTIFY_PCM) / (24000 * 2)
                await asyncio.sleep(duration)
            except Exception as exc:
                logger.debug(f"Notify sound error: {exc}", module="Conversation")

    async def _play_send_sound(self):
        """Play send notification sound."""
        if not _SEND_PCM:
            return
        speaker = get_speaker()
        if speaker:
            try:
                await speaker.play(buffer=_SEND_PCM)
                duration = len(_SEND_PCM) / (24000 * 2)
                await asyncio.sleep(duration)
            except Exception as exc:
                logger.debug(f"Send sound error: {exc}", module="Conversation")

    async def _call_after_wakeup(self):
        """Call after_wakeup hook."""
        after_wakeup = self.config.get_app_config("wakeup.after_wakeup")
        if after_wakeup:
            speaker = get_speaker()
            if speaker:
                await after_wakeup(speaker, source="miloco")