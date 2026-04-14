# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
WebSocket routes for Xiaomi Bridge.

Reference: open-xiaoai-bridge/core/routes/websocket.py
"""

import asyncio
from typing import Dict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from miloco_server.xiaomi_bridge.services.protocols.websocket_protocol import WebSocketProtocol
from miloco_server.xiaomi_bridge.services.audio.stream import AudioStreamHandler
from miloco_server.xiaomi_bridge.utils.logger import logger

websocket_router = APIRouter()

# Connected clients
_clients: Dict[str, WebSocketProtocol] = {}


@websocket_router.websocket("/ws/audio")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for audio streaming."""
    await websocket.accept()
    
    # Generate client ID
    import uuid
    client_id = str(uuid.uuid4())
    
    # Create protocol handler
    protocol = WebSocketProtocol(websocket)
    
    # Store client
    _clients[client_id] = protocol
    
    logger.info(f"[WS] Client connected: {client_id}")
    
    # Set audio callback
    def audio_callback(audio_data: bytes):
        # Forward audio to audio stream handler
        AudioStreamHandler.instance().process_audio_input(audio_data)
    
    protocol.set_audio_callback(audio_callback)
    
    # Set message callback
    def message_callback(data: Dict):
        logger.debug(f"[WS] Received message: {data}")
    
    protocol.set_message_callback(message_callback)
    
    try:
        # Start receiving messages
        await protocol.receive_messages()
    except WebSocketDisconnect:
        logger.info(f"[WS] Client disconnected: {client_id}")
    except Exception as e:
        logger.error(f"[WS] Client error: {client_id}, {e}")
    finally:
        # Remove client
        _clients.pop(client_id, None)
        logger.info(f"[WS] Client removed: {client_id}")


@websocket_router.websocket("/ws/control")
async def control_websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for control commands."""
    await websocket.accept()
    
    client_id = str(uuid.uuid4())
    logger.info(f"[WS] Control client connected: {client_id}")
    
    try:
        while True:
            data = await websocket.receive_json()
            command = data.get("command")
            
            if command == "start_conversation":
                from miloco_server.xiaomi_bridge.conversation_controller import ConversationController
                controller = ConversationController.instance()
                asyncio.create_task(controller.start())
                await websocket.send_json({"status": "ok", "message": "Conversation started"})
            
            elif command == "stop_conversation":
                from miloco_server.xiaomi_bridge.conversation_controller import ConversationController
                controller = ConversationController.instance()
                controller.stop()
                await websocket.send_json({"status": "ok", "message": "Conversation stopped"})
            
            elif command == "get_status":
                from miloco_server.xiaomi_bridge.main_app import MainApp
                app = MainApp.instance()
                status = {
                    "device_state": app.device_state.value,
                    "is_conversation_active": False,
                }
                await websocket.send_json({"status": "ok", "data": status})
            
            else:
                await websocket.send_json({"status": "error", "message": f"Unknown command: {command}"})
    
    except WebSocketDisconnect:
        logger.info(f"[WS] Control client disconnected: {client_id}")
    except Exception as e:
        logger.error(f"[WS] Control client error: {client_id}, {e}")


async def broadcast_audio(audio_data: bytes):
    """Broadcast audio to all connected clients."""
    for client_id, protocol in _clients.items():
        try:
            await protocol.send_audio(audio_data)
        except Exception as e:
            logger.error(f"[WS] Failed to send audio to {client_id}: {e}")


async def send_audio_to_client(client_id: str, audio_data: bytes):
    """Send audio to specific client."""
    protocol = _clients.get(client_id)
    if protocol:
        try:
            await protocol.send_audio(audio_data)
        except Exception as e:
            logger.error(f"[WS] Failed to send audio to {client_id}: {e}")


def get_client_count() -> int:
    """Get number of connected clients."""
    return len(_clients)