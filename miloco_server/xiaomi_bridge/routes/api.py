# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
REST API routes for Xiaomi Bridge.

Reference: open-xiaoai-bridge/core/routes/api.py
"""

from fastapi import APIRouter, HTTPException

from miloco_server.xiaomi_bridge.services.audio.vad import VAD
from miloco_server.xiaomi_bridge.services.audio.kws import KWS
from miloco_server.xiaomi_bridge.services.audio.asr.sherpa import SherpaASR
from miloco_server.xiaomi_bridge.services.audio.tts.doubao import DoubaoTTS
from miloco_server.xiaomi_bridge.conversation_controller import ConversationController
from miloco_server.xiaomi_bridge.routes.websocket import get_client_count
from miloco_server.xiaomi_bridge.utils.config import ConfigManager
from miloco_server.xiaomi_bridge.utils.logger import logger

api_router = APIRouter(prefix="/api/v1")


@api_router.get("/health")
async def health_check():
    """Check service health."""
    return {"status": "healthy", "service": "xiaomi-bridge"}


@api_router.get("/status")
async def get_status():
    """Get bridge status."""
    from miloco_server.xiaomi_bridge.main_app import MainApp
    app = MainApp.instance()
    
    controller = ConversationController.instance()
    
    return {
        "device_state": app.device_state.value,
        "conversation_active": controller.is_active(),
        "vad_running": VAD.is_running(),
        "kws_running": KWS.is_running(),
        "asr_initialized": SherpaASR.is_initialized(),
        "tts_initialized": DoubaoTTS.is_initialized(),
        "connected_clients": get_client_count(),
        "current_text": app.current_text,
        "current_emotion": app.current_emotion,
    }


@api_router.get("/config")
async def get_config():
    """Get current configuration."""
    config = ConfigManager.instance()
    return config.get_app_config()


@api_router.post("/config/reload")
async def reload_config():
    """Reload configuration."""
    config = ConfigManager.instance()
    try:
        config.reload_app_config()
        return {"status": "ok", "message": "Config reloaded"}
    except Exception as e:
        logger.error(f"Failed to reload config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/conversation/start")
async def start_conversation():
    """Start conversation mode."""
    controller = ConversationController.instance()
    if controller.is_active():
        return {"status": "ok", "message": "Conversation already active"}
    
    import asyncio
    asyncio.create_task(controller.start())
    return {"status": "ok", "message": "Conversation started"}


@api_router.post("/conversation/stop")
async def stop_conversation():
    """Stop conversation mode."""
    controller = ConversationController.instance()
    controller.stop()
    return {"status": "ok", "message": "Conversation stopped"}


@api_router.get("/conversation/status")
async def get_conversation_status():
    """Get conversation status."""
    controller = ConversationController.instance()
    return {
        "active": controller.is_active(),
        "input_mode": controller.input_mode,
        "exit_keywords": controller.exit_keywords,
    }


@api_router.post("/tts/speak")
async def tts_speak(text: str, speaker: str = None):
    """Synthesize and play text."""
    tts = DoubaoTTS.instance()
    audio_data = await tts.synthesize(text, speaker)
    
    if audio_data:
        from miloco_server.xiaomi_bridge.services.audio.stream import AudioStreamHandler
        await AudioStreamHandler.instance().play_audio(audio_data)
        return {"status": "ok", "message": "Speech started"}
    else:
        raise HTTPException(status_code=500, detail="Failed to synthesize speech")


@api_router.get("/kws/keywords")
async def get_keywords():
    """Get configured keywords."""
    return {"keywords": KWS.get_keywords()}


@api_router.post("/kws/keywords")
async def set_keywords(keywords: list[str]):
    """Set keywords."""
    KWS.set_config(keywords=keywords)
    return {"status": "ok", "message": "Keywords updated", "keywords": keywords}


@api_router.post("/kws/reset")
async def reset_kws():
    """Reset KWS state."""
    KWS.reset()
    return {"status": "ok", "message": "KWS reset"}


@api_router.post("/vad/pause")
async def pause_vad():
    """Pause VAD."""
    VAD.pause()
    return {"status": "ok", "message": "VAD paused"}


@api_router.post("/vad/resume")
async def resume_vad(mode: str = "speech"):
    """Resume VAD."""
    VAD.resume(mode)
    return {"status": "ok", "message": f"VAD resumed in {mode} mode"}