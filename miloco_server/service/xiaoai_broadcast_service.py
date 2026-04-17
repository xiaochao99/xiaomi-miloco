"""
XiaoAI broadcast service.

This service broadcasts text to XiaoAI speakers via the integrated Xiaomi Bridge
(open-xiaoai Rust client over WS/RPC on port 4399).
"""

from __future__ import annotations

import logging
import os
from typing import Optional, List

logger = logging.getLogger(__name__)


def _is_enabled() -> bool:
    # Keep as a safety switch for auto-broadcast (e.g., chat replies).
    value = str(os.getenv("MILOCO_XIAOAI_BROADCAST_ENABLED", "0")).strip().lower()
    return value in {"1", "true", "yes", "on"}


def _extract_speak_text(response_text: str) -> str:
    if not response_text:
        return ""

    from miloco_server.utils.structured_tags import extract_final_answer

    final_answer = extract_final_answer(response_text)
    return (final_answer or response_text).strip()


async def broadcast_chat_reply(response_text: str, client_ids: Optional[List[str]] = None) -> bool:
    """
    Broadcast chat reply via the integrated Xiaomi Bridge.

    Controlled by environment variable:
    - MILOCO_XIAOAI_BROADCAST_ENABLED: 1/true to enable
    """
    if not _is_enabled():
        return False
    speak_text = _extract_speak_text(response_text)
    if not speak_text:
        return False
    return await broadcast_via_bridge(speak_text, client_ids=client_ids)


async def broadcast_via_bridge(text: str, client_ids: Optional[List[str]] = None) -> bool:
    """
    Broadcast text to Xiaomi speakers via the integrated Xiaomi Bridge.
    
    Args:
        text: The text to speak
        client_ids: Optional list of specific device IDs to send to. 
                   If None, broadcasts to all connected devices.
    
    Returns:
        True if successful, False otherwise.
    """
    if not text:
        logger.warning("Empty text to broadcast")
        return False
    
    try:
        from miloco_server.xiaomi_bridge.tts import TTSService
        from miloco_server.xiaomi_bridge.shell_utils import build_mibrain_tts_script
        
        # Get TTS service
        tts = TTSService.instance()
        if not tts.is_initialized:
            ok = await tts.initialize()
            if not ok:
                logger.error("TTS service not configured")
                return False
        
        # Check if using Xiaomi native TTS
        if tts.engine == "xiaoai":
            from miloco_server.xiaomi_bridge.audio_stream import get_audio_stream_manager
            manager = get_audio_stream_manager()
            await manager.run_shell(build_mibrain_tts_script(text), client_ids=client_ids)
            
            target = "all devices" if client_ids is None else f"devices {client_ids}"
            logger.info(f"Broadcast XiaoAI TTS via Xiaomi Bridge to {target}: {text[:50]}...")
            return True
        else:
            # Use external TTS engine (e.g., Doubao/MiMo) via the unified playback path.
            # This ensures the same buffering/session/pacing logic as /xiaomi-bridge/tts.
            ok = await tts.speak(text, speaker=None, client_ids=client_ids)
            if not ok:
                logger.error("TTS speak failed (engine=%s)", tts.engine)
                return False

            target = "all devices" if client_ids is None else f"devices {client_ids}"
            logger.info(f"Broadcast via Xiaomi Bridge to {target}: {text[:50]}...")
            return True
        
    except Exception as e:
        logger.error(f"Failed to broadcast via Xiaomi Bridge: {e}")
        return False


async def get_connected_devices() -> List[dict]:
    """
    Get list of connected Xiaomi speakers via Xiaomi Bridge.
    
    Returns:
        List of device info dictionaries with client_id, device_name, ip_address, etc.
    """
    try:
        from miloco_server.xiaomi_bridge.audio_stream import get_audio_stream_manager
        
        manager = get_audio_stream_manager()
        return manager.get_all_devices()
    except Exception as e:
        logger.error(f"Failed to get connected devices: {e}")
        return []
