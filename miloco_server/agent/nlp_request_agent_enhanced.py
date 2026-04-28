# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Enhanced Nlp Request Agent with OpenClaw Integration"""
import asyncio
import json
import logging
import re

from miloco_server.schema.chat_schema import Event, Internal, Nlp
from miloco_server.utils.chat_companion import ChatCachedData
from miloco_server.agent import EnhancedChatAgent, auto_select_role, select_tools

logger = logging.getLogger(__name__)


class NlpRequestAgentEnhanced(EnhancedChatAgent):
    """
    Enhanced Nlp Request Agent with OpenClaw Framework Integration
    
    Features:
    - Automatic role selection based on query
    - Intelligent tool selection
    - Context-aware responses
    - Adaptive learning
    - Comprehensive error handling
    """

    _WHO_AM_I_PATTERNS = [
        r"我是谁",
        r"看看我是谁",
        r"你认识我吗",
        r"认得出我吗",
        r"我是谁啊",
        r"who\s*am\s*i",
        r"do\s*you\s*know\s*me",
        r"recognize\s*me",
    ]

    def _parse_and_handle_event(self, event: Event) -> None:
        """Parse and handle event."""
        if event.judge_type("Nlp", "Request"):
            payload = Nlp.Request(**json.loads(event.payload))
            self._handle_nlp_request(payload)
        else:
            raise ValueError(f"Unsupported event: {event.header.namespace}.{event.header.name}")

    def _handle_nlp_request(self, payload: Nlp.Request) -> None:
        """
        Handle Nlp request with OpenClaw enhancements.
        
        Args:
            payload: Nlp request payload
        """
        query = payload.query
        query = self._route_query_with_tool_intent(query)
        
        # Send dispatcher message
        self._send_instruction(Internal.Dispatcher(current_query=query, need_storage_history=True))
        
        # OpenClaw: Auto-select role based on query
        self._auto_select_and_set_role(query)
        
        # OpenClaw: Intelligent tool selection
        self._log_tool_selections(query)
        
        # Set tools metadata
        mcp_list = payload.mcp_list
        self._set_tools_meta(mcp_list)
        
        # Set chat data
        self._chat_companion.set_chat_data(
            self._request_id,
            ChatCachedData(
                camera_ids=payload.camera_ids,
                mcp_ids=payload.mcp_list,
                xiaoai_play=bool(payload.xiaoai_play),
                xiaoai_client_ids=payload.xiaoai_client_ids,
            ))

        # Run chat with enhanced processing
        asyncio.create_task(self._run_chat(query))

    def _auto_select_and_set_role(self, query: str) -> None:
        """
        Automatically select and set role based on query.
        
        Args:
            query: User query
        """
        try:
            # Auto-select role
            selected_role = auto_select_role(query)
            
            # Check if we got a valid role
            if selected_role is None:
                logger.debug("[%s] Auto-select returned None, keeping current role", self._request_id)
                return
            
            # Check if role changed
            if (self._active_role is None or 
                selected_role.config.name != self._active_role.config.name):
                
                logger.info("[%s] Auto-selected role: %s (was: %s)", 
                           self._request_id,
                           selected_role.config.name,
                           self._active_role.config.name if self._active_role else "None")
                
                # Update active role
                self._active_role = selected_role
                
                # Update system prompt with new role
                new_system_prompt = self._build_enhanced_system_prompt()
                self._chat_history_messages.update_system_message(new_system_prompt)
                
                logger.info("[%s] Updated system prompt for role: %s",
                           self._request_id, selected_role.config.name)
        except Exception as e:
            logger.warning("[%s] Failed to auto-select role: %s", self._request_id, e)
            # Continue with current role

    def _log_tool_selections(self, query: str) -> None:
        """
        Log intelligent tool selections for monitoring.
        
        Args:
            query: User query
        """
        try:
            tool_selections = select_tools(query, top_k=5)
            if tool_selections:
                logger.info("[%s] Intelligent tool selections for '%s': %s",
                           self._request_id,
                           query[:50],
                           [f"{s.tool_name}({s.confidence:.2f})" for s in tool_selections])
        except Exception as e:
            logger.debug("[%s] Tool selection logging failed: %s", self._request_id, e)

    def _route_query_with_tool_intent(self, query: str) -> str:
        """
        Lightweight semantic routing for "who am I" requests.
        If matched, inject an execution hint so the model prioritizes `who_am_i`.
        
        Args:
            query: Original query
            
        Returns:
            Modified query with hints if matched
        """
        q = (query or "").strip()
        if not q:
            return query

        lower_q = q.lower()
        matched = any(re.search(p, lower_q) for p in self._WHO_AM_I_PATTERNS)
        if not matched:
            return query

        logger.info("[%s] Semantic route hit: force who_am_i tool first", self._request_id)
        return (
            "你必须先调用工具 who_am_i 来识别用户身份，再基于工具结果回复。\n"
            "who_am_i 最多只允许调用 1 次，禁止重复调用或重试。\n"
            "请按工具结果严格分支回复：\n"
            "1) success=true 且 recognized=true：明确说出姓名；\n"
            '2) success=true 且 recognized=false：回复"我不认识你"；\n'
            '3) success=false：不要说"我不认识你"，应直接转述工具 message（如摄像头离线/无可用摄像头/无法获取截图）。\n'
            "在完成上述分支回复后立即结束，不要再调用任何工具。\n"
            f"用户原始问题：{query}"
        )
