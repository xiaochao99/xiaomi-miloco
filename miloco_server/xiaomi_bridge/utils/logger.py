# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Logger utilities for Xiaomi Bridge.

Reference: open-xiaoai-bridge/core/utils/logger.py
"""

import logging
from typing import Optional

logger = logging.getLogger("xiaomi-bridge")


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """Get logger with optional module name."""
    if name:
        return logging.getLogger(f"xiaomi-bridge.{name}")
    return logger