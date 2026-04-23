# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Xiaomi Bridge Configuration Service
Handles persistence and retrieval of Xiaomi speaker bridge configuration.
"""

import json
import logging
from typing import Optional

from miloco_server.dao.kv_dao import KVDao
from miloco_server.schema.xiaomi_bridge_schema import (
    BridgeConfigSchema,
    VADConfigSchema,
    KWSConfigSchema,
    ASRConfigSchema,
    TTSConfigSchema,
    AudioInputConfigSchema,
)
from miloco_server.xiaomi_bridge.config import BridgeConfig

logger = logging.getLogger(__name__)

# Configuration key for storing bridge config in KV store
BRIDGE_CONFIG_KEY = "XIAOMI_BRIDGE_CONFIG"


class XiaomiBridgeConfigService:
    """Service for managing Xiaomi Bridge configuration."""

    _instance: Optional["XiaomiBridgeConfigService"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._kv_dao = KVDao()
        self._initialized = True
        logger.info("XiaomiBridgeConfigService initialized")

    @classmethod
    def instance(cls) -> "XiaomiBridgeConfigService":
        """Get singleton instance."""
        return cls()

    def get_config(self) -> BridgeConfigSchema:
        """
        Get the current bridge configuration.
        
        Returns:
            BridgeConfigSchema: Current configuration, defaults if not found.
        """
        try:
            config_str = self._kv_dao.get(BRIDGE_CONFIG_KEY)
            if config_str:
                config_data = json.loads(config_str)
                return BridgeConfigSchema(**config_data)
            return self._get_default_config()
        except Exception as e:
            logger.error(f"Failed to load bridge config: {e}")
            return self._get_default_config()

    def save_config(self, config: BridgeConfigSchema) -> bool:
        """
        Save the bridge configuration.
        
        Args:
            config: Configuration to save.
            
        Returns:
            bool: True if saved successfully, False otherwise.
        """
        try:
            config_str = json.dumps(config.dict(), ensure_ascii=False, indent=2)
            success = self._kv_dao.set(BRIDGE_CONFIG_KEY, config_str)
            if success:
                logger.info("Bridge configuration saved successfully")
            return success
        except Exception as e:
            logger.error(f"Failed to save bridge config: {e}")
            return False

    def _get_default_config(self) -> BridgeConfigSchema:
        """Get default configuration. Enabled is always False by default,
        user must enable it via web UI."""
        env_config = BridgeConfig.from_env()
        return BridgeConfigSchema(
            enabled=False,  # 默认不启用，必须通过Web UI配置启用
            vad=VADConfigSchema(
                threshold=env_config.vad.threshold,
                min_speech_duration_ms=env_config.vad.min_speech_duration_ms,
                min_silence_duration_ms=env_config.vad.min_silence_duration_ms,
                model_path=env_config.vad.model_path or "models/vad/silero_vad.onnx",
            ),
            kws=KWSConfigSchema(
                keywords=env_config.kws.keywords,
                keywords_score=env_config.kws.keywords_score,
                keywords_threshold=env_config.kws.keywords_threshold,
                model_dir=env_config.kws.model_dir or "models/kws/sherpa-onnx-kws",
            ),
            asr=ASRConfigSchema(
                model=env_config.asr.model,
                int8=env_config.asr.int8,
                model_dir=env_config.asr.model_dir or "models/asr/sense-voice",
                num_threads=env_config.asr.num_threads,
            ),
            tts=TTSConfigSchema(
                engine=env_config.tts.engine,
                app_id=env_config.tts.app_id,
                access_key=env_config.tts.access_key,
                api_key=env_config.tts.api_key,
                api_base_url=env_config.tts.api_base_url,
                default_speaker=env_config.tts.default_speaker,
                audio_format=env_config.tts.audio_format,
                stream=env_config.tts.stream,
                speed=env_config.tts.speed,
                mimo_tts_model=env_config.tts.mimo_tts_model,
                voice_design_description=env_config.tts.voice_design_description,
            ),
            audio_input=AudioInputConfigSchema(
                gain=env_config.audio_input.gain,
            ),
            exit_keywords=env_config.exit_keywords,
            wakeup_timeout=env_config.wakeup_timeout,
            wakeup_opening_reply=env_config.wakeup_opening_reply,
            sample_rate=env_config.sample_rate,
            ws_port=env_config.ws_port,
            ws_host=env_config.ws_host,
        )

    def to_bridge_config(self, schema: BridgeConfigSchema) -> BridgeConfig:
        """
        Convert schema to internal BridgeConfig.
        
        Args:
            schema: Schema configuration.
            
        Returns:
            BridgeConfig: Internal config object.
        """
        from miloco_server.xiaomi_bridge.config import VADConfig, KWSConfig, ASRConfig, TTSConfig, AudioInputConfig
        
        return BridgeConfig(
            enabled=schema.enabled,
            vad=VADConfig(
                threshold=schema.vad.threshold,
                min_speech_duration_ms=schema.vad.min_speech_duration_ms,
                min_silence_duration_ms=schema.vad.min_silence_duration_ms,
                model_path=schema.vad.model_path,
            ),
            kws=KWSConfig(
                keywords=schema.kws.keywords,
                keywords_score=schema.kws.keywords_score,
                keywords_threshold=schema.kws.keywords_threshold,
                model_dir=schema.kws.model_dir,
            ),
            asr=ASRConfig(
                model=schema.asr.model,
                int8=schema.asr.int8,
                model_dir=schema.asr.model_dir,
                num_threads=schema.asr.num_threads,
            ),
            tts=TTSConfig(
                engine=schema.tts.engine,
                app_id=schema.tts.app_id,
                access_key=schema.tts.access_key,
                api_key=schema.tts.api_key,
                api_base_url=schema.tts.api_base_url,
                default_speaker=schema.tts.default_speaker,
                audio_format=schema.tts.audio_format,
                stream=schema.tts.stream,
                speed=schema.tts.speed,
                mimo_tts_model=schema.tts.mimo_tts_model,
                voice_design_description=schema.tts.voice_design_description,
            ),
            audio_input=AudioInputConfig(
                gain=schema.audio_input.gain,
            ),
            exit_keywords=schema.exit_keywords,
            wakeup_timeout=schema.wakeup_timeout,
            wakeup_opening_reply=schema.wakeup_opening_reply,
            sample_rate=schema.sample_rate,
            ws_port=schema.ws_port,
            ws_host=schema.ws_host,
        )
