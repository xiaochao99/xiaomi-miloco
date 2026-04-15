# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Bridge configuration module.
Manages configuration for Xiaomi speaker bridge integration.

Reference: open-xiaoai-bridge config structure
"""

import os
from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class VADConfig:
    """VAD (Voice Activity Detection) configuration."""
    threshold: float = 0.10  # 0-1, lower = more sensitive
    min_speech_duration_ms: int = 250
    min_silence_duration_ms: int = 500
    model_path: str = "models/vad/silero_vad.onnx"  # path to silero_vad.onnx


@dataclass
class KWSConfig:
    """KWS (Keyword Spotting) configuration."""
    keywords: List[str] = field(default_factory=lambda: ["小米同学"])
    keywords_score: float = 2.0
    keywords_threshold: float = 0.2
    min_silence_duration: int = 480  # ms
    model_dir: str = "models/kws"  # path to sherpa-onnx-kws model dir


@dataclass
class ASRConfig:
    """ASR (Automatic Speech Recognition) configuration."""
    model: str = "sense_voice"  # "sense_voice" / "paraformer" / "fire_red_asr"
    int8: bool = True
    model_dir: str = "models/asr"  # explicit model directory
    replacements: Dict[str, str] = field(default_factory=dict)
    num_threads: int = 2


@dataclass
class TTSConfig:
    """TTS configuration."""
    engine: str = "doubao"  # "doubao", "xiaoai", or "mimo"
    app_id: str = ""
    access_key: str = ""
    api_key: str = ""  # For MiMo API
    api_base_url: str = "https://api.xiaomimimo.com"  # For MiMo API
    default_speaker: str = "zh_female_vv_uranus_bigtts"
    audio_format: str = "pcm"  # "pcm" or "mp3"
    stream: bool = True
    speed: float = 1.0


@dataclass
class AudioInputConfig:
    """Audio input configuration."""
    gain: float = 1.0  # input gain multiplier


@dataclass
class BridgeConfig:
    """Configuration for Xiaomi speaker bridge."""
    
    # Enable/disable bridge
    enabled: bool = False
    
    # Component configs
    vad: VADConfig = field(default_factory=VADConfig)
    kws: KWSConfig = field(default_factory=KWSConfig)
    asr: ASRConfig = field(default_factory=ASRConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    audio_input: AudioInputConfig = field(default_factory=AudioInputConfig)
    
    # Conversation settings
    exit_keywords: List[str] = field(default_factory=lambda: ["退出", "结束对话", "停止"])
    wakeup_timeout: int = 20  # seconds of silence before auto-exit
    
    # Audio settings
    sample_rate: int = 16000
    channels: int = 1
    
    # WebSocket server for audio streaming
    ws_port: int = 4399
    ws_host: str = "0.0.0.0"
    
    @classmethod
    def from_env(cls) -> "BridgeConfig":
        """Create config from environment variables."""
        return cls(
            enabled=os.getenv("MILOCO_BRIDGE_ENABLED", "0").lower() in ("1", "true", "yes"),
            
            vad=VADConfig(
                threshold=float(os.getenv("MILOCO_VAD_THRESHOLD", "0.10")),
                min_speech_duration_ms=int(os.getenv("MILOCO_VAD_MIN_SPEECH", "250")),
                min_silence_duration_ms=int(os.getenv("MILOCO_VAD_MIN_SILENCE", "500")),
                model_path=os.getenv("MILOCO_VAD_MODEL_PATH", ""),
            ),
            
            kws=KWSConfig(
                keywords=os.getenv("MILOCO_WAKEUP_KEYWORDS", "小米同学").split(","),
                keywords_score=float(os.getenv("MILOCO_KWS_SCORE", "2.0")),
                keywords_threshold=float(os.getenv("MILOCO_KWS_THRESHOLD", "0.2")),
                min_silence_duration=int(os.getenv("MILOCO_KWS_MIN_SILENCE", "480")),
                model_dir=os.getenv("MILOCO_KWS_MODEL_DIR", ""),
            ),
            
            asr=ASRConfig(
                model=os.getenv("MILOCO_ASR_MODEL", "sense_voice"),
                int8=os.getenv("MILOCO_ASR_INT8", "1").lower() in ("1", "true"),
                model_dir=os.getenv("MILOCO_ASR_MODEL_DIR", ""),
                num_threads=int(os.getenv("MILOCO_ASR_THREADS", "2")),
            ),
            
            tts=TTSConfig(
                engine=os.getenv("MILOCO_TTS_ENGINE", "doubao"),
                app_id=os.getenv("MILOCO_DOUBAO_APP_ID", ""),
                access_key=os.getenv("MILOCO_DOUBAO_ACCESS_KEY", ""),
                api_key=os.getenv("MILOCO_MIMO_API_KEY", ""),
                api_base_url=os.getenv("MILOCO_MIMO_API_URL", "https://api.xiaomimimo.com"),
                default_speaker=os.getenv("MILOCO_TTS_VOICE", "zh_female_vv_uranus_bigtts"),
                audio_format=os.getenv("MILOCO_TTS_FORMAT", "pcm"),
                stream=os.getenv("MILOCO_TTS_STREAM", "1").lower() in ("1", "true"),
                speed=float(os.getenv("MILOCO_TTS_SPEED", "1.0")),
            ),
            
            audio_input=AudioInputConfig(
                gain=float(os.getenv("MILOCO_AUDIO_GAIN", "1.0")),
            ),
            
            exit_keywords=os.getenv("MILOCO_EXIT_KEYWORDS", "退出,结束对话,停止").split(","),
            wakeup_timeout=int(os.getenv("MILOCO_WAKEUP_TIMEOUT", "20")),
            sample_rate=int(os.getenv("MILOCO_SAMPLE_RATE", "16000")),
            ws_port=int(os.getenv("MILOCO_WS_PORT", "4399")),
            ws_host=os.getenv("MILOCO_WS_HOST", "0.0.0.0"),
        )