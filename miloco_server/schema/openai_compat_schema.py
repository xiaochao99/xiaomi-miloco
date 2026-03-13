from __future__ import annotations

"""
OpenAI compatible request/response schemas & helpers shared by controllers.

This module intentionally avoids importing controllers to prevent circular imports.
"""

from typing import Any, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class OpenAIChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"] = Field(...)
    content: Optional[Union[str, List[Any]]] = Field(default=None)


class OpenAIChatCompletionRequest(BaseModel):
    """
    Minimal OpenAI-compatible chat completion request.

    Notes:
    - Accept extra fields for compatibility.
    - Extensions used by Miloco AI Chat:
      - session_id: multi-turn memory
      - camera_ids, mcp_list: forwarded to AI chat adapter; if None, adapter will auto-select
    """

    model_config = ConfigDict(extra="allow")

    model: Optional[str] = Field(default=None)
    messages: List[OpenAIChatMessage] = Field(default_factory=list)
    stream: bool = Field(default=False)

    # Non-standard extensions (optional)
    session_id: Optional[str] = Field(default=None, description="Miloco AI Chat session_id")
    camera_ids: Optional[List[str]] = Field(default=None, description="Camera DID list")
    mcp_list: Optional[List[str]] = Field(default=None, description="MCP service id list")


def extract_text_from_content(content: Optional[Union[str, List[Any]]]) -> str:
    """
    OpenAI messages.content can be a string or a list of content parts.
    Support:
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


def build_query_from_messages(messages: List[OpenAIChatMessage], session_id: Optional[str]) -> str:
    """
    Build a single query string for Miloco AI Chat.

    - If session_id is provided: use the latest user message content as query.
    - Otherwise: include a short history prefix (best-effort) and the latest user message.
    """
    last_user = ""
    for m in reversed(messages or []):
        if m.role == "user":
            last_user = extract_text_from_content(m.content).strip()
            if last_user:
                break

    if session_id:
        return last_user or ""

    history_lines: List[str] = []
    for m in messages[:-1]:
        if m.role in ("user", "assistant", "system"):
            txt = extract_text_from_content(m.content).strip()
            if not txt:
                continue
            prefix = "User" if m.role == "user" else ("Assistant" if m.role == "assistant" else "System")
            history_lines.append(f"{prefix}: {txt}")

    history = "\n".join(history_lines)
    if history:
        history = history[-2000:]
        return f"对话历史（供参考）：\n{history}\n\n当前问题：{last_user}"

    return last_user

