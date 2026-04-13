# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
KWS (Keyword Spotting) module.
Uses sherpa-onnx KeywordSpotter for wake word detection.

Reference: open-xiaoai-bridge/core/services/audio/kws/sherpa.py
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


class KWSManager:
    """
    Keyword Spotting manager.
    Detects wake words in audio stream.
    """
    
    def __init__(
        self,
        model_dir: str = "",
        keywords_score: float = 2.0,
        keywords_threshold: float = 0.2,
        sample_rate: int = 16000,
    ):
        self._model_dir = model_dir
        self._keywords_score = keywords_score
        self._keywords_threshold = keywords_threshold
        self._sample_rate = sample_rate
        self._spotter = None
        self._stream = None
        self._initialized = False
        
        # Custom keywords file path
        self._keywords_file = ""
    
    def initialize(self, keywords: list[str] = None):
        """Initialize KWS model."""
        try:
            import sherpa_onnx
            
            if not self._model_dir or not os.path.isdir(self._model_dir):
                logger.warning("KWS model directory not found: %s", self._model_dir)
                return
            
            # Check required files
            required_files = ["encoder.onnx", "decoder.onnx", "joiner.onnx", "tokens.txt"]
            for f in required_files:
                if not os.path.isfile(os.path.join(self._model_dir, f)):
                    logger.warning("KWS model missing file: %s", f)
                    return
            
            # Find keywords file
            keywords_file = os.path.join(self._model_dir, "keywords.txt")
            if not os.path.isfile(keywords_file):
                logger.warning("KWS keywords file not found: %s", keywords_file)
                return
            
            self._keywords_file = keywords_file
            
            self._spotter = sherpa_onnx.KeywordSpotter(
                provider="cpu",
                num_threads=1,
                max_active_paths=8,
                keywords_score=self._keywords_score,
                keywords_threshold=self._keywords_threshold,
                num_trailing_blanks=0,
                keywords_file=keywords_file,
                tokens=os.path.join(self._model_dir, "tokens.txt"),
                encoder=os.path.join(self._model_dir, "encoder.onnx"),
                decoder=os.path.join(self._model_dir, "decoder.onnx"),
                joiner=os.path.join(self._model_dir, "joiner.onnx"),
            )
            
            self._stream = self._spotter.create_stream()
            self._initialized = True
            logger.info("KWS model loaded from %s", self._model_dir)
            
        except ImportError:
            logger.warning("sherpa-onnx not available, KWS disabled")
        except Exception as e:
            logger.error("Failed to initialize KWS: %s", e)
    
    def reset(self):
        """Reset the KWS stream."""
        if self._spotter:
            self._stream = self._spotter.create_stream()
    
    def detect(self, audio_chunk: bytes) -> Optional[str]:
        """
        Detect wake word in audio chunk.
        
        Returns:
            Detected keyword (lowercase) or None
        """
        if not self._initialized or not self._spotter or not self._stream:
            return None
        
        try:
            samples = np.frombuffer(audio_chunk, dtype=np.int16).astype(np.float32) / 32768.0
            self._stream.accept_waveform(self._sample_rate, samples)
            
            while self._spotter.is_ready(self._stream):
                self._spotter.decode_stream(self._stream)
                result = self._spotter.get_result(self._stream)
                if result:
                    self._spotter.reset_stream(self._stream)
                    return result.lower()
        except Exception as e:
            logger.debug("KWS detection error: %s", e)
        
        return None
    
    def is_keyword_match(self, text: str, keywords: list[str]) -> Optional[str]:
        """
        Check if text contains any keyword.
        
        Returns:
            Matched keyword or None
        """
        text_lower = text.lower()
        for keyword in keywords:
            if keyword.lower() in text_lower:
                return keyword
        return None
    
    @property
    def is_initialized(self) -> bool:
        return self._initialized