from __future__ import annotations

"""
AI Chat core adapter (controller-independent).

This module hosts the reusable AI-CHAT logic that bridges:
- OpenAI-compatible controllers (/v1/...)
- Miloco actor-based chat pipeline (NlpRequestAgent, Template/Dialog messages)

It intentionally contains no FastAPI router code so that API layers can be added/removed
without affecting core behavior (including default auto camera selection and MCP selection).
"""

import asyncio
import json
import logging
import time
import uuid
from typing import AsyncGenerator, List, Optional

from thespian.actors import Actor, ActorExitRequest

from miloco_server import actor_system
from miloco_server.agent.nlp_request_agent import NlpRequestAgent
from miloco_server.schema.chat_schema import Dialog, Event, Header, Instruction, Nlp, Template
from miloco_server.schema.chat_history_schema import (
    ChatHistoryMessages,
    ChatHistorySession,
    ChatHistoryStorage,
)
from miloco_server.service.manager import get_manager
from miloco_server.service.xiaoai_broadcast_service import broadcast_chat_reply

logger = logging.getLogger(__name__)


def parse_ai_response(response_text: str) -> dict:
    """
    Parse AI response text and extract structured fields.

    Rules:
    - <reflect>...</reflect> => thinking
    - <final_answer>...</final_answer> => final_answer
    """
    from miloco_server.utils.structured_tags import extract_reflect_blocks, extract_final_answer

    if not response_text:
        return {"thinking": None, "final_answer": None, "has_structured_format": False}

    result = {"thinking": None, "final_answer": None, "has_structured_format": False}

    reflect_matches = extract_reflect_blocks(response_text)
    if reflect_matches:
        result["thinking"] = "\n\n".join(match.strip() for match in reflect_matches if match.strip())
        result["has_structured_format"] = True

    final_answer = extract_final_answer(response_text)
    if final_answer:
        result["final_answer"] = final_answer
        result["has_structured_format"] = True

    return result


class APIMessageCollector:
    """Global per-request message queues for streaming."""

    _collectors: dict[str, asyncio.Queue] = {}

    @classmethod
    def create_collector(cls, request_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        cls._collectors[request_id] = queue
        return queue

    @classmethod
    def remove_collector(cls, request_id: str):
        cls._collectors.pop(request_id, None)

    @classmethod
    async def send_message(cls, request_id: str, message: dict):
        queue = cls._collectors.get(request_id)
        if queue:
            await queue.put(message)


class APIOutActor(Actor):
    """
    Output Actor that receives ChatAgent/NlpRequestAgent messages and forwards them
    into the API message collector.
    """

    def __init__(self, request_id: str, session_id: str | None = None):
        super().__init__()
        self.request_id = request_id
        self.session_id = session_id
        self.message_count = 0

    def receiveMessage(self, msg, sender):  # noqa: N802  (thespian naming)
        try:
            if isinstance(
                msg,
                (
                    Template.ToastStream,
                    Dialog.Finish,
                    Dialog.Exception,
                    Template.CallTool,
                    Template.CallToolResult,
                ),
            ):
                self.message_count += 1
                namespace, name = self._get_message_type(msg)

                header = {
                    "type": "instruction",
                    "namespace": namespace,
                    "name": name,
                    "timestamp": int(time.time() * 1000),
                    "request_id": self.request_id,
                    "session_id": self.session_id,
                }

                payload = self._extract_payload(msg)
                message_dict = {"header": header, "payload": json.dumps(payload, ensure_ascii=False)}

                asyncio.create_task(APIMessageCollector.send_message(self.request_id, message_dict))

                if isinstance(msg, Dialog.Finish):
                    asyncio.create_task(APIMessageCollector.send_message(self.request_id, {"__finish__": True}))

            elif isinstance(msg, ActorExitRequest):
                logger.info("[%s] APIOutActor received exit request", self.request_id)

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("[%s] APIOutActor error: %s", self.request_id, e, exc_info=True)

    def _get_message_type(self, msg) -> tuple[str, str]:
        if isinstance(msg, Template.ToastStream):
            return ("Template", "ToastStream")
        if isinstance(msg, Dialog.Finish):
            return ("Dialog", "Finish")
        if isinstance(msg, Dialog.Exception):
            return ("Dialog", "Exception")
        if isinstance(msg, Template.CallTool):
            return ("Template", "CallTool")
        if isinstance(msg, Template.CallToolResult):
            return ("Template", "CallToolResult")
        return ("Unknown", "Unknown")

    def _extract_payload(self, msg) -> dict:
        try:
            if isinstance(msg, Template.ToastStream):
                return {"stream": msg.stream}
            if isinstance(msg, Dialog.Finish):
                return {"success": msg.success}
            if isinstance(msg, Dialog.Exception):
                return {"message": msg.message}
            if isinstance(msg, Template.CallTool):
                return {
                    "id": msg.id,
                    "service_name": msg.service_name,
                    "tool_name": msg.tool_name,
                    "tool_params": msg.tool_params,
                }
            if isinstance(msg, Template.CallToolResult):
                return {
                    "id": msg.id,
                    "success": msg.success,
                    "tool_response": msg.tool_response,
                    "error_message": msg.error_message,
                }
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning("[%s] Extract payload failed: %s", self.request_id, e)
        return {}


class APIChatAdapter:
    """
    Reuse Miloco chat pipeline and expose a stream of internal instruction messages.

    Defaults:
    - camera_ids is None => auto select all online cameras
    - mcp_list is None => use all MCP services
    """

    def __init__(self, request_id: str, session_id: Optional[str] = None):
        self.request_id = request_id
        self.session_id = session_id or str(uuid.uuid4())
        self.message_queue: asyncio.Queue = APIMessageCollector.create_collector(request_id)

        self._chat_agent = None
        self._out_actor = None
        self._manager = get_manager()
        self._chat_companion = self._manager.chat_companion

        chat_history_storage = self._chat_companion.get_chat_history(self.session_id)
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
        self._need_storage_history = False
        self._full_response = ""
        self._success = True

        logger.info("[%s] APIChatAdapter initialized, session_id=%s", request_id, self.session_id)

    async def _get_auto_selected_cameras(self) -> List[str]:
        try:
            all_cameras = await self._manager.miot_proxy.get_cameras()
            if not all_cameras:
                return []

            online_cameras: List[str] = []
            for did, camera_info in all_cameras.items():
                is_online = getattr(camera_info, "online", False)
                camera_status = getattr(camera_info, "camera_status", None)
                status_online = camera_status in ["1", 1, "CONNECTED", "ONLINE"]
                if is_online or status_online:
                    online_cameras.append(did)
            return online_cameras
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("[%s] Get cameras failed: %s", self.request_id, e)
            return []

    async def _get_all_mcp_services(self) -> List[str]:
        try:
            mcp_service = self._manager.mcp_service
            client_ids: List[str] = []

            if hasattr(mcp_service, "clients") and isinstance(mcp_service.clients, dict):
                client_ids = list(mcp_service.clients.keys())

            if not client_ids and hasattr(self._manager, "tool_executor"):
                tool_executor = self._manager.tool_executor
                if hasattr(tool_executor, "mcp_client_manager") and tool_executor.mcp_client_manager:
                    mcp_manager = tool_executor.mcp_client_manager
                    if hasattr(mcp_manager, "clients") and isinstance(mcp_manager.clients, dict):
                        client_ids = list(mcp_manager.clients.keys())

            return client_ids or ["local_default"]
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("[%s] Get MCP services failed: %s", self.request_id, e)
            return ["local_default"]

    async def process_query(
        self,
        query: str,
        camera_ids: Optional[List[str]] = None,
        mcp_list: Optional[List[str]] = None,
    ) -> AsyncGenerator[dict, None]:
        start_time = time.time()
        try:
            if self._chat_history_storage.title == "":
                self._chat_history_storage.title = (query or "")[:50]

            # Performance optimization:
            # Auto camera selection can be expensive (vision analysis). Only auto-enable when query
            # likely needs camera context. Users can still force-enable by explicitly passing camera_ids.
            if camera_ids is None:
                q = (query or "").lower()
                need_camera = bool(
                    re.search(r"(摄像头|监控|画面|摄像|camera|cam|视频|画面里|看一下|看看|看下)", q)
                )
                camera_ids = await self._get_auto_selected_cameras() if need_camera else []
            if mcp_list is None:
                mcp_list = await self._get_all_mcp_services()

            self._out_actor = actor_system.createActor(lambda: APIOutActor(self.request_id, self.session_id))
            self._chat_agent = actor_system.createActor(
                lambda: NlpRequestAgent(self.request_id, self._out_actor, self._chat_history_messages)
            )

            nlp_request = Nlp.Request(query=query, camera_ids=camera_ids or [], mcp_list=mcp_list or [])
            event = Event.build_event(nlp_request, self.request_id, self.session_id)
            self._chat_history_storage.session.add_event(event)
            actor_system.tell(self._chat_agent, event)

            finished = False
            timeout_count = 0
            max_timeout = 600  # 600 * 0.5s = 300s
            finish_message_received = False

            while not finished and timeout_count < max_timeout:
                try:
                    message = await asyncio.wait_for(self.message_queue.get(), timeout=0.5)
                    timeout_count = 0

                    if isinstance(message, dict) and message.get("__finish__"):
                        finish_message_received = True
                        finished = True
                        continue

                    await self._process_message(message)
                    yield {"type": "message", "data": message}

                    if self._is_finish_message(message):
                        finish_message_received = True
                        try:
                            while True:
                                extra_msg = await asyncio.wait_for(self.message_queue.get(), timeout=0.3)
                                if isinstance(extra_msg, dict) and extra_msg.get("__finish__"):
                                    break
                                await self._process_message(extra_msg)
                                yield {"type": "message", "data": extra_msg}
                        except asyncio.TimeoutError:
                            pass
                        finished = True

                except asyncio.TimeoutError:
                    timeout_count += 1
                    if finish_message_received and timeout_count < 10:
                        continue
                    if timeout_count > 120 and not self._full_response and not finish_message_received:
                        finished = True
                        self._success = False

            if self._success and self._full_response:
                await broadcast_chat_reply(self._full_response)

            yield {
                "type": "complete",
                "data": {
                    "request_id": self.request_id,
                    "session_id": self.session_id,
                    "response": self._full_response,
                    "processing_time": time.time() - start_time,
                    "success": self._success,
                },
            }

            if self._need_storage_history:
                self._chat_history_storage.messages = self._chat_history_messages.to_json()
                self._chat_companion.store_chat_history(self._chat_history_storage)

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("[%s] Process query failed: %s", self.request_id, e, exc_info=True)
            yield {"type": "error", "data": {"error": str(e), "request_id": self.request_id}}
        finally:
            await self._cleanup()

    async def _process_message(self, message: dict):
        try:
            header = message.get("header", {})
            payload_str = message.get("payload", "{}")
            payload = json.loads(payload_str) if isinstance(payload_str, str) else payload_str

            if header.get("namespace") == "Template" and header.get("name") == "ToastStream":
                self._full_response += str(payload.get("stream", ""))
            elif header.get("namespace") == "Dialog" and header.get("name") == "Finish":
                self._success = payload.get("success", True)
                if header.get("session_id"):
                    self.session_id = header.get("session_id")
                self._need_storage_history = True

            instruction = Instruction(
                header=Header(
                    type=header.get("type", "instruction"),
                    namespace=header.get("namespace", ""),
                    name=header.get("name", ""),
                    timestamp=header.get("timestamp", int(time.time() * 1000)),
                    request_id=header.get("request_id", self.request_id),
                    session_id=header.get("session_id", self.session_id),
                ),
                payload=payload_str,
            )
            self._chat_history_storage.session.add_instruction(instruction)

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning("[%s] Parse message failed: %s", self.request_id, e)

    def _is_finish_message(self, message: dict) -> bool:
        try:
            header = message.get("header", {})
            return header.get("namespace") == "Dialog" and header.get("name") == "Finish"
        except Exception:
            return False

    async def _cleanup(self):
        try:
            if self._chat_agent:
                try:
                    actor_system.tell(self._chat_agent, ActorExitRequest())
                except Exception as e:  # pylint: disable=broad-exception-caught
                    logger.warning("[%s] Close ChatAgent failed: %s", self.request_id, e)

            if self._out_actor:
                try:
                    actor_system.tell(self._out_actor, ActorExitRequest())
                except Exception as e:  # pylint: disable=broad-exception-caught
                    logger.warning("[%s] Close APIOutActor failed: %s", self.request_id, e)

            APIMessageCollector.remove_collector(self.request_id)
            self._chat_companion.clear_chat_data(self.request_id)

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning("[%s] Cleanup failed: %s", self.request_id, e)

