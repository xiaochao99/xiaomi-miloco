# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Strip markdown / markup for TTS playback (XiaoAI bridge)."""

from __future__ import annotations

import re


def plain_text_for_tts(text: str) -> str:
    """
    Convert model/markdown-style text to plain speech-friendly lines.
    Best-effort: removes common markdown so TTS does not read symbols like # or **.
    Preserves MiMo-V2.5-TTS audio tags like [笑声], [叹气], [停顿] etc.
    """
    if not text:
        return ""

    s = text.replace("\r\n", "\n").replace("\r", "\n")

    audio_tags = re.findall(r'\[[^\]]+\]', s)
    
    placeholders = []
    for i, tag in enumerate(audio_tags):
        placeholder = f"__AUDIO_TAG_{i}__"
        placeholders.append((placeholder, tag))
        s = s.replace(tag, placeholder, 1)

    s = re.sub(r"```[\w-]*\n?[\s\S]*?```", " ", s)
    s = re.sub(r"`{3}[\s\S]*?`{3}", " ", s)

    s = re.sub(r"`([^`]+)`", r"\1", s)

    s = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s)

    s = re.sub(r"\*{2}([^*]+)\*{2}", r"\1", s)
    s = re.sub(r"_{2}([^_]+)_{2}", r"\1", s)

    s = re.sub(r"(?m)^#+\s*", "", s)

    s = re.sub(r"(?m)^\s*[-*+]\s+", "", s)
    s = re.sub(r"(?m)^\s*\d+\.\s+", "", s)
    s = re.sub(r"(?m)^\s*>\s*", "", s)

    s = re.sub(r"(?m)^\s*[-*_]{3,}\s*$", "", s)

    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)

    for placeholder, tag in placeholders:
        s = s.replace(placeholder, tag)

    return s.strip()
