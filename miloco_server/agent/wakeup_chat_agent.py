# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""WakeUp Chat Agent with AHAA Architecture"""
import json
import logging
import asyncio
from typing import Optional, Dict, Any

from thespian.actors import ActorAddress
from openai.types.chat.chat_completion_message_tool_call import ChatCompletionMessageToolCall
from miloco_server.schema.chat_history_schema import ChatHistoryMessages
from miloco_server.schema.chat_schema import Dialog, Event, Nlp
from miloco_server.schema.mcp_schema import LocalMcpClientId
from miloco_server.agent.enhanced_chat_agent import EnhancedChatAgent
from miloco_server.config import CHAT_CONFIG

logger = logging.getLogger(__name__)


class WakeUpChatAgent(EnhancedChatAgent):
    """
    WakeUp Chat Agent with AHAA Architecture
    
    Handles voice wakeup interactions with AHAA-based processing.
    """
    
    def __init__(
        self,
        request_id: str,
        out_actor_address: ActorAddress,
        chat_history_messages: Optional[ChatHistoryMessages] = None,
    ):
        super().__init__(request_id, out_actor_address, chat_history_messages)
        self._actions: list = []

    def _parse_and_handle_event(self, event: Event) -> None:
        """Parse and handle event."""
        if event.judge_type("Nlp", "Request"):
            payload = Nlp.Request(**json.loads(event.payload))
            self._handle_wakeup_request(payload)
        else:
            raise ValueError(f"Unsupported event: {event.header.namespace}.{event.header.name}")

    def _handle_wakeup_request(self, payload: Nlp.Request) -> None:
        """Handle wakeup NLP request."""
        query = payload.query
        logger.info("[%s] Wakeup request: %s", self._request_id, query)
        
        self._set_tools_meta(payload.mcp_list)
        asyncio.create_task(self._run_chat(query))

    async def _run_chat(self, query: str) -> None:
        """Run enhanced chat for wakeup request."""
        try:
            await super()._run_chat(query)
        except Exception as e:
            logger.error("[%s] Wakeup chat failed: %s", self._request_id, e)
            self._send_instruction(Dialog.Exception(message=str(e)))
            self._send_dialog_finish(False)
