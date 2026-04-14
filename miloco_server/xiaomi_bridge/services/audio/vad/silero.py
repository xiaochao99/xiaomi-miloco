# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Silero VAD implementation for Xiaomi Bridge.

Reference: open-xiaoai-bridge/core/services/audio/vad/silero.py
"""

import asyncio
import os
import threading
from typing import Callable, Optional

import numpy as np

from miloco_server.xiaomi_bridge.utils.logger import logger


class SileroVAD:
    """Silero Voice Activity Detection."""

    _instance = None
    _model = None
    _sampling_rate = 16000

    # State
    _running = False
    _paused = False
    _mode = "off"  # off, speech, silence
    _stream = None
    _lock = threading.Lock()

    # Config
    _threshold = 0.10
    _min_speech_duration_ms = 250
    _min_silence_duration_ms = 500

    # Buffers
    _speech_frames = []
    _input_bytes = b""

    # Callbacks
    _on_speech_callback: Optional[Callable[[bytes], None]] = None
    _on_silence_callback: Optional[Callable[[], None]] = None

    @classmethod
    def instance(cls) -> "SileroVAD":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        """Initialize VAD."""
        self._loop = None

    @classmethod
    def set_config(
        cls,
        threshold: float = 0.10,
        min_speech_duration_ms: int = 250,
        min_silence_duration_ms: int = 500,
    ):
        """Set VAD configuration."""
        cls._threshold = threshold
        cls._min_speech_duration_ms = min_speech_duration_ms
        cls._min_silence_duration_ms = min_silence_duration_ms

    @classmethod
    def start(cls):
        """Start VAD processing."""
        if cls._running:
            return

        # Load model
        cls._load_model()

        cls._running = True
        cls._paused = False
        cls._mode = "off"
        cls._speech_frames = []
        cls._input_bytes = b""
        logger.info("[VAD] Silero VAD started")

    @classmethod
    def stop(cls):
        """Stop VAD processing."""
        cls._running = False
        cls._paused = False
        cls._mode = "off"
        cls._speech_frames = []
        cls._input_bytes = b""
        logger.info("[VAD] Silero VAD stopped")

    @classmethod
    def pause(cls):
        """Pause VAD processing."""
        cls._paused = True
        logger.debug("[VAD] VAD paused")

    @classmethod
    def resume(cls, mode: str = "speech"):
        """
        Resume VAD processing.
        
        Args:
            mode: "speech" to detect speech start, "silence" to detect silence
        """
        cls._paused = False
        cls._mode = mode
        cls._speech_frames = []
        cls._input_bytes = b""
        logger.debug(f"[VAD] VAD resumed in {mode} mode")

    @classmethod
    def _load_model(cls):
        """Load Silero VAD model."""
        if cls._model is not None:
            return

        try:
            import torch

            # Try to load from configured path first
            from miloco_server.xiaomi_bridge.utils.config import ConfigManager
            config = ConfigManager.instance()
            model_path = config.get_app_config("vad.model_path", "")

            if model_path and os.path.exists(model_path):
                cls._model, _ = torch.jit.load(model_path, map_location="cpu").eval()
            else:
                # Download and cache
                cls._model, _ = torch.hub.load(
                    repo_or_dir="snakers4/silero-vad",
                    model="silero_vad",
                    force_reload=False,
                )

            logger.info("[VAD] Silero VAD model loaded")
        except Exception as e:
            logger.error(f"[VAD] Failed to load Silero VAD model: {e}")
            raise

    @classmethod
    def process_audio(cls, audio_data: bytes):
        """
        Process audio data for voice activity detection.
        
        Args:
            audio_data: PCM audio bytes (int16, 16kHz, mono)
        """
        if not cls._running or cls._paused:
            return

        if cls._model is None:
            cls._load_model()

        # Convert bytes to numpy array
        samples = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

        cls._input_bytes += audio_data

        # Process in chunks
        chunk_size = 512
        for i in range(0, len(samples), chunk_size):
            chunk = samples[i:i+chunk_size]
            if len(chunk) < chunk_size:
                pad = np.zeros(chunk_size - len(chunk), dtype=np.float32)
                chunk = np.concatenate([chunk, pad])

            # Get VAD score
            score = cls._model(torch.from_numpy(chunk), cls._sampling_rate).item()

            if cls._mode == "speech":
                cls._detect_speech(score, audio_data)
            elif cls._mode == "silence":
                cls._detect_silence(score, audio_data)

    @classmethod
    def _detect_speech(cls, score: float, audio_data: bytes):
        """Detect speech start."""
        if score >= cls._threshold:
            cls._speech_frames.append(audio_data)
            # Check if we've accumulated enough speech
            duration_ms = len(cls._speech_frames) * len(audio_data) * 1000 / (cls._sampling_rate * 2)
            if duration_ms >= cls._min_speech_duration_ms:
                if cls._on_speech_callback:
                    speech_buffer = cls._input_bytes + b"".join(cls._speech_frames)
                    cls._on_speech_callback(speech_buffer)
                cls._speech_frames = []
                cls._input_bytes = b""

    @classmethod
    def _detect_silence(cls, score: float, audio_data: bytes):
        """Detect silence after speech."""
        if score < cls._threshold:
            cls._speech_frames.append(audio_data)
            duration_ms = len(cls._speech_frames) * len(audio_data) * 1000 / (cls._sampling_rate * 2)
            if duration_ms >= cls._min_silence_duration_ms:
                if cls._on_silence_callback:
                    cls._on_silence_callback()
                cls._speech_frames = []
                cls._input_bytes = b""
        else:
            # Still speech, keep accumulating
            cls._speech_frames = []

    @classmethod
    def set_callbacks(
        cls,
        on_speech: Optional[Callable[[bytes], None]] = None,
        on_silence: Optional[Callable[[], None]] = None,
    ):
        """Set VAD callbacks."""
        cls._on_speech_callback = on_speech
        cls._on_silence_callback = on_silence

    @classmethod
    def is_running(cls) -> bool:
        """Check if VAD is running."""
        return cls._running

    @classmethod
    def is_paused(cls) -> bool:
        """Check if VAD is paused."""
        return cls._paused

    @classmethod
    def get_mode(cls) -> str:
        """Get current VAD mode."""
        return cls._mode