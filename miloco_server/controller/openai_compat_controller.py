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
from typing import Any, AsyncGenerator, Optional
import re

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from miloco_server.middleware import verify_token
from miloco_server.service.ai_chat_adapter import APIChatAdapter, parse_ai_response
from miloco_server.schema.openai_compat_schema import (
    OpenAIChatCompletionRequest,
    build_query_from_messages,
)


router = APIRouter(prefix="/v1", tags=["OpenAI Compatible API"])

MILOCO_OPENAI_MODEL_ID = "miloco-ai-chat"
MILOCO_OPENAI_MODEL_ALIASES = {"miloco", "miloco-chat", "miloco-ai-chat"}


def _canonicalize_model(model: Optional[str]) -> str:
    if not model:
        return MILOCO_OPENAI_MODEL_ID
    if model in MILOCO_OPENAI_MODEL_ALIASES:
        return MILOCO_OPENAI_MODEL_ID
    # For now, only Miloco AI Chat is supported by this compat layer.
    return MILOCO_OPENAI_MODEL_ID


def _estimate_tokens(text: str) -> int:
    """
    Best-effort token estimate without introducing tokenizer dependency.
    Many clients only require integers here; accuracy is not critical.
    """
    if not text:
        return 0
    return max(1, len(text) // 4)


def _tool_call_delta(payload: dict) -> dict:
    """
    Map internal Template.CallTool payload to OpenAI `tool_calls` delta.
    Payload example:
      {"id": "...", "service_name": "...", "tool_name": "...", "tool_params": {...}}
    """
    tool_id = str(payload.get("id") or f"call_{uuid.uuid4().hex[:12]}")
    tool_name = str(payload.get("tool_name") or "tool")
    tool_params = payload.get("tool_params")
    try:
        arguments = json.dumps(tool_params or {}, ensure_ascii=False)
    except Exception:
        arguments = "{}"

    return {
        "id": tool_id,
        "type": "function",
        "function": {"name": tool_name, "arguments": arguments},
    }


class _ReflectFinalStreamSplitter:
    """
    Split streamed text into:
    - reasoning: text inside <reflect>...</reflect>
    - content: text inside <final_answer>...</final_answer>

    If no tags are seen, treat all text as content.
    Tag matching is case-insensitive, supports tags spanning multiple chunks.
    """

    _OPEN_REFLECT = re.compile(r"<reflect>", re.IGNORECASE)
    _CLOSE_REFLECT = re.compile(r"</reflect>", re.IGNORECASE)
    _OPEN_FINAL = re.compile(r"<final_answer>", re.IGNORECASE)
    _CLOSE_FINAL = re.compile(r"</final_answer>", re.IGNORECASE)
    _ANY_TAG = re.compile(r"</?reflect>|</?final_answer>", re.IGNORECASE)
    _MAX_TAG_LEN = max(len("<reflect>"), len("</reflect>"), len("<final_answer>"), len("</final_answer>"))

    def __init__(self) -> None:
        self._buf = ""
        self._mode: str = "outside"  # outside | reflect | final
        self._saw_any_tag = False

    def _strip_stray_tags(self, text: str) -> str:
        if not text:
            return ""
        return self._ANY_TAG.sub("", text)

    def feed(self, chunk: str) -> list[dict[str, str]]:
        """
        Feed one chunk, return a list of deltas:
        - {"reasoning": "..."} or {"content": "..."}
        """
        if not chunk:
            return []
        self._buf += chunk
        out: list[dict[str, str]] = []

        while self._buf:
            if self._mode == "outside":
                # Find next tag (open/close). Close tags are treated as control tokens and dropped.
                m_candidates = [
                    ("open_reflect", self._OPEN_REFLECT.search(self._buf)),
                    ("close_reflect", self._CLOSE_REFLECT.search(self._buf)),
                    ("open_final", self._OPEN_FINAL.search(self._buf)),
                    ("close_final", self._CLOSE_FINAL.search(self._buf)),
                ]
                m_candidates = [(mode, m) for mode, m in m_candidates if m is not None]
                if not m_candidates:
                    # No tags found; if we never saw tags, stream as normal content.
                    if not self._saw_any_tag:
                        # Keep a small tail to avoid leaking partial tags across chunk boundaries.
                        if len(self._buf) <= self._MAX_TAG_LEN:
                            break
                        emit, self._buf = self._buf[:-self._MAX_TAG_LEN], self._buf[-self._MAX_TAG_LEN:]
                        cleaned = self._strip_stray_tags(emit)
                        if cleaned:
                            out.append({"content": cleaned})
                    else:
                        # Tags have been seen before; outside-tag text is usually meta noise. Drop it,
                        # but still keep a small tail to avoid leaking partial tags.
                        if len(self._buf) <= self._MAX_TAG_LEN:
                            break
                        self._buf = self._buf[-self._MAX_TAG_LEN:]
                    break

                # Pick earliest match
                mode, m = min(m_candidates, key=lambda x: x[1].start())
                before = self._buf[: m.start()]
                if before and not self._saw_any_tag:
                    cleaned = self._strip_stray_tags(before)
                    if cleaned:
                        out.append({"content": cleaned})
                self._buf = self._buf[m.end() :]
                self._saw_any_tag = True
                if mode == "open_reflect":
                    self._mode = "reflect"
                elif mode == "open_final":
                    self._mode = "final"
                else:
                    # close tags outside: drop and continue
                    self._mode = "outside"
                continue

            if self._mode == "reflect":
                m_close = self._CLOSE_REFLECT.search(self._buf)
                if not m_close:
                    # Emit most and keep tail to avoid leaking partial close tag.
                    if len(self._buf) <= self._MAX_TAG_LEN:
                        break
                    emit, self._buf = self._buf[:-self._MAX_TAG_LEN], self._buf[-self._MAX_TAG_LEN:]
                    if emit:
                        out.append({"reasoning": emit})
                    break
                inside = self._buf[: m_close.start()]
                if inside:
                    out.append({"reasoning": inside})
                self._buf = self._buf[m_close.end() :]
                self._mode = "outside"
                continue

            if self._mode == "final":
                m_close = self._CLOSE_FINAL.search(self._buf)
                if not m_close:
                    # Emit most and keep tail so `</final_answer>` split across chunks won't leak.
                    if len(self._buf) <= self._MAX_TAG_LEN:
                        break
                    emit, self._buf = self._buf[:-self._MAX_TAG_LEN], self._buf[-self._MAX_TAG_LEN:]
                    cleaned = self._strip_stray_tags(emit)
                    if cleaned:
                        out.append({"content": cleaned})
                    break
                inside = self._buf[: m_close.start()]
                if inside:
                    cleaned = self._strip_stray_tags(inside)
                    if cleaned:
                        out.append({"content": cleaned})
                self._buf = self._buf[m_close.end() :]
                self._mode = "outside"
                continue

            # Fallback: should not happen
            out.append({"content": self._buf})
            self._buf = ""
            break

        return out


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

    query = build_query_from_messages(req.messages, req.session_id)
    splitter = _ReflectFinalStreamSplitter()

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
            for delta_piece in splitter.feed(chunk_text):
                yield _sse_data({
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model_id,
                    "choices": [{"index": 0, "delta": delta_piece, "finish_reason": None}],
                })
        elif header.get("namespace") == "Template" and header.get("name") == "CallTool":
            tool_call = _tool_call_delta(payload)
            yield _sse_data({
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model_id,
                "choices": [{"index": 0, "delta": {"tool_calls": [tool_call]}, "finish_reason": None}],
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

    query = build_query_from_messages(req.messages, req.session_id)
    full_response = ""
    tool_calls: list[dict] = []

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
        elif header.get("namespace") == "Template" and header.get("name") == "CallTool":
            tool_calls.append(_tool_call_delta(payload))

    parsed = parse_ai_response(full_response)
    assistant_content = parsed.get("final_answer") or full_response
    assistant_reasoning = parsed.get("thinking")

    created = int(time.time())
    completion_id = f"chatcmpl-{uuid.uuid4().hex}"
    prompt_text = "\n".join((m.role + ": " + (m.content if isinstance(m.content, str) else "")) for m in (req.messages or []))
    prompt_tokens = _estimate_tokens(prompt_text)
    completion_tokens = _estimate_tokens(assistant_content)
    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": created,
        "model": model_id,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": assistant_content,
                    **({"reasoning": assistant_reasoning} if assistant_reasoning else {}),
                    **({"tool_calls": tool_calls} if tool_calls else {}),
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }

