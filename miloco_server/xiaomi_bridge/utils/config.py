# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Configuration manager for Xiaomi Bridge.

Reference: open-xiaoai-bridge/core/utils/config.py
"""

import json
import os
from typing import Any, Dict, Optional

from miloco_server.xiaomi_bridge.utils.logger import logger


class ConfigManager:
    """Singleton configuration manager."""

    _instance = None
    _app_config: Dict[str, Any] = {}
    _config_path: str = ""
    _reload_listeners = []

    @classmethod
    def instance(cls) -> "ConfigManager":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        """Initialize config manager."""
        self._config_path = os.environ.get(
            "MILOCO_BRIDGE_CONFIG_PATH",
            os.path.join(os.path.expanduser("~"), ".miloco", "bridge_config.json")
        )
        self._load_config()

    def _load_config(self):
        """Load configuration from file."""
        if os.path.exists(self._config_path):
            try:
                with open(self._config_path, "r", encoding="utf-8") as f:
                    self._app_config = json.load(f)
                logger.info(f"[Config] Loaded config from {self._config_path}")
            except Exception as e:
                logger.warning(f"[Config] Failed to load config: {e}")
                self._app_config = self._get_default_config()
        else:
            self._app_config = self._get_default_config()

    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration."""
        return {
            "bridge": {
                "enabled": False,
                "url": "ws://localhost:4399",
                "token": "",
                "session_key": "agent:main:xiaomi-bridge",
                "identity_path": "~/.miloco/identity/device.json",
                "ack_timeout": 30,
                "response_timeout": 120,
                "input_mode": "local_asr",  # local_asr or xiaoai_asr
            },
            "wakeup": {
                "keywords": ["小米同学"],
                "timeout": 20,
            },
            "exit_keywords": ["退出", "结束对话", "停止"],
            "audio": {
                "sample_rate": 16000,
                "channels": 1,
                "input_gain": 1.0,
            },
            "vad": {
                "threshold": 0.10,
                "min_speech_duration_ms": 250,
                "min_silence_duration_ms": 500,
                "model_path": "models/vad/silero_vad.onnx",
            },
            "kws": {
                "model_dir": "models/kws",
                "keywords_score": 2.0,
                "keywords_threshold": 0.2,
            },
            "asr": {
                "model": "sense_voice",
                "model_dir": "models/asr",
                "int8": True,
                "num_threads": 2,
            },
            "tts": {
                "engine": "doubao",
                "app_id": "",
                "access_key": "",
                "default_speaker": "zh_female_vv_uranus_bigtts",
                "audio_format": "pcm",
                "stream": True,
                "speed": 1.0,
            },
        }

    def get_app_config(self, key: str, default=None) -> Any:
        """Get configuration value by dotted key."""
        keys = key.split(".")
        value = self._app_config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

    def set_app_config(self, key: str, value: Any):
        """Set configuration value by dotted key."""
        keys = key.split(".")
        config = self._app_config
        for i, k in enumerate(keys[:-1]):
            if k not in config:
                config[k] = {}
            config = config[k]
        config[keys[-1]] = value

    def reload_app_config(self):
        """Reload configuration from file."""
        old_config = self._app_config.copy()
        self._load_config()
        for listener in self._reload_listeners:
            try:
                listener(old_config, self._app_config)
            except Exception as e:
                logger.error(f"[Config] Error calling reload listener: {e}")

    def add_reload_listener(self, listener):
        """Add a config reload listener."""
        self._reload_listeners.append(listener)

    def get_config_path(self) -> str:
        """Get the config file path."""
        return self._config_path

    def save_config(self):
        """Save current config to file."""
        os.makedirs(os.path.dirname(self._config_path), exist_ok=True)
        with open(self._config_path, "w", encoding="utf-8") as f:
            json.dump(self._app_config, f, ensure_ascii=False, indent=2)
            f.write("\n")
        logger.info(f"[Config] Saved config to {self._config_path}")