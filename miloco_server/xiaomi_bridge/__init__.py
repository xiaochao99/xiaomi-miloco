# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Xiaomi Speaker Bridge Module

Integrates open-xiaoai-bridge capabilities into miloco_server:
- Keyword wakeup (KWS) for entering Miloco conversation mode
- Voice Activity Detection (VAD) for speech segmentation
- Automatic Speech Recognition (ASR) for speech-to-text
- Text-to-Speech (TTS) for Miloco reply playback
- Conversation controller for continuous dialogue
- Audio streaming via WebSocket for real-time audio processing

Reference: https://github.com/coderzc/open-xiaoai-bridge
"""

from miloco_server.xiaomi_bridge.conversation import MilocoConversationController, ConversationState
from miloco_server.xiaomi_bridge.config import BridgeConfig
from miloco_server.xiaomi_bridge.manager import BridgeManager, get_bridge_manager, init_bridge
from miloco_server.xiaomi_bridge.vad import VADManager
from miloco_server.xiaomi_bridge.kws import KWSManager
from miloco_server.xiaomi_bridge.asr import ASRManager
from miloco_server.xiaomi_bridge.tts import TTSService
from miloco_server.xiaomi_bridge.audio_stream import AudioStreamManager, get_audio_stream_manager

__all__ = [
    "MilocoConversationController",
    "ConversationState",
    "BridgeConfig",
    "BridgeManager",
    "get_bridge_manager",
    "init_bridge",
    "VADManager",
    "KWSManager",
    "ASRManager",
    "TTSService",
    "AudioStreamManager",
    "get_audio_stream_manager",
]