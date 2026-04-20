# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Xiaomi Bridge Configuration Schema
Data models for Xiaomi speaker bridge configuration management.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class VADConfigSchema(BaseModel):
    """VAD (Voice Activity Detection) configuration schema."""
    threshold: float = Field(0.10, ge=0, le=1, description="检测阈值 (0-1, 越小越灵敏)")
    min_speech_duration_ms: int = Field(250, ge=0, description="最小语音时长 (ms)")
    min_silence_duration_ms: int = Field(500, ge=0, description="最小静默时长 (ms)")
    model_path: str = Field("models/vad/silero_vad.onnx", description="VAD模型路径")


class KWSConfigSchema(BaseModel):
    """KWS (Keyword Spotting) configuration schema."""
    keywords: List[str] = Field(default_factory=lambda: ["小米同学"], description="唤醒词列表")
    keywords_score: float = Field(2.0, description="唤醒词置信度加成")
    keywords_threshold: float = Field(0.2, ge=0, le=1, description="唤醒词检测阈值")
    model_dir: str = Field("models/kws/sherpa-onnx-kws", description="KWS模型目录")


class ASRConfigSchema(BaseModel):
    """ASR (Automatic Speech Recognition) configuration schema."""
    model: str = Field("sense_voice", description="ASR模型: sense_voice / paraformer / fire_red_asr")
    int8: bool = Field(True, description="使用INT8量化模型")
    model_dir: str = Field("models/asr/sense-voice", description="ASR模型目录")
    num_threads: int = Field(2, ge=1, description="ASR推理线程数")


class TTSConfigSchema(BaseModel):
    """TTS (Text-to-Speech) configuration schema."""
    engine: str = Field("doubao", description="TTS引擎: doubao / xiaoai / mimo")
    app_id: str = Field("", description="豆包App ID")
    access_key: str = Field("", description="豆包Access Key")
    api_key: str = Field("", description="MiMo API Key")
    api_base_url: str = Field("https://api.xiaomimimo.com", description="MiMo API URL")
    default_speaker: str = Field("zh_female_vv_uranus_bigtts", description="默认音色")
    audio_format: str = Field("pcm", description="音频格式: pcm / mp3")
    stream: bool = Field(True, description="流式播放")
    speed: float = Field(1.0, ge=0.5, le=2.0, description="语速 (0.5-2.0)")


class AudioInputConfigSchema(BaseModel):
    """Audio input configuration schema."""
    gain: float = Field(1.0, description="输入增益")


class BridgeConfigSchema(BaseModel):
    """Complete Xiaomi Bridge configuration schema."""
    enabled: bool = Field(False, description="启用桥接（必须通过Web UI配置启用）")
    
    vad: VADConfigSchema = Field(default_factory=VADConfigSchema)
    kws: KWSConfigSchema = Field(default_factory=KWSConfigSchema)
    asr: ASRConfigSchema = Field(default_factory=ASRConfigSchema)
    tts: TTSConfigSchema = Field(default_factory=TTSConfigSchema)
    audio_input: AudioInputConfigSchema = Field(default_factory=AudioInputConfigSchema)
    
    exit_keywords: List[str] = Field(default_factory=lambda: ["退出", "结束对话", "停止"], description="退出关键词")
    wakeup_timeout: int = Field(20, ge=5, description="超时时间 (秒)")
    wakeup_opening_reply: str = Field("", description="唤醒后回复语")
    
    sample_rate: int = Field(16000, description="采样率")
    ws_port: int = Field(4399, ge=1, le=65535, description="WebSocket服务器端口")
    ws_host: str = Field("0.0.0.0", description="WebSocket服务器地址")


class BridgeConfigUpdateRequest(BaseModel):
    """Request model for updating bridge configuration."""
    config: BridgeConfigSchema


class BridgeConfigResponse(BaseModel):
    """Response model for bridge configuration."""
    code: int = Field(0)
    message: str = Field("success")
    data: Optional[BridgeConfigSchema] = None


class BridgeRestartResponse(BaseModel):
    """Response model for bridge restart."""
    code: int = Field(0)
    message: str = Field("success")
    data: Optional[dict] = None
