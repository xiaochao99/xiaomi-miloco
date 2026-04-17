# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
VAD (Voice Activity Detection) module.
Uses Silero VAD via ONNX Runtime for efficient speech detection.

Reference: open-xiaoai-bridge/core/services/audio/vad/silero.py
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


class SileroVADOnnx:
    """Silero VAD wrapper using ONNX Runtime."""
    
    def __init__(self, model_path: str):
        import onnxruntime as ort
        
        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        
        self.session = ort.InferenceSession(
            model_path,
            providers=["CPUExecutionProvider"],
            sess_options=opts,
        )
        self.reset_states()
        self.sample_rates = [8000, 16000]
    
    def reset_states(self, batch_size: int = 1):
        """Reset internal RNN states."""
        self._state = np.zeros((2, batch_size, 128), dtype=np.float32)
        self._context = np.zeros(0, dtype=np.float32)
        self._last_sr = 0
        self._last_batch_size = 0
    
    def _validate_input(self, x, sr: int):
        """Validate and normalize input."""
        if len(x.shape) == 1:
            x = np.expand_dims(x, 0)
        if len(x.shape) > 2:
            raise ValueError(f"Too many dimensions for input audio chunk {len(x.shape)}")
        
        if sr != 16000 and (sr % 16000 == 0):
            step = sr // 16000
            x = x[:, ::step]
            sr = 16000
        
        if sr not in self.sample_rates:
            raise ValueError(f"Supported sampling rates: {self.sample_rates} (or multiply of 16000)")
        if sr / x.shape[1] > 31.25:
            raise ValueError("Input audio chunk is too short")
        
        return x, sr
    
    def __call__(self, x: np.ndarray, sr: int) -> float:
        """Run VAD inference. Returns speech probability [0, 1]."""
        x, sr = self._validate_input(x, sr)
        num_samples = 512 if sr == 16000 else 256
        
        if x.shape[-1] != num_samples:
            raise ValueError(
                f"Provided number of samples is {x.shape[-1]} "
                f"(Supported values: 256 for 8000 sample rate, 512 for 16000)"
            )
        
        batch_size = x.shape[0]
        context_size = 64 if sr == 16000 else 32
        
        if not self._last_batch_size:
            self.reset_states(batch_size)
        if self._last_sr and self._last_sr != sr:
            self.reset_states(batch_size)
        if self._last_batch_size and self._last_batch_size != batch_size:
            self.reset_states(batch_size)
        
        if not len(self._context):
            self._context = np.zeros((batch_size, context_size), dtype=np.float32)
        
        x = np.concatenate([self._context, x], axis=1)
        
        ort_inputs = {
            "input": x,
            "state": self._state,
            "sr": np.array(sr, dtype="int64"),
        }
        ort_outs = self.session.run(None, ort_inputs)
        out, state = ort_outs
        self._state = state
        
        self._context = x[..., -context_size:]
        self._last_sr = sr
        self._last_batch_size = batch_size
        
        return out.item()


class EnergyVAD:
    """Simple energy-based VAD fallback."""
    
    def __init__(self, threshold: float = 0.10):
        self._threshold = threshold
    
    def __call__(self, audio_chunk: bytes, sample_rate: int = 16000) -> float:
        """Return energy-based speech probability."""
        samples = np.frombuffer(audio_chunk, dtype=np.int16).astype(np.float32) / 32768.0
        energy = np.sqrt(np.mean(samples ** 2))
        # Normalize to [0, 1] range
        return min(energy / self._threshold, 1.0) if self._threshold > 0 else 0.0


class VADManager:
    """
    VAD manager with speech/silence detection.
    Manages speech buffering and state transitions.
    
    Reference: open-xiaoai-bridge wakeup_session.py VAD integration
    """
    
    def __init__(
        self,
        model_path: str = "",
        threshold: float = 0.10,
        min_speech_duration_ms: int = 250,
        min_silence_duration_ms: int = 500,
        sample_rate: int = 16000,
    ):
        self._threshold = threshold
        self._min_speech_duration_ms = min_speech_duration_ms
        self._min_silence_duration_ms = min_silence_duration_ms
        self._sample_rate = sample_rate
        
        # Calculate frame counts
        self._frames_per_second = sample_rate // 512  # 512 samples per frame at 16kHz
        self._min_speech_frames = max(1, int(min_speech_duration_ms / 1000 * self._frames_per_second))
        self._min_silence_frames = max(1, int(min_silence_duration_ms / 1000 * self._frames_per_second))
        
        # State
        self._model: Optional[SileroVADOnnx] = None
        self._fallback: Optional[EnergyVAD] = None
        self._is_speaking = False
        self._speech_buffer: list[bytes] = []
        self._silence_frame_count = 0
        self._speech_frame_count = 0
        
        # Callbacks
        self._on_speech_start = None
        self._on_speech_end = None
        self._paused = False
        
        # Initialize model
        self._init_model(model_path)
    
    def _init_model(self, model_path: str):
        """Initialize VAD model."""
        if model_path and os.path.isfile(model_path):
            try:
                self._model = SileroVADOnnx(model_path)
                logger.info("Silero VAD model loaded from %s", model_path)
            except Exception as e:
                logger.warning("Failed to load Silero VAD: %s. Using energy-based VAD.", e)
                self._fallback = EnergyVAD(self._threshold)
        else:
            logger.info("No VAD model path provided, using energy-based VAD")
            self._fallback = EnergyVAD(self._threshold)
    
    def set_callbacks(self, on_speech_start=None, on_speech_end=None):
        """Set speech event callbacks."""
        self._on_speech_start = on_speech_start
        self._on_speech_end = on_speech_end
    
    def _detect_speech(self, audio_chunk: bytes) -> float:
        """Detect speech probability in audio chunk."""
        if self._model:
            try:
                samples = np.frombuffer(audio_chunk, dtype=np.int16).astype(np.float32) / 32768.0
                return self._model(samples, self._sample_rate)
            except Exception as e:
                logger.debug("Silero VAD error: %s", e)
        
        if self._fallback:
            return self._fallback(audio_chunk, self._sample_rate)
        
        return 0.0
    
    def process_chunk(self, audio_chunk: bytes) -> Optional[str]:
        """
        Process audio chunk and detect speech state changes.
        
        Returns:
            "speech_start" when speech begins
            "speech_end" when speech ends (with buffered audio)
            None otherwise
        """
        if self._paused:
            return None
        
        speech_prob = self._detect_speech(audio_chunk)
        is_speech = speech_prob > self._threshold
        
        if is_speech:
            self._silence_frame_count = 0
            self._speech_frame_count += 1
            
            if not self._is_speaking:
                if self._speech_frame_count >= self._min_speech_frames:
                    self._is_speaking = True
                    self._speech_buffer = []
                    logger.debug("VAD: Speech started (prob=%.3f)", speech_prob)
                    if self._on_speech_start:
                        self._on_speech_start()
                    # Include pre-speech buffer
                    self._speech_buffer.append(audio_chunk)
                    return "speech_start"
            else:
                self._speech_buffer.append(audio_chunk)
        else:
            self._speech_frame_count = 0
            
            if self._is_speaking:
                self._silence_frame_count += 1
                self._speech_buffer.append(audio_chunk)  # include trailing silence
                
                if self._silence_frame_count >= self._min_silence_frames:
                    self._is_speaking = False
                    segment = b"".join(self._speech_buffer)
                    self._speech_buffer = []
                    self._silence_frame_count = 0
                    logger.debug("VAD: Speech ended (%d bytes)", len(segment))
                    if self._on_speech_end:
                        self._on_speech_end(segment)
                    return "speech_end"
        
        return None
    
    def get_speech_buffer(self) -> bytes:
        """Get current speech buffer."""
        return b"".join(self._speech_buffer)
    
    def pause(self):
        """Pause VAD processing."""
        self._paused = True
    
    def resume(self, mode: str = "speech"):
        """Resume VAD processing and reset state."""
        self._paused = False
        self._is_speaking = False
        self._speech_buffer = []
        self._silence_frame_count = 0
        self._speech_frame_count = 0
        
        if self._model:
            self._model.reset_states()
        
        logger.debug("VAD resumed (mode=%s)", mode)
    
    def reset(self):
        """Reset all state."""
        self._is_speaking = False
        self._speech_buffer = []
        self._silence_frame_count = 0
        self._speech_frame_count = 0
        self._paused = False
        
        if self._model:
            self._model.reset_states()
    
    @property
    def is_speaking(self) -> bool:
        return self._is_speaking
    
    @property
    def is_paused(self) -> bool:
        return self._paused