# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Sherpa ASR implementation for Xiaomi Bridge.

Reference: open-xiaoai-bridge/core/services/audio/asr/sherpa.py
"""

import os
import threading

import sherpa_onnx

from miloco_server.xiaomi_bridge.utils.logger import logger


class SherpaASR:
    """Sherpa Automatic Speech Recognition."""

    _instance = None
    _recognizer = None
    _initialized = False
    _model_loaded = False
    _load_lock = threading.Lock()

    # Config
    _model = "sense_voice"
    _model_dir = "models/asr"
    _int8 = True
    _num_threads = 2

    @classmethod
    def instance(cls) -> "SherpaASR":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        """Initialize ASR."""
        pass

    @classmethod
    def set_config(
        cls,
        model: str = "sense_voice",
        model_dir: str = "models/asr",
        int8: bool = True,
        num_threads: int = 2,
    ):
        """Set ASR configuration."""
        cls._model = model
        cls._model_dir = model_dir
        cls._int8 = int8
        cls._num_threads = num_threads

    @classmethod
    def initialize(cls):
        """Initialize ASR engine."""
        if cls._initialized:
            return

        cls._ensure_loaded()
        cls._initialized = True
        logger.info("[ASR] Sherpa ASR initialized with model: %s", cls._model)

    @classmethod
    def _ensure_loaded(cls):
        """Ensure model is loaded (thread-safe)."""
        with cls._load_lock:
            if cls._model_loaded:
                return

            cls._load_model()
            cls._model_loaded = True

    @classmethod
    def _load_model(cls):
        """Load Sherpa ASR model."""
        if cls._recognizer is not None:
            return

        model_dir = cls._model_dir
        if not os.path.exists(model_dir):
            logger.error(f"[ASR] Model directory not found: {model_dir}")
            raise FileNotFoundError(f"ASR model directory not found: {model_dir}")

        backend_config = cls._get_backend_config(model_dir)
        if not backend_config:
            logger.error(f"[ASR] Unsupported model: {cls._model}")
            raise ValueError(f"Unsupported ASR model: {cls._model}")

        try:
            cls._recognizer = backend_config["factory"](
                model_dir=model_dir,
                use_int8=cls._int8,
                num_threads=cls._num_threads,
                **backend_config.get("extra_kwargs", {}),
            )
            logger.info(f"[ASR] Sherpa ASR model loaded: {cls._model}")
        except Exception as e:
            logger.error(f"[ASR] Failed to load Sherpa ASR model: {e}")
            raise

    @classmethod
    def _get_backend_config(cls, model_dir: str):
        """Get backend configuration for the selected model."""
        backends = {
            "sense_voice": {
                "factory": cls._create_sense_voice_recognizer,
                "extra_kwargs": {"language": "auto", "use_itn": True},
            },
            "paraformer": {
                "factory": cls._create_paraformer_recognizer,
                "extra_kwargs": {},
            },
        }
        return backends.get(cls._model)

    @classmethod
    def _create_sense_voice_recognizer(
        cls,
        model_dir: str,
        use_int8: bool = True,
        num_threads: int = 2,
        **kwargs
    ):
        """Create SenseVoice recognizer."""
        model_file = "model.int8.onnx" if use_int8 else "model.onnx"
        return sherpa_onnx.OfflineRecognizer.from_sense_voice(
            encoder=os.path.join(model_dir, model_file),
            decoder=os.path.join(model_dir, "decoder.onnx"),
            joiner=os.path.join(model_dir, "joiner.onnx"),
            tokens=os.path.join(model_dir, "tokens.txt"),
            num_threads=num_threads,
            **kwargs
        )

    @classmethod
    def _create_paraformer_recognizer(
        cls,
        model_dir: str,
        use_int8: bool = True,
        num_threads: int = 2,
        **kwargs
    ):
        """Create Paraformer recognizer."""
        return sherpa_onnx.OfflineRecognizer.from_paraformer(
            encoder=os.path.join(model_dir, "encoder-epoch-99-avg.onnx"),
            decoder=os.path.join(model_dir, "decoder-epoch-99-avg.onnx"),
            tokens=os.path.join(model_dir, "tokens.txt"),
            num_threads=num_threads,
            **kwargs
        )

    @classmethod
    def asr(cls, audio_data: bytes, sample_rate: int = 16000) -> str:
        """
        Perform speech recognition on audio data.
        
        Args:
            audio_data: PCM audio bytes (int16, 16kHz, mono)
            sample_rate: Audio sample rate (default: 16000)
        
        Returns:
            Recognized text, or empty string if recognition failed
        """
        if not cls._initialized:
            cls.initialize()

        if cls._recognizer is None:
            logger.error("[ASR] Recognizer not loaded")
            return ""

        try:
            # Convert int16 bytes to float32
            samples = sherpa_onnx.int16_to_float32(audio_data)
            
            # Create offline stream
            stream = cls._recognizer.create_stream()
            stream.accept_waveform(sample_rate, samples)
            
            # Decode
            cls._recognizer.decode_stream(stream)
            result = stream.result
            
            text = result.text.strip()
            logger.debug(f"[ASR] Recognized: {text}")
            return text
        except Exception as e:
            logger.error(f"[ASR] Recognition failed: {e}")
            return ""

    @classmethod
    def is_initialized(cls) -> bool:
        """Check if ASR is initialized."""
        return cls._initialized

    @classmethod
    def reset(cls):
        """Reset ASR state."""
        cls._model_loaded = False
        cls._recognizer = None
        cls._initialized = False