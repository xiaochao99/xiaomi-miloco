# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Global references for Xiaomi Bridge components.

Reference: open-xiaoai-bridge/core/ref.py
"""

from typing import Optional

# Global references
_app = None
_speaker = None
_vad = None


def set_app(app):
    """Set global app reference."""
    global _app
    _app = app


def get_app():
    """Get global app reference."""
    return _app


def set_speaker(speaker):
    """Set global speaker reference."""
    global _speaker
    _speaker = speaker


def get_speaker():
    """Get global speaker reference."""
    return _speaker


def set_vad(vad):
    """Set global VAD reference."""
    global _vad
    _vad = vad


def get_vad():
    """Get global VAD reference."""
    return _vad