from __future__ import annotations

import re
from typing import Optional, List


def extract_tag_blocks(text: str, tag: str) -> List[str]:
    """
    Extract all blocks inside <tag>...</tag> (case-insensitive, dotall).
    Returns the raw inner strings (not stripped).
    """
    if not text or not tag:
        return []
    pattern = re.compile(rf"<{re.escape(tag)}>(.*?)</{re.escape(tag)}>", re.IGNORECASE | re.DOTALL)
    return pattern.findall(text) or []


def extract_first_tag(text: str, tag: str) -> Optional[str]:
    """Extract the first <tag>...</tag> block, stripped. Returns None if not found."""
    blocks = extract_tag_blocks(text, tag)
    if not blocks:
        return None
    first = blocks[0].strip()
    return first if first else None


def extract_final_answer(text: str) -> Optional[str]:
    return extract_first_tag(text, "final_answer")


def extract_reflect_blocks(text: str) -> List[str]:
    return extract_tag_blocks(text, "reflect")

