# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
OpenAI compatibility layer for Miloco.

Expose a subset of OpenAI API endpoints so that external clients can call Miloco AI Chat
using standard OpenAI-compatible protocols.

Supported:
- GET  /v1/models
- POST /v1/chat/completions  (stream and non-stream)

Auth:
- Reuse Miloco `verify_token`, supports JWT cookie and `Authorization: Bearer <token>`
  where token can be JWT or API Token (apt_...).
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any, AsyncGenerator, List, Literal, Optional, Union

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ConfigDict

from miloco_server.middleware import verify_token
from miloco_server.controller.ai_chat_controller import APIChatAdapter, parse_ai_response


router = APIRouter(prefix="/v1", tags=["OpenAI Compatible API"])

MILOCO_OPENAI_MODEL_ID = "miloco-ai-chat"
MILOCO_OPENAI_MODEL_ALIASES = {"miloco", "miloco-chat", "miloco-ai-chat"}


class OpenAIChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"] = Field(...)
    content: Optional[Union[str, List[Any]]] = Field(default=None)


class OpenAIChatCompletionRequest(BaseModel):
    """
    Minimal OpenAI-compatible chat completion request.

    Notes:
    - We accept extra fields for compatibility (e.g. `session_id`, `camera_ids`, `mcp_list`)
    - If `session_id` is provided, it will be forwarded to Miloco AI Chat for multi-turn.
    """

    model_config = ConfigDict(extra="allow")

    model: Optional[str] = Field(default=MILOCO_OPENAI_MODEL_ID)
    messages: List[OpenAIChatMessage] = Field(default_factory=list)
    stream: bool = Field(default=False)

    # Non-standard extensions (optional)
    session_id: Optional[str] = Field(default=None, description="Miloco AI Chat session_id")
    camera_ids: Optional[List[str]] = Field(default=None, description="Camera DID list")
    mcp_list: Optional[List[str]] = Field(default=None, description="MCP service id list")


def _canonicalize_model(model: Optional[str]) -> str:
    if not model:
        return MILOCO_OPENAI_MODEL_ID
    if model in MILOCO_OPENAI_MODEL_ALIASES:
        return MILOCO_OPENAI_MODEL_ID
    # For now, only Miloco AI Chat is supported by this compat layer.
    return MILOCO_OPENAI_MODEL_ID


def _extract_text_from_content(content: Optional[Union[str, List[Any]]]) -> str:
    """
    OpenAI messages.content can be a string or a list of content parts.
    We support:
    - string
    - list of {"type":"text","text": "..."} parts (join)
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts: List[str] = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                texts.append(str(part.get("text", "")))
            elif isinstance(part, str):
                texts.append(part)
        return "".join(texts)
    return str(content)


def _build_query_from_messages(messages: List[OpenAIChatMessage], session_id: Optional[str]) -> str:
    """
    Build a single query string for Miloco AI Chat.

    - If session_id is provided: use the latest user message content as query.
    - Otherwise: include a short history prefix (best-effort) and the latest user message.
    """
    # Find the last user message
    last_user = ""
    for m in reversed(messages or []):
        if m.role == "user":
            last_user = _extract_text_from_content(m.content).strip()
            if last_user:
                break

    if session_id:
        return last_user or ""

    # No session_id: embed brief history for better continuity
    history_lines: List[str] = []
    for m in messages[:-1]:
        if m.role in ("user", "assistant", "system"):
            txt = _extract_text_from_content(m.content).strip()
            if not txt:
                continue
            prefix = "User" if m.role == "user" else ("Assistant" if m.role == "assistant" else "System")
            history_lines.append(f"{prefix}: {txt}")

    history = "\n".join(history_lines)
    if history:
        # Keep it bounded
        history = history[-2000:]
        return f"对话历史（供参考）：\n{history}\n\n当前问题：{last_user}"

    return last_user


@router.get("/models")
async def list_models(current_user: str = Depends(verify_token)):  # pylint: disable=unused-argument
    created = int(time.time())
    return {
        "object": "list",
        "data": [
            {
                "id": MILOCO_OPENAI_MODEL_ID,
                "object": "model",
                "created": created,
                "owned_by": "miloco",
            }
        ],
    }


def _sse_data(data: Any) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _stream_chat_completions(req: OpenAIChatCompletionRequest) -> AsyncGenerator[str, None]:
    """
    Stream response in OpenAI SSE format.
    """
    created = int(time.time())
    model_id = _canonicalize_model(req.model)
    completion_id = f"chatcmpl-{uuid.uuid4().hex}"

    # Initial chunk with role
    yield _sse_data({
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model_id,
        "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
    })

    adapter = APIChatAdapter(
        request_id=f"oai_{uuid.uuid4().hex[:12]}",
        session_id=req.session_id,
    )

    query = _build_query_from_messages(req.messages, req.session_id)

    async for event in adapter.process_query(
        query=query,
        camera_ids=req.camera_ids,
        mcp_list=req.mcp_list,
    ):
        if event.get("type") != "message":
            continue
        data = event.get("data") or {}
        header = data.get("header") or {}
        payload_str = data.get("payload", "{}")
        try:
            payload = json.loads(payload_str) if isinstance(payload_str, str) else payload_str
        except Exception:
            payload = {}

        if header.get("namespace") == "Template" and header.get("name") == "ToastStream":
            chunk_text = str(payload.get("stream", ""))
            if not chunk_text:
                continue
            yield _sse_data({
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model_id,
                "choices": [{"index": 0, "delta": {"content": chunk_text}, "finish_reason": None}],
            })

    # Final chunk
    yield _sse_data({
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model_id,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    })
    yield "data: [DONE]\n\n"


@router.post("/chat/completions")
async def chat_completions(
    req: OpenAIChatCompletionRequest,
    request: Request,
    current_user: str = Depends(verify_token),  # pylint: disable=unused-argument
):
    """
    OpenAI compatible `chat.completions.create`.

    Supported extensions:
    - `session_id`: Use Miloco multi-turn memory.
    - `camera_ids`, `mcp_list`: Forwarded to Miloco AI Chat.
    """
    model_id = _canonicalize_model(req.model)

    if req.stream:
        return StreamingResponse(
            _stream_chat_completions(req),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # Non-streaming mode: collect full response
    adapter = APIChatAdapter(
        request_id=f"oai_{uuid.uuid4().hex[:12]}",
        session_id=req.session_id,
    )

    query = _build_query_from_messages(req.messages, req.session_id)
    full_response = ""

    async for event in adapter.process_query(
        query=query,
        camera_ids=req.camera_ids,
        mcp_list=req.mcp_list,
    ):
        if event.get("type") != "message":
            continue
        data = event.get("data") or {}
        header = data.get("header") or {}
        payload_str = data.get("payload", "{}")
        try:
            payload = json.loads(payload_str) if isinstance(payload_str, str) else payload_str
        except Exception:
            payload = {}

        if header.get("namespace") == "Template" and header.get("name") == "ToastStream":
            full_response += str(payload.get("stream", ""))

    parsed = parse_ai_response(full_response)
    assistant_content = parsed.get("final_answer") or full_response

    created = int(time.time())
    completion_id = f"chatcmpl-{uuid.uuid4().hex}"
    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": created,
        "model": model_id,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": assistant_content},
                "finish_reason": "stop",
            }
        ],
    }

