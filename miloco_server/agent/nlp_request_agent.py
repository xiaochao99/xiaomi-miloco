# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Chat Agent"""
import asyncio
import json
import logging
import re

from miloco_server.schema.chat_schema import Event, Internal, Nlp
from miloco_server.utils.chat_companion import ChatCachedData
from miloco_server.agent.chat_agent import ChatAgent

logger = logging.getLogger(__name__)

class NlpRequestAgent(ChatAgent):
    """Nlp Request Agent"""

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
        """Handle Nlp request."""
        query = payload.query
        query = self._route_query_with_tool_intent(query)
        self._send_instruction(Internal.Dispatcher(current_query=query, need_storage_history=True))
        mcp_list = payload.mcp_list
        self._set_tools_meta(mcp_list)

        self._chat_companion.set_chat_data(
            self._request_id,
            ChatCachedData(
                camera_ids=payload.camera_ids,
                mcp_ids=payload.mcp_list,
                xiaoai_play=bool(payload.xiaoai_play),
                xiaoai_client_ids=payload.xiaoai_client_ids,
            ))

        asyncio.create_task(self._run_chat(query))

    def _route_query_with_tool_intent(self, query: str) -> str:
        """
        Lightweight semantic routing for "who am I" requests.
        If matched, inject an execution hint so the model prioritizes `who_am_i`.
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
            "2) success=true 且 recognized=false：回复“我不认识你”；\n"
            "3) success=false：不要说“我不认识你”，应直接转述工具 message（如摄像头离线/无可用摄像头/无法获取截图）。\n"
            "在完成上述分支回复后立即结束，不要再调用任何工具。\n"
            f"用户原始问题：{query}"
        )

