# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Chat controller
Handles instant queries, chat history, and WebSocket connections
Uses unified exception handling framework
"""
import json
import asyncio
import logging
from typing import Optional
from fastapi import APIRouter, Depends, WebSocket
from fastapi.websockets import WebSocketDisconnect
from thespian.actors import ActorExitRequest

from miloco_server import actor_system
from miloco_server.service.chat_agent_dispatcher import ChatAgentDispatcher
from miloco_server.schema.chat_schema import Event
from miloco_server.schema.common_schema import NormalResponse
from miloco_server.service.manager import get_manager
from miloco_server.middleware import verify_token, verify_websocket_token

router = APIRouter(prefix="/chat", tags=["Instant Query"])

manager = get_manager()

logger = logging.getLogger(name=__name__)

@router.websocket("/ws/query")
async def ws_query(
    websocket: WebSocket,
    request_id: str,
    session_id: Optional[str] = None,
    current_user: str = Depends(verify_websocket_token)):  # pylint: disable=unused-argument
    """Chat WebSocket."""
    logger.info("[%s] WebSocket connection request", request_id)

    agent_transceiver = actor_system.createActor(
        lambda: ChatAgentDispatcher(websocket, request_id, session_id))
    try:
        await websocket.accept()
        while True:

            message = await websocket.receive_text()
            logger.info(
                "[%s] Received message from client, %s", request_id, message)
            event_data = json.loads(message)
            event = Event(**event_data)
            actor_system.tell(agent_transceiver, event)
            await asyncio.sleep(0.1)

    except WebSocketDisconnect:
        logger.warning("[%s] Client disconnected", request_id)
    except Exception as err:  # pylint: disable=broad-exception-caught
        logger.error("[%s] WebSocket error: %s", request_id, err)
        await websocket.close(code=1011, reason=f"Server error: {str(err)}")
    finally:
        logger.info("[%s] WebSocket connection closed", request_id)
        actor_system.tell(agent_transceiver, ActorExitRequest())
        logger.info(
            "[%s] ActorExitRequest sent to ChatAgentDispatcher", request_id)

@router.get("/history/{session_id}", summary="Get chat history details", response_model=NormalResponse)
async def get_chat_history(session_id: str,
                           current_user: str = Depends(verify_token)):
    logger.info("Get chat history API called, user: %s, session_id: %s", current_user, session_id)
    info = manager.chat_service.get_chat_history(session_id)
    logger.info("Chat history retrieved successfully, user: %s, session_id: %s, data: %s",
                current_user, session_id, info)
    return NormalResponse(code=0, message="Chat history retrieved successfully", data=info)


@router.get("/historys", summary="Get chat history list", response_model=NormalResponse)
async def list_chat_histories(
    current_user: str = Depends(verify_token)
):
    logger.info("Get chat history list API called, user: %s", current_user)
    result = manager.chat_service.get_all_chat_history_simple()
    logger.info("Chat history list retrieved successfully, user: %s, data: %s", current_user, result)
    return NormalResponse(code=0, message="Chat history list retrieved successfully", data=result)


@router.delete("/history/{session_id}", summary="Delete chat history", response_model=NormalResponse)
async def delete_chat_history(session_id: str,
                              current_user: str = Depends(verify_token)):
    logger.info("Delete chat history API called, user: %s, session_id: %s", current_user, session_id)
    manager.chat_service.delete_chat_history(session_id)
    return NormalResponse(code=0, message="Chat history deleted successfully", data=None)


@router.get("/history/search", summary="Search chat history", response_model=NormalResponse)
async def search_chat_histories(keyword: str,
                                current_user: str = Depends(verify_token)):
    logger.info("Search chat history API called, user: %s, keyword: %s", current_user, keyword)
    result = manager.chat_service.search_chat_histories(keyword)
    logger.info("Chat history search completed successfully, user: %s, keyword: %s, data: %s",
                current_user, keyword, result)
    return NormalResponse(code=0, message="Chat history search completed successfully", data=result)
