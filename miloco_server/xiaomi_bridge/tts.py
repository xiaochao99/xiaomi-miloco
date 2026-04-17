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
import base64
import json
import logging
import os
import time
from typing import Optional, AsyncIterator, Any

import httpx

logger = logging.getLogger(__name__)


class TTSService:
    _DOUBAO_TTS_URL = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"
    # Align with open-xiaoai-bridge playback buffering strategy:
    # 24kHz mono int16 => 48000 bytes/s
    _STREAM_SAMPLE_RATE = 24000
    _STREAM_BYTES_PER_SAMPLE = 2

    """
    TTS service for Xiaomi bridge.
    Supports Doubao (火山引擎) TTS, Xiaomi native TTS, and MiMo TTS.
    """

    _instance = None

    def __init__(
        self,
        engine: str = "doubao",
        app_id: str = "",
        access_key: str = "",
        api_key: str = "",
        api_base_url: str = "https://api.xiaomimimo.com",
        default_speaker: str = "mimo_default",
        audio_format: str = "pcm",
        stream: bool = False,
        speed: float = 1.0,
    ):
        self._engine = engine
        self._app_id = app_id
        self._access_key = access_key
        self._api_key = api_key  # For MiMo API
        self._api_base_url = api_base_url  # For MiMo API
        self._default_speaker = default_speaker
        self._audio_format = audio_format
        self._stream = stream
        self._speed = speed
        self._initialized = False
        self._client = None
        self._playback_session = 0

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
        
        elif self._engine == "mimo":
            if not self._api_key:
                logger.warning("MiMo TTS API key not configured")
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
            Audio data bytes (PCM format), or text payload for xiaoai engine
        """
        if not self._initialized:
            logger.error("TTS service not initialized")
            return b""

        try:
            if self._engine == "doubao":
                return await self._synthesize_doubao(text, speaker)
            
            elif self._engine == "mimo":
                return await self._synthesize_mimo(text, speaker)
            
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

        For Doubao/MiMo engine this yields PCM chunks as they arrive from the upstream API.
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

        if self._engine == "mimo":
            async for chunk in self._synthesize_mimo_stream(text, speaker):
                if chunk:
                    yield chunk
            return

        # xiaoai: no audio stream available from server side
        return

    async def _synthesize_doubao(self, text: str, speaker: str = None) -> bytes:
        """Synthesize using Doubao unidirectional streaming API and return merged bytes."""
        audio_data = bytearray()
        async for chunk in self._synthesize_doubao_stream(text, speaker):
            audio_data.extend(chunk)
        return bytes(audio_data)

    async def _synthesize_doubao_stream(self, text: str, speaker: str = None) -> AsyncIterator[bytes]:
        """Stream audio chunks from Doubao TTS API (line-delimited JSON with base64 data)."""
        if not self._client:
            logger.error("Doubao TTS client not initialized")
            return

        payload = self._build_doubao_payload(
            text=text,
            speaker=speaker or self._default_speaker,
        )
        headers = {
            "X-Api-App-Id": self._app_id,
            "X-Api-Access-Key": self._access_key,
            "X-Api-Resource-Id": self._detect_doubao_resource_id(payload["req_params"]["speaker"]),
            "Content-Type": "application/json",
            "Connection": "keep-alive",
        }

        async with self._client.stream(
            "POST",
            self._DOUBAO_TTS_URL,
            headers=headers,
            json=payload,
        ) as response:
            if response.status_code != 200:
                body = await response.aread()
                logger.error("Doubao TTS API error: %d body=%s", response.status_code, body[:300])
                return

            async for line in response.aiter_lines():
                if not line:
                    continue
                parsed = self._parse_doubao_line(line)
                if parsed is None:
                    break
                if parsed:
                    yield parsed

    def _detect_doubao_resource_id(self, speaker: str) -> str:
        """Infer doubao resource_id from speaker prefix."""
        if speaker.startswith("S_"):
            return "seed-icl-2.0"
        if speaker.startswith("ICL_") or speaker.startswith("icl_"):
            return "seed-icl-1.0"
        if speaker.startswith("DiT_") or speaker.startswith("saturn_"):
            return "seed-icl-2.0"
        # Keep compatibility with open-xiaoai-bridge defaults.
        if "_uranus_" in speaker:
            return "seed-tts-2.0"
        return "seed-tts-1.0"

    def _build_doubao_payload(self, text: str, speaker: str) -> dict[str, Any]:
        fmt = self._audio_format if self._audio_format != "auto" else "pcm"
        additions = {
            "explicit_language": "zh",
            "disable_markdown_filter": True,
        }
        req_params: dict[str, Any] = {
            "text": text,
            "speaker": speaker,
            "audio_params": {
                "format": fmt,
                "sample_rate": 24000,
                "enable_timestamp": False,
                "speed": self._speed,
            },
            "additions": json.dumps(additions, ensure_ascii=False),
        }
        if self._detect_doubao_resource_id(speaker) == "seed-tts-1.0":
            req_params["model"] = "seed-tts-1.1"
        return {
            "user": {"uid": "xiaomi-miloco"},
            "req_params": req_params,
        }

    def _parse_doubao_line(self, line: str) -> Optional[bytes]:
        """Parse one Doubao streaming response line."""
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            logger.debug("Doubao TTS ignored non-JSON line")
            return b""

        code = data.get("code", 0)
        if code == 0:
            b64_data = data.get("data") or ""
            if not b64_data:
                return b""
            try:
                return base64.b64decode(b64_data)
            except Exception:
                logger.debug("Doubao TTS base64 decode failed", exc_info=True)
                return b""

        # 20000000 indicates end-of-stream in Doubao unidirectional API.
        if code == 20000000:
            return None

        logger.error("Doubao TTS returned error code=%s message=%s", code, data.get("message"))
        return None

    async def _synthesize_mimo(self, text: str, speaker: str = None) -> bytes:
        """Synthesize using MiMo TTS API."""
        voice = speaker or self._default_speaker
        headers = self._build_mimo_headers()

        # 兼容两种非流式请求体，避免某些网关返回 200 但不含 audio 字段。
        payload_candidates = [
            self._build_mimo_payload_legacy(text, voice, stream=False),
            self._build_mimo_payload_openai_style(text, voice, stream=False),
        ]
        for payload in payload_candidates:
            audio_data = await self._request_mimo_non_stream(payload, headers)
            if audio_data:
                return audio_data

        logger.error("MiMo TTS returned empty audio data")
        return b""

    async def _synthesize_mimo_stream(self, text: str, speaker: str = None) -> AsyncIterator[bytes]:
        """Stream audio chunks from MiMo TTS API."""
        url = f"{self._api_base_url}/v1/chat/completions"
        voice = speaker or self._default_speaker

        headers = self._build_mimo_headers()

        if not self._client:
            logger.error("MiMo TTS client not initialized")
            return

        max_retries = 3
        retry_delay = 1.0

        # 兼容两种请求体：旧格式 + OpenAI audio 风格格式
        payload_candidates = [
            self._build_mimo_payload_legacy(text, voice, stream=True),
            self._build_mimo_payload_openai_style(text, voice, stream=True),
        ]

        for payload in payload_candidates:
            for attempt in range(max_retries):
                async with self._client.stream("POST", url, json=payload, headers=headers) as response:
                    if response.status_code == 200:
                        got_any = False
                        # 成功获取响应，开始处理流式数据
                        async for line in response.aiter_lines():
                            if line.startswith("data: "):
                                line = line[5:]  # Remove "data: " prefix
                            if line.strip() == "[DONE]":
                                break
                            if not line.strip():
                                continue
                            try:
                                chunk_data = json.loads(line)
                            except Exception:
                                logger.debug("MiMo stream parse skipped non-JSON line")
                                continue

                            audio_chunks = self._extract_mimo_audio_chunks(chunk_data)
                            for audio_chunk in audio_chunks:
                                got_any = True
                                yield audio_chunk

                        if got_any:
                            return  # 成功完成
                        logger.warning("MiMo stream response has no audio chunks, trying fallback payload")
                        break

                    if response.status_code == 429:
                        logger.warning(
                            "MiMo TTS stream rate limited (attempt %d/%d), retrying in %.1fs",
                            attempt + 1,
                            max_retries,
                            retry_delay,
                        )
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2
                        continue

                    body = await response.aread()
                    logger.error(
                        "MiMo TTS stream API error: %d body=%s",
                        response.status_code,
                        body[:500],
                    )
                    break

        logger.error("MiMo TTS stream failed after %d retries", max_retries)

    def _normalize_mimo_audio_format(self) -> str:
        """Normalize local config audio format to MiMo supported format string."""
        fmt = (self._audio_format or "").lower().strip()
        if fmt in ("pcm16", "pcm", "s16le"):
            return "pcm16"
        if fmt in ("mp3", "wav"):
            return fmt
        return "pcm16"

    def _build_mimo_headers(self) -> dict[str, str]:
        return {
            "api-key": self._api_key,
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _build_mimo_payload_legacy(self, text: str, voice: str, stream: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": "mimo-v2-tts",
            "messages": [
                {"role": "user", "content": text},
                {"role": "assistant", "content": text},
            ],
            "audio": {
                "format": self._normalize_mimo_audio_format(),
                "voice": voice,
            },
        }
        if stream:
            payload["stream"] = True
        return payload

    def _build_mimo_payload_openai_style(self, text: str, voice: str, stream: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": "mimo-v2-tts",
            "messages": [
                {"role": "user", "content": text},
            ],
            "modalities": ["audio"],
            "audio": {
                "format": self._normalize_mimo_audio_format(),
                "voice": voice,
            },
        }
        if stream:
            payload["stream"] = True
        return payload

    def _extract_mimo_audio_chunks(self, obj: Any) -> list[bytes]:
        """
        从 MiMo/OpenAI 兼容返回里提取所有可用音频块。
        兼容路径：
        - choices[0].message.audio.data
        - choices[0].delta.audio.data
        - output_audio.data
        """
        b64_values: list[str] = []

        if isinstance(obj, dict):
            choices = obj.get("choices")
            if isinstance(choices, list):
                for choice in choices:
                    if not isinstance(choice, dict):
                        continue
                    for key in ("message", "delta"):
                        node = choice.get(key)
                        if isinstance(node, dict):
                            audio = node.get("audio")
                            if isinstance(audio, dict):
                                data = audio.get("data")
                                if isinstance(data, str) and data:
                                    b64_values.append(data)
            output_audio = obj.get("output_audio")
            if isinstance(output_audio, dict):
                data = output_audio.get("data")
                if isinstance(data, str) and data:
                    b64_values.append(data)

        chunks: list[bytes] = []
        for b64_item in b64_values:
            try:
                chunks.append(base64.b64decode(b64_item))
            except Exception:
                logger.debug("MiMo audio base64 decode failed", exc_info=True)
        return chunks

    async def _request_mimo_non_stream(self, payload: dict[str, Any], headers: dict[str, str]) -> bytes:
        if not self._client:
            return b""
        url = f"{self._api_base_url}/v1/chat/completions"
        response = await self._client.post(url, json=payload, headers=headers)
        if response.status_code != 200:
            logger.error(
                "MiMo TTS API error: %d body=%s",
                response.status_code,
                response.text[:500],
            )
            return b""
        response_data = response.json()
        chunks = self._extract_mimo_audio_chunks(response_data)
        if chunks:
            return b"".join(chunks)
        logger.warning("MiMo non-stream response has no audio payload: %s", str(response_data)[:500])
        return b""

    async def speak(
        self,
        text: str,
        speaker: str = None,
        client_ids: Optional[list[str]] = None,
    ) -> bool:
        """
        Synthesize and play text via audio stream.
        
        Args:
            text: Text to speak
            speaker: Speaker name (optional)
        
        Returns:
            True if successful, False otherwise
        """
        if self._engine == "xiaoai":
            # For xiaoai engine, send text directly via WebSocket using native TTS
            return await self._speak_xiaoai(text, client_ids=client_ids)

        # Align with open-xiaoai-bridge style: prefer stream playback when enabled.
        # If upstream stream mode is not supported, gracefully fallback to non-stream.
        if self._stream:
            streamed_ok = await self.speak_stream(text, speaker)
            if streamed_ok:
                return True
            logger.warning(
                "Stream TTS failed for engine=%s, fallback to non-stream synthesis",
                self._engine,
            )

        audio_data = await self.synthesize(text, speaker)
        if not audio_data:
            return False

        from miloco_server.xiaomi_bridge.audio_stream import get_audio_stream_manager
        stream_manager = get_audio_stream_manager()
        token = self._begin_playback_session()
        await stream_manager.restart_playback(client_ids=client_ids, force_reinit=True)
        await self._send_pcm_with_throttle(stream_manager, audio_data, client_ids, token)
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
            token = self._begin_playback_session()
            sent_any = False
            buffer = bytearray()
            start_buffer_ms = int(os.getenv("MILOCO_TTS_STREAM_START_BUFFER_MS", "240"))
            chunk_ms = int(os.getenv("MILOCO_TTS_STREAM_CHUNK_MS", "60"))
            bytes_per_sec = self._STREAM_SAMPLE_RATE * self._STREAM_BYTES_PER_SAMPLE
            startup_bytes = max(1, bytes_per_sec * start_buffer_ms // 1000)
            chunk_bytes = max(1, bytes_per_sec * chunk_ms // 1000)
            started = False
            playback_initialized = False
            sent_bytes = 0
            playback_start = time.monotonic()

            async for chunk in self.synthesize_stream(text, speaker):
                if not self._is_playback_session_active(token):
                    logger.debug("Stream TTS aborted by newer playback session")
                    return sent_any
                if not chunk:
                    continue
                buffer.extend(chunk)

                # Before starting playback, wait until enough audio is buffered.
                if not started and len(buffer) < startup_bytes:
                    continue
                started = True

                # Emit fixed-size chunks to smooth device-side playback cadence.
                while len(buffer) >= chunk_bytes:
                    if not playback_initialized:
                        # Delay start_play until we have enough buffered audio to send immediately.
                        await stream_manager.restart_playback(client_ids, force_reinit=True)
                        playback_initialized = True
                        playback_start = time.monotonic()
                    packet = bytes(buffer[:chunk_bytes])
                    del buffer[:chunk_bytes]
                    await stream_manager.send_audio_to_clients(packet, client_ids)
                    sent_any = True
                    sent_bytes += len(packet)
                    await self._throttle_if_needed(sent_bytes, playback_start, token)

            # Flush remaining buffered bytes.
            if buffer:
                if not playback_initialized:
                    await stream_manager.restart_playback(client_ids, force_reinit=True)
                    playback_initialized = True
                    playback_start = time.monotonic()
                await stream_manager.send_audio_to_clients(bytes(buffer), client_ids)
                sent_any = True
                sent_bytes += len(buffer)
                await self._throttle_if_needed(sent_bytes, playback_start, token)

            return sent_any
        except Exception as e:
            logger.error("Stream TTS speak failed: %s", e, exc_info=True)
            return False

    def _begin_playback_session(self) -> int:
        """Begin a new playback session; invalidates previous session."""
        self._playback_session += 1
        return self._playback_session

    def _is_playback_session_active(self, token: int) -> bool:
        return token == self._playback_session

    async def _throttle_if_needed(self, sent_bytes: int, playback_start: float, token: int):
        """
        Keep audio sent ahead-of-time bounded, similar to open-xiaoai-bridge MAX_AHEAD_MS.
        """
        max_ahead_ms = int(os.getenv("MILOCO_TTS_STREAM_MAX_AHEAD_MS", "1500"))
        sent_duration_ms = sent_bytes * 1000 / (self._STREAM_SAMPLE_RATE * self._STREAM_BYTES_PER_SAMPLE)
        elapsed_ms = (time.monotonic() - playback_start) * 1000
        ahead_ms = max(0.0, sent_duration_ms - elapsed_ms)
        if ahead_ms <= max_ahead_ms:
            return
        wait_ms = int(ahead_ms - max_ahead_ms)
        while wait_ms > 0 and self._is_playback_session_active(token):
            step = min(wait_ms, 50)
            await asyncio.sleep(step / 1000.0)
            wait_ms -= step

    async def _send_pcm_with_throttle(
        self,
        stream_manager,
        pcm_data: bytes,
        client_ids: Optional[list[str]],
        token: int,
    ):
        """
        Send full PCM bytes in paced chunks to avoid remote aplay underrun/overrun jitter.
        """
        if not pcm_data:
            return
        chunk_ms = int(os.getenv("MILOCO_TTS_STREAM_CHUNK_MS", "60"))
        chunk_bytes = max(
            1,
            (self._STREAM_SAMPLE_RATE * self._STREAM_BYTES_PER_SAMPLE * chunk_ms) // 1000,
        )
        sent_bytes = 0
        playback_start = time.monotonic()
        offset = 0
        total = len(pcm_data)
        while offset < total:
            if not self._is_playback_session_active(token):
                logger.debug("PCM playback aborted by newer playback session")
                return
            end = min(offset + chunk_bytes, total)
            packet = pcm_data[offset:end]
            await stream_manager.send_audio_to_clients(packet, client_ids)
            sent_bytes += len(packet)
            await self._throttle_if_needed(sent_bytes, playback_start, token)
            offset = end

    async def _speak_xiaoai(self, text: str, client_ids: Optional[list[str]] = None) -> bool:
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
            await stream_manager.run_shell(build_mibrain_tts_script(text), client_ids=client_ids)
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