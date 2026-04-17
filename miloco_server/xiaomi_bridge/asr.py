# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
ASR (Automatic Speech Recognition) module.
Uses sherpa-onnx for offline speech recognition.

Supported backends:
  - sense_voice (default): SenseVoice multilingual model
  - paraformer: Paraformer Chinese model
  - fire_red_asr: FireRedASR AED model

Reference: open-xiaoai-bridge/core/services/audio/asr/sherpa.py
"""

from __future__ import annotations

import logging
import os
from typing import Optional, Dict

import numpy as np

logger = logging.getLogger(__name__)

_BACKENDS = {
    "sense_voice": {
        "dir_keyword": "sense-voice",
        "factory": "from_sense_voice",
        "extra_kwargs": {"language": "auto", "use_itn": True},
        "model_files": {"model": {True: "model.int8.onnx", False: "model.onnx"}},
    },
    "paraformer": {
        "dir_keyword": "paraformer",
        "factory": "from_paraformer",
        "extra_kwargs": {},
        "model_files": {"paraformer": {True: "model.int8.onnx", False: "model.onnx"}},
    },
    "fire_red_asr": {
        "dir_keyword": "fire-red-asr",
        "factory": "from_fire_red_asr",
        "extra_kwargs": {},
        "model_files": {
            "encoder": {True: "encoder.int8.onnx", False: "encoder.onnx"},
            "decoder": {True: "decoder.int8.onnx", False: "decoder.onnx"},
        },
    },
}


class ASRManager:
    """
    ASR manager using sherpa-onnx.
    Supports multiple model backends.
    """
    
    def __init__(
        self,
        backend: str = "sense_voice",
        model_dir: str = "",
        use_int8: bool = True,
        num_threads: int = 2,
        replacements: Dict[str, str] = None,
    ):
        self._backend = backend
        self._model_dir = model_dir
        self._use_int8 = use_int8
        self._num_threads = num_threads
        self._replacements = replacements or {}
        self._recognizer = None
        self._initialized = False
    
    def _get_required_model_files(self) -> dict[str, str]:
        """Get required model files for current backend."""
        if self._backend not in _BACKENDS:
            raise ValueError(f"Unknown ASR model '{self._backend}'. Supported: {', '.join(_BACKENDS)}")
        spec = _BACKENDS[self._backend]
        return {
            arg_name: filenames[self._use_int8]
            for arg_name, filenames in spec["model_files"].items()
        }
    
    def _dir_has_required_files(self, path: str, required_files: dict[str, str]) -> bool:
        """Check if directory has all required files."""
        return all(
            os.path.isfile(os.path.join(path, filename))
            for filename in required_files.values()
        )
    
    def _find_model_dir(self, keyword: str, required_files: dict[str, str]) -> str:
        """Find model directory."""
        # If explicit model dir is configured, use it
        if self._model_dir:
            if os.path.isdir(self._model_dir) and self._dir_has_required_files(self._model_dir, required_files):
                return self._model_dir
            # Try as subdirectory of models root
            if os.path.isdir(self._model_dir):
                missing = [
                    f for f in required_files.values()
                    if not os.path.isfile(os.path.join(self._model_dir, f))
                ]
                raise FileNotFoundError(
                    f"Model dir '{self._model_dir}' missing files: {missing}"
                )
        
        raise FileNotFoundError(
            f"No '{keyword}' model found. "
            f"Please configure MILOCO_ASR_MODEL_DIR or place model files."
        )
    
    def initialize(self):
        """Initialize ASR recognizer."""
        try:
            import sherpa_onnx
            
            if self._backend not in _BACKENDS:
                logger.error("Unknown ASR backend: %s", self._backend)
                return
            
            spec = _BACKENDS[self._backend]
            required_files = self._get_required_model_files()
            
            try:
                model_dir = self._find_model_dir(spec["dir_keyword"], required_files)
            except FileNotFoundError as e:
                logger.warning("ASR model not found: %s", e)
                return
            
            model_kwargs = {
                arg_name: os.path.join(model_dir, filename)
                for arg_name, filename in required_files.items()
            }
            tokens_path = os.path.join(model_dir, "tokens.txt")
            
            if not os.path.isfile(tokens_path):
                logger.error("Missing tokens.txt in model dir: %s", model_dir)
                return
            
            factory = getattr(sherpa_onnx.OfflineRecognizer, spec["factory"])
            self._recognizer = factory(
                **model_kwargs,
                tokens=tokens_path,
                num_threads=self._num_threads,
                debug=False,
                provider="cpu",
                **spec["extra_kwargs"],
            )
            
            self._initialized = True
            logger.info(
                "ASR initialized: backend=%s, model_dir=%s, int8=%s",
                self._backend, model_dir, self._use_int8,
            )
            
        except ImportError:
            logger.warning("sherpa-onnx not available, ASR disabled")
        except Exception as e:
            logger.error("Failed to initialize ASR: %s", e)
    
    def transcribe(self, pcm_bytes: bytes, sample_rate: int = 16000) -> str:
        """
        Transcribe audio to text.
        
        Args:
            pcm_bytes: Raw PCM audio data (int16, mono)
            sample_rate: Sample rate of the audio
            
        Returns:
            Recognized text or empty string
        """
        if not self._initialized or not self._recognizer:
            return ""
        
        try:
            samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            
            stream = self._recognizer.create_stream()
            stream.accept_waveform(sample_rate, samples)
            self._recognizer.decode_stream(stream)
            
            text = stream.result.text.strip()
            
            # Apply text replacements
            if text:
                for old, new in self._replacements.items():
                    text = text.replace(old, new)
                logger.debug("ASR recognized: %s", text[:50])
            
            return text
            
        except Exception as e:
            logger.error("ASR transcription failed: %s", e)
            return ""
    
    @property
    def is_initialized(self) -> bool:
        return self._initialized