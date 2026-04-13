# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Xiaomi Bridge Controller
API endpoints for Xiaomi speaker bridge functionality.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from miloco_server.xiaomi_bridge.conversation import MilocoConversationController
from miloco_server.xiaomi_bridge.audio_stream import get_audio_stream_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/xiaomi-bridge", tags=["Xiaomi Bridge"])


class WakeupRequest(BaseModel):
    """Wakeup request model."""
    text: str = ""


class TextRequest(BaseModel):
    """Text input request model."""
    text: str


class BridgeStatus(BaseModel):
    """Bridge status response model."""
    enabled: bool
    active: bool
    state: str


class BridgeConfigRequest(BaseModel):
    """Bridge configuration request."""
    wakeup_keywords: Optional[list[str]] = None
    exit_keywords: Optional[list[str]] = None
    tts_engine: Optional[str] = None


@router.get("/status", response_model=BridgeStatus)
async def get_bridge_status():
    """Get Xiaomi bridge status."""
    from miloco_server.xiaomi_bridge.manager import get_bridge_manager
    manager = get_bridge_manager()
    return BridgeStatus(
        enabled=manager.is_enabled,
        active=manager.conversation_controller.is_active,
        state=manager.conversation_controller.state.value,
    )


@router.post("/wakeup")
async def trigger_wakeup(request: WakeupRequest):
    """Manually trigger wakeup for Miloco conversation."""
    controller = MilocoConversationController.instance()
    await controller.on_wakeup(request.text)
    return {"success": True, "message": "Wakeup triggered"}


@router.post("/text")
async def process_text(request: TextRequest):
    """Process text input through Miloco conversation."""
    controller = MilocoConversationController.instance()
    if not controller.is_active:
        raise HTTPException(status_code=400, detail="Conversation not active")
    
    response = await controller.process_text(request.text)
    if response is None:
        return {"success": False, "message": "Exit keyword detected or no response"}
    return {"success": True, "response": response}


@router.post("/stop")
async def stop_conversation():
    """Stop Miloco conversation mode."""
    controller = MilocoConversationController.instance()
    await controller.stop()
    return {"success": True, "message": "Conversation stopped"}


@router.post("/config")
async def update_config(request: BridgeConfigRequest):
    """Update bridge configuration."""
    from miloco_server.xiaomi_bridge.manager import get_bridge_manager
    manager = get_bridge_manager()
    
    if request.wakeup_keywords is not None:
        manager.conversation_controller.configure(wakeup_keywords=request.wakeup_keywords)
    if request.exit_keywords is not None:
        manager.conversation_controller.configure(exit_keywords=request.exit_keywords)
    
    return {"success": True, "message": "Configuration updated"}


@router.websocket("/ws/audio")
async def audio_stream_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for audio streaming from Xiaomi speaker.
    Receives raw audio data for VAD/ASR processing.
    """
    manager = get_audio_stream_manager()
    
    # Extract client ID from query params or use default
    client_id = websocket.query_params.get("client_id", "default")
    
    try:
        await manager.handle_connection(websocket, client_id)
    except WebSocketDisconnect:
        logger.info("Audio stream client disconnected: %s", client_id)
    except Exception as e:
        logger.error("Audio stream error: %s", e)
        try:
            await websocket.close(code=1011, reason=f"Server error: {str(e)}")
        except Exception:
            pass