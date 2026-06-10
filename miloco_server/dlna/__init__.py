# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
DLNA Module - UPnP/DLNA device discovery and media casting.
DLNA模块 - UPnP/DLNA设备发现与媒体投屏
"""

from miloco_server.dlna.dlna_service import DLNAService, get_dlna_service

__all__ = ["DLNAService", "get_dlna_service"]
