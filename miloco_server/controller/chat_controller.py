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
from miloco_server.config import CHAT_CONFIG

# Determine which dispatcher to use based on configuration
_use_openclaw = CHAT_CONFIG.get("use_openclaw", True)
_use_ahaa = CHAT_CONFIG.get("use_ahaa", False)

if _use_ahaa:
    # Use AHAA (Adaptive Hybrid Agent Architecture) dispatcher
    from miloco_server.agent.multi_agent.ahaa_dispatcher import AHAADispatcher
    from miloco_server.service.chat_agent_dispatcher_enhanced import ChatAgentDispatcherEnhanced as ChatAgentDispatcher
    _ahaa_dispatcher = None
    _init_ahaa = True
elif _use_openclaw:
    from miloco_server.service.chat_agent_dispatcher_enhanced import ChatAgentDispatcherEnhanced as ChatAgentDispatcher
    _init_ahaa = False
else:
    from miloco_server.service.chat_agent_dispatcher import ChatAgentDispatcher
    _init_ahaa = False

from miloco_server.schema.chat_schema import Event
from miloco_server.schema.common_schema import NormalResponse
from miloco_server.service.manager import get_manager
from miloco_server.middleware import verify_token, verify_websocket_token

router = APIRouter(prefix="/chat", tags=["Instant Query"])

manager = get_manager()

logger = logging.getLogger(name=__name__)
logger.info("ChatController initialized, use_openclaw=%s, use_ahaa=%s", _use_openclaw, _use_ahaa)

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
            logger.debug(
                "[%s] Received message from client, %s", request_id, message)
            event_data = json.loads(message)
            event = Event(**event_data)
            actor_system.tell(agent_transceiver, event)
            await asyncio.sleep(0.1)

    except WebSocketDisconnect:
        logger.warning("[%s] Client disconnected", request_id)
    except Exception as err:  # pylint: disable=broad-exception-caught
        logger.error("[%s] WebSocket error: %s", request_id, err)
        try:
            if websocket.client_state == websocket.client_state.CONNECTED:
                await websocket.close(code=1011, reason=f"Server error: {str(err)}")
        except Exception as close_err:
            logger.warning("[%s] Failed to close WebSocket: %s", request_id, close_err)
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


@router.get("/agent/status", summary="Get agent architecture status", response_model=NormalResponse)
async def get_agent_status(current_user: str = Depends(verify_token)):
    """Get current agent architecture status and configuration."""
    logger.info("Get agent status API called, user: %s", current_user)
    
    status = {
        "use_openclaw": _use_openclaw,
        "use_ahaa": _use_ahaa,
        "architecture": "AHAA" if _use_ahaa else ("OpenClaw" if _use_openclaw else "Legacy"),
        "ahaa_config": CHAT_CONFIG.get("ahaa", {}) if _use_ahaa else None,
    }
    
    return NormalResponse(code=0, message="Agent status retrieved successfully", data=status)


@router.post("/agent/ahaa/test", summary="Test AHAA with a query", response_model=NormalResponse)
async def test_ahaa_query(
    query: str,
    session_id: Optional[str] = None,
    current_user: str = Depends(verify_token)
):
    """Test AHAA architecture with a sample query (for debugging)."""
    logger.info("Test AHAA query called, user: %s, query: %s", current_user, query)
    
    if not _use_ahaa:
        return NormalResponse(
            code=1,
            message="AHAA is not enabled. Set chat.use_ahaa=true in server_config.yaml",
            data=None
        )
    
    try:
        from miloco_server.agent.multi_agent import ComplexityAnalyzer, RuleEngine
        
        analyzer = ComplexityAnalyzer()
        rule_engine = RuleEngine()
        
        # Analyze complexity
        analysis = await analyzer.analyze(query)
        
        # Try rule matching
        rule_match = await rule_engine.match(query)
        
        result = {
            "query": query,
            "analysis": {
                "complexity": analysis.complexity.name,
                "confidence": analysis.confidence,
                "suggested_mode": analysis.suggested_mode,
                "factors": analysis.factors.to_dict(),
            },
            "rule_match": {
                "matched": rule_match is not None,
                "rule_name": rule_match.rule_name if rule_match else None,
                "action": rule_match.action.name if rule_match else None,
                "response": rule_match.response_template if rule_match else None,
            } if rule_match else None,
            "summary": analyzer.get_analysis_summary(analysis),
        }
        
        return NormalResponse(code=0, message="AHAA test completed", data=result)
        
    except Exception as e:
        logger.error("AHAA test error: %s", e, exc_info=True)
        return NormalResponse(code=1, message=f"AHAA test failed: {str(e)}", data=None)
