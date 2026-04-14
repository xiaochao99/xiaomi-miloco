# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
VAD (Voice Activity Detection) service module.

Reference: open-xiaoai-bridge/core/services/audio/vad/__init__.py
"""

from miloco_server.xiaomi_bridge.services.audio.vad.silero import SileroVAD

VAD = SileroVAD