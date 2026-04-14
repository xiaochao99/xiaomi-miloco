# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
KWS (Keyword Spotting) service module.

Reference: open-xiaoai-bridge/core/services/audio/kws/__init__.py
"""

from miloco_server.xiaomi_bridge.services.audio.kws.sherpa import SherpaKWS

KWS = SherpaKWS