# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Chat Agent Dispatcher with AHAA Architecture
Implements AHAA (Adaptive Hybrid Agent Architecture) dispatch logic
"""

import json
import logging
import time
from typing import Optional
import uuid
import asyncio

from fastapi import WebSocket
from thespian.actors import Actor, ActorAddress, ActorExitRequest

from miloco_server import actor_system
from miloco_server.config import CHAT_CONFIG
from miloco_server.schema.chat_schema import Event, Instruction, InstructionPayload, Internal, Template, Dialog
from miloco_server.schema.chat_history_schema import (
    ChatHistoryStorage, ChatHistoryMessages, ChatHistorySession
)
from miloco_server.service.xiaoai_broadcast_service import broadcast_chat_reply, broadcast_via_bridge

logger = logging.getLogger(__name__)

# AHAA is always enabled by default
_ahaa_dispatcher = None

try:
    from miloco_server.agent.multi_agent.ahaa_dispatcher import AHAADispatcher as _AHAADispatcher
    _ahaa_dispatcher = _AHAADispatcher()
    logger.info("AHAADispatcher initialized successfully")
except Exception as e:
    logger.warning("Failed to initialize AHAADispatcher: %s", e)
    _ahaa_dispatcher = None


class ChatAgentDispatcher(Actor):
    """
    Chat Agent Dispatcher with AHAA Agent Framework Support
    
    Features:
    - AHAA (Adaptive Hybrid Agent Architecture) integration
    - Automatic role management
    - Intelligent tool selection
    - Enhanced error handling
    """

    def __init__(self,
                 web_socket: WebSocket,
                 request_id: str,
                 session_id: Optional[str] = None):
        super().__init__()

        self.web_socket = web_socket
        self.request_id = request_id
        if session_id is None:
            self.session_id = str(uuid.uuid4())
        else:
            self.session_id = session_id

        self._chat_agent: Optional[ActorAddress] = None
        self._next_event_handler: Optional[ActorAddress] = None
        from miloco_server.service.manager import get_manager  # pylint: disable=import-outside-toplevel
        self._manager = get_manager()
        self._chat_companion = self._manager.chat_companion
        
        # AHAA is always enabled
        logger.info("[%s] ChatAgentDispatcher initialized with AHAA", self.request_id)
        
        chat_history_storage = self._chat_companion.get_chat_history(
            self.session_id)
        if chat_history_storage is not None:
            self._chat_history_storage = chat_history_storage
        else:
            self._chat_history_storage = ChatHistoryStorage(
                session_id=self.session_id,
                title="",
                timestamp=int(time.time() * 1000),
                session=ChatHistorySession(),
                messages=None,
            )
        self._chat_history_messages = ChatHistoryMessages.from_json(self._chat_history_storage.messages)
        logger.debug(
            "[%s] Chat history: %s", self.request_id, self._chat_history_storage
        )
        self._need_storage_history = False
        self._full_response = ""

    def receiveMessage(self, msg, sender):
        """
        Actor message receiving method
        """
        try:
            if isinstance(msg, Event):
                self._handle_event(msg)
            elif isinstance(msg, InstructionPayload):
                self._handle_instruction_payload(msg)
            elif isinstance(msg, ActorExitRequest):
                logger.info("[%s] ActorExitRequest received", self.request_id)
                self._handle_exit_request()
            else:
                logger.warning(
                    "[%s] Invalid message format: %s", self.request_id, msg)
        except Exception as e:  # pylint: disable=broad-except
            logger.error(
                "[%s] Error in receiveMessage: %s", self.request_id, e)
            self._close_web_socket()

    def _handle_event(self, event: Event) -> None:
        """
        Handle Event object with AHAA Agent support
        """
        logger.info("[%s] handle_event: %s.%s", self.request_id,
            event.header.namespace, event.header.name
        )
        if event.header.type != "event":
            raise ValueError(f"Invalid event type: {event.header.type}")

        self._chat_history_storage.session.add_event(event)

        if self._next_event_handler is not None:
            self.send(self._next_event_handler, event)
            self._next_event_handler = None
            return

        if event.judge_type("Nlp", "Request"):
            self._handle_nlp_request_event(event)
        elif event.judge_type("Nlp", "ActionDescriptionDynamicExecute"):
            self._handle_dynamic_execute_event(event)
        else:
            logger.warning(
                "[%s] Unsupported event: %s.%s", self.request_id,
                event.header.namespace, event.header.name
            )

    def _handle_nlp_request_event(self, event: Event) -> None:
        """
        Handle Nlp Request event with AHAA dispatch
        """
        self._full_response = ""
        
        # Use AHAA dispatcher if available
        if _ahaa_dispatcher is not None:
            query = self._extract_query_from_event(event)
            logger.info("[%s] AHAA dispatch for query: %s", self.request_id, query)
            self._handle_ahaa_dispatch(event, query)
            return
        
        # Fallback to AHAA Agent (NlpRequestAgent)
        from miloco_server.agent.nlp_request_agent_enhanced import NlpRequestAgent
        
        self._chat_agent = actor_system.createActor(
            lambda: NlpRequestAgent(
                self.request_id, self.myAddress, self._chat_history_messages,
            ))

        logger.info("[%s] Sending event to AHAA Agent", self.request_id)
        actor_system.tell(self._chat_agent, event)

    async def _ahaa_dispatch_async(self, event: Event, query: str) -> None:
        """
        AHAA dispatch async task: analyze complexity, try rule engine, fallback to AHAA Agent.
        """
        try:
            dispatcher = _ahaa_dispatcher
            rule_engine = dispatcher.rule_engine
            
            match_result = await rule_engine.match(query)
            if match_result is not None:
                logger.info("[%s] AHAA rule matched: %s, action=%s, confidence=%.2f",
                           self.request_id, match_result.rule_name, match_result.action.name,
                           match_result.confidence)
                
                action_name = match_result.action.name
                
                if action_name in ("CHAT",):
                    from miloco_server.service.context_provider import ContextProvider
                    provider = ContextProvider.get_instance()
                    ctx = provider.get_context() if provider else None
                    
                    tpl = match_result.response_template or "你好！有什么我可以帮您的吗？"
                    template_values = {
                        "query": query,
                        "temperature": getattr(ctx, "temperature", None),
                        "humidity": getattr(ctx, "humidity", None),
                        "weather": getattr(ctx, "weather", None),
                    }
                    template_values.update(match_result.extracted_entities)
                    
                    try:
                        response_text = tpl.format(**template_values)
                    except KeyError:
                        response_text = tpl
                    
                    logger.info("[%s] AHAA rule CHAT direct response: %s", self.request_id, response_text)
                    self._full_response = response_text
                    asyncio.create_task(broadcast_chat_reply(response_text))
                    
                    instruction = Instruction.build_instruction(
                        Template.ToastStream(stream=response_text), self.request_id, self.session_id)
                    instruction_finish = Instruction.build_instruction(
                        Dialog.Finish(success=True), self.request_id, self.session_id)
                    await self._send_instruction(instruction)
                    await self._send_instruction(instruction_finish)
                    
                    self._update_chat_history_info_title(query)
                    return
                
                if action_name in ("DEVICE_CONTROL", "DEVICE_QUERY"):
                    logger.info("[%s] AHAA rule matched %s, need tool execution, falling back to AHAA Agent",
                               self.request_id, action_name)
            
            logger.info("[%s] AHAA no rule match, falling back to AHAA Agent", self.request_id)
            self._fallback_to_ahaa_agent(event)
            
        except Exception as e:
            logger.error("[%s] AHAA dispatch error: %s, falling back", self.request_id, e, exc_info=True)
            self._fallback_to_ahaa_agent(event)

    def _extract_query_from_event(self, event: Event) -> str:
        """Extract query text from Nlp.Request event payload (JSON string)."""
        try:
            from miloco_server.schema.chat_schema import Nlp
            payload_data = json.loads(event.payload) if isinstance(event.payload, str) else event.payload
            return payload_data.get("query", "")
        except Exception:
            return ""

    def _handle_ahaa_dispatch(self, event: Event, query: str) -> None:
        """
        Start AHAA dispatch asynchronously.
        Rule-matched queries respond directly, others fallback to AHAA Agent.
        """
        asyncio.create_task(self._ahaa_dispatch_async(event, query))

    def _fallback_to_ahaa_agent(self, event: Event) -> None:
        """
        Fallback to AHAA Agent (NlpRequestAgent) when AHAA rule doesn't match.
        """
        from miloco_server.agent.nlp_request_agent_enhanced import NlpRequestAgent
        
        self._chat_agent = actor_system.createActor(
            lambda: NlpRequestAgent(
                self.request_id, self.myAddress, self._chat_history_messages,
            ))

        logger.info("[%s] Sending event to AHAA Agent (AHAA fallback)", self.request_id)
        actor_system.tell(self._chat_agent, event)

    def _handle_dynamic_execute_event(self, event: Event) -> None:
        """
        Handle Action Description Dynamic Execute event
        """
        logger.info("[%s] Creating dynamic execute agent", self.request_id)
        
        self._full_response = ""
        
        from miloco_server.agent.dynamic_execute_agent import ActionDescriptionDynamicExecuteAgent
        
        self._chat_agent = actor_system.createActor(
            lambda: ActionDescriptionDynamicExecuteAgent(
                self.request_id, self.myAddress, self._chat_history_messages,
            ))

        logger.info("[%s] Sending event to dynamic execute agent", self.request_id)
        actor_system.tell(self._chat_agent, event)

    def _update_chat_history_info_title(self, query: str):
        if self._chat_history_storage.title == "":
            self._chat_history_storage.title = query

    def _handle_instruction_payload(self, instruction_payload: InstructionPayload) -> None:
        """
        Handle Instruction object
        """
        if isinstance(instruction_payload, Internal.Dispatcher):
            self._handle_internal_dispatcher(instruction_payload)
            return
        if isinstance(instruction_payload, Template.ToastStream):
            self._full_response += instruction_payload.stream
        elif isinstance(instruction_payload, Dialog.Finish):
            if instruction_payload.success and self._full_response:
                # Per-request override: allow UI to request XiaoAI playback even if env toggle is off.
                try:
                    chat_data = self._chat_companion.get_chat_data(self.request_id)
                    if chat_data and chat_data.xiaoai_play:
                        from miloco_server.utils.structured_tags import extract_final_answer

                        speak_text = (extract_final_answer(self._full_response) or self._full_response).strip()
                        if speak_text:
                            device_ids = chat_data.xiaoai_client_ids
                            # None / [] => broadcast to all connected devices
                            asyncio.create_task(
                                broadcast_via_bridge(speak_text, client_ids=(device_ids or None))
                            )
                    else:
                        asyncio.create_task(broadcast_chat_reply(self._full_response))
                except Exception:
                    asyncio.create_task(broadcast_chat_reply(self._full_response))

        instruction = Instruction.build_instruction(instruction_payload, self.request_id, self.session_id)

        self._chat_history_storage.session.add_instruction(instruction)
        asyncio.create_task(self._send_instruction(instruction))

    def _handle_internal_dispatcher(self, dispatcher_message: Internal.Dispatcher) -> None:
        """
        Handle Internal Dispatcher message
        """
        logger.info("[%s] handle_internal_dispatcher: %s", self.request_id, dispatcher_message)
        self._next_event_handler = dispatcher_message.next_event_handler
        if dispatcher_message.current_query is not None and self._chat_history_storage.title == "":
            self._chat_history_storage.title = dispatcher_message.current_query
        if dispatcher_message.need_storage_history is not None:
            self._need_storage_history = dispatcher_message.need_storage_history

    async def _send_instruction(self, instruction: Instruction):
        """
        Send instruction
        """
        msg = instruction.model_dump_json()
        if instruction.judge_type("Template", "ToastStream"):
            logger.debug("[%s] send_instruction: %s", self.request_id, msg)
        else:
            logger.info("[%s] send_instruction: %s", self.request_id, msg)
        await self._send_message(msg)
        if instruction.judge_type("Dialog", "Finish"):
            logger.info(
                "[%s] Dialog.Finish received, requesting Actor exit", self.request_id
            )
            actor_system.tell(self.myAddress, ActorExitRequest())

    async def _send_message(self, message: str):
        """
        Send message
        """
        if self.web_socket is None:
            return

        try:
            await self.web_socket.send_text(message)
        except Exception:  # pylint: disable=broad-except
            pass

    def _handle_exit_request(self):
        """Handle Actor exit request"""
        self._close_web_socket()
        logger.info("[%s] handle_exit_request, need_storage_history: %s", 
                   self.request_id, self._need_storage_history)
        if self._need_storage_history:
            self._chat_history_storage.messages = self._chat_history_messages.to_json()
            self._chat_companion.store_chat_history(self._chat_history_storage)
        self._chat_companion.clear_chat_data(self.request_id)

        logger.info("[%s] Exit request handled successfully", self.request_id)

    def _close_web_socket(self):
        if self.web_socket is None:
            return

        try:
            if (hasattr(self.web_socket, "client_state")
                    and self.web_socket.client_state.value == 3):
                logger.info("[%s] WebSocket already closed", self.request_id)
                self.web_socket = None
                return

            asyncio.create_task(self.web_socket.close())
        except Exception as e:  # pylint: disable=broad-except
            logger.error("[%s] Error closing WebSocket: %s", self.request_id, e)
        finally:
            self.web_socket = None
