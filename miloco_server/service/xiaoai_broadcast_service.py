"""
XiaoAI broadcast service.

When enabled via environment variables, this service forwards Miloco chat replies
to open-xiaoai-bridge `/api/play/text` for playback on XiaoAI speakers.
"""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)


def _is_enabled() -> bool:
    value = str(os.getenv("MILOCO_XIAOAI_BROADCAST_ENABLED", "0")).strip().lower()
    return value in {"1", "true", "yes", "on"}


def _extract_speak_text(response_text: str) -> str:
    if not response_text:
        return ""

    text = response_text

    lower_text = response_text.lower()
    open_tag = "<final_answer>"
    close_tag = "</final_answer>"
    start = lower_text.find(open_tag)
    end = lower_text.find(close_tag)
    if start != -1 and end != -1 and end > start:
        content_start = start + len(open_tag)
        text = response_text[content_start:end].strip()

    return text.strip()


async def _broadcast_text(text: str, require_enabled: bool = True) -> bool:
    if require_enabled and not _is_enabled():
        return False
    if not text:
        return False
    base_url = os.getenv("MILOCO_XIAOAI_BRIDGE_URL", "http://127.0.0.1:9092").rstrip("/")
    token = os.getenv("MILOCO_XIAOAI_BRIDGE_TOKEN", "").strip()
    timeout_seconds = float(os.getenv("MILOCO_XIAOAI_BROADCAST_TIMEOUT", "5"))

    headers: dict[str, str] = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    endpoint = f"{base_url}/api/play/text"
    payload = {"text": text}

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            resp = await client.post(endpoint, json=payload, headers=headers)
            if resp.status_code >= 400:
                logger.warning(
                    "XiaoAI broadcast failed, status=%s, body=%s",
                    resp.status_code,
                    resp.text[:300],
                )
                return False
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning("XiaoAI broadcast request failed: %s", exc)
        return False

    logger.info("XiaoAI broadcast success")
    return True


async def broadcast_text(text: str, require_enabled: bool = False) -> bool:
    """
    Broadcast plain text to open-xiaoai-bridge.

    When require_enabled=False, this is suitable for rule actions where the action
    itself controls whether broadcasting should happen.
    """
    return await _broadcast_text(text.strip(), require_enabled=require_enabled)


async def broadcast_chat_reply(response_text: str) -> bool:
    """
    Broadcast chat reply to open-xiaoai-bridge.

    Environment variables:
    - MILOCO_XIAOAI_BROADCAST_ENABLED: 1/true to enable
    - MILOCO_XIAOAI_BRIDGE_URL: bridge base url, default http://127.0.0.1:9092
    - MILOCO_XIAOAI_BRIDGE_TOKEN: optional bridge token
    - MILOCO_XIAOAI_BROADCAST_TIMEOUT: request timeout seconds, default 5
    """
    speak_text = _extract_speak_text(response_text)
    if not speak_text:
        return False
    return await _broadcast_text(speak_text, require_enabled=True)
