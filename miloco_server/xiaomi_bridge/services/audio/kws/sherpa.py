# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Sherpa KWS implementation for Xiaomi Bridge.

Reference: open-xiaoai-bridge/core/services/audio/kws/sherpa.py
"""

import os
import threading

import sherpa_onnx

from miloco_server.xiaomi_bridge.utils.logger import logger


class SherpaKWS:
    """Sherpa Keyword Spotting."""

    _instance = None
    _spotter = None
    _running = False
    _lock = threading.Lock()

    # Config
    _keywords = ["小米同学"]
    _keywords_score = 2.0
    _keywords_threshold = 0.2
    _model_dir = "models/kws"

    # Callback
    _on_keyword_callback = None

    @classmethod
    def instance(cls) -> "SherpaKWS":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        """Initialize KWS."""
        pass

    @classmethod
    def set_config(
        cls,
        keywords: list = None,
        keywords_score: float = 2.0,
        keywords_threshold: float = 0.2,
        model_dir: str = "models/kws",
    ):
        """Set KWS configuration."""
        if keywords is not None:
            cls._keywords = keywords
        cls._keywords_score = keywords_score
        cls._keywords_threshold = keywords_threshold
        cls._model_dir = model_dir

    @classmethod
    def start(cls):
        """Start KWS processing."""
        if cls._running:
            return

        cls._load_model()
        cls._running = True
        logger.info("[KWS] Sherpa KWS started with keywords: %s", cls._keywords)

    @classmethod
    def stop(cls):
        """Stop KWS processing."""
        cls._running = False
        cls._spotter = None
        logger.info("[KWS] Sherpa KWS stopped")

    @classmethod
    def _load_model(cls):
        """Load Sherpa KWS model."""
        if cls._spotter is not None:
            return

        model_dir = cls._model_dir
        if not os.path.exists(model_dir):
            logger.error(f"[KWS] Model directory not found: {model_dir}")
            raise FileNotFoundError(f"KWS model directory not found: {model_dir}")

        # Create keywords file
        keywords_file = os.path.join(model_dir, "keywords.txt")
        with open(keywords_file, "w", encoding="utf-8") as f:
            for kw in cls._keywords:
                f.write(f"{kw} /{cls._keywords_score}/\n")

        try:
            cls._spotter = sherpa_onnx.KeywordSpotter(
                provider="cpu",
                num_threads=1,
                max_active_paths=8,
                keywords_score=cls._keywords_score,
                keywords_threshold=cls._keywords_threshold,
                num_trailing_blanks=0,
                keywords_file=keywords_file,
                tokens=os.path.join(model_dir, "tokens.txt"),
                encoder=os.path.join(model_dir, "encoder.onnx"),
                decoder=os.path.join(model_dir, "decoder.onnx"),
                joiner=os.path.join(model_dir, "joiner.onnx"),
            )
            logger.info("[KWS] Sherpa KWS model loaded")
        except Exception as e:
            logger.error(f"[KWS] Failed to load Sherpa KWS model: {e}")
            raise

    @classmethod
    def process_audio(cls, audio_data: bytes):
        """
        Process audio data for keyword spotting.
        
        Args:
            audio_data: PCM audio bytes (int16, 16kHz, mono)
        """
        if not cls._running or cls._spotter is None:
            return None

        with cls._lock:
            samples = sherpa_onnx.float32_to_int16(
                sherpa_onnx.int16_to_float32(audio_data)
            )
            result = cls._spotter.decode(samples)

            if result.keyword:
                detected = result.keyword.strip()
                logger.info(f"[KWS] Keyword detected: {detected}")
                
                # Check if detected keyword matches configured keywords
                for kw in cls._keywords:
                    if kw in detected or detected in kw:
                        if cls._on_keyword_callback:
                            cls._on_keyword_callback(detected)
                        return detected

        return None

    @classmethod
    def set_callback(cls, callback):
        """Set keyword detected callback."""
        cls._on_keyword_callback = callback

    @classmethod
    def is_running(cls) -> bool:
        """Check if KWS is running."""
        return cls._running

    @classmethod
    def reset(cls):
        """Reset KWS state."""
        if cls._spotter:
            cls._spotter.reset()

    @classmethod
    def get_keywords(cls) -> list:
        """Get configured keywords."""
        return cls._keywords