# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Strip markdown / markup for TTS playback (XiaoAI bridge)."""

from __future__ import annotations

import re


def plain_text_for_tts(text: str) -> str:
    """
    Convert model/markdown-style text to plain speech-friendly lines.
    Best-effort: removes common markdown so TTS does not read symbols like # or **.
    """
    if not text:
        return ""

    s = text.replace("\r\n", "\n").replace("\r", "\n")

    # fenced code blocks
    s = re.sub(r"```[\w-]*\n?[\s\S]*?```", " ", s)
    s = re.sub(r"`{3}[\s\S]*?`{3}", " ", s)

    # inline code
    s = re.sub(r"`([^`]+)`", r"\1", s)

    # images ![alt](url) -> alt
    s = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", s)
    # links [text](url) -> text
    s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s)

    # bold (keep inner text)
    s = re.sub(r"\*{2}([^*]+)\*{2}", r"\1", s)
    s = re.sub(r"_{2}([^_]+)_{2}", r"\1", s)

    # headings
    s = re.sub(r"(?m)^#+\s*", "", s)

    # list / quote markers at line start
    s = re.sub(r"(?m)^\s*[-*+]\s+", "", s)
    s = re.sub(r"(?m)^\s*\d+\.\s+", "", s)
    s = re.sub(r"(?m)^\s*>\s*", "", s)

    # horizontal rules
    s = re.sub(r"(?m)^\s*[-*_]{3,}\s*$", "", s)

    # collapse spaces and blank lines
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)

    return s.strip()
