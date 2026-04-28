# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Persona NLP Parser Module

Parses natural language descriptions to extract persona settings.
Uses pattern matching and keyword extraction.
"""

import re
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ParsedPersona:
    """Parsed persona from natural language"""
    ai_name: Optional[str] = None
    user_name: Optional[str] = None
    user_title: Optional[str] = None
    speaking_style: Optional[str] = None
    tone: Optional[str] = None
    personality: Optional[str] = None
    confidence: float = 0.0
    raw_extractions: Dict[str, Any] = None


class PersonaNLPParser:
    """
    Natural Language Parser for Persona Settings
    
    Extracts persona configuration from user descriptions.
    """
    
    # Patterns for AI name extraction
    AI_NAME_PATTERNS = [
        r"(?:你|AI|助手|机器人)?(?:叫|叫做|是|名为)?\s*[""']([^""']+)[""']",
        r"(?:名字|名称)(?:是|叫|为)?\s*[""']?([^""'，。]+?)[""']?(?:\s|$|[，。])",
        r"(?:叫我|称呼我)?\s*[""']?([^""'，。]{1,6})[""']?(?:吧|好了|就行)?",
        r"(?:设定|设置)(?:你|AI)?(?:名字|名称)?(?:为|是|叫)?\s*[""']?([^""'，。]+?)[""']?(?:\s|$|[，。])",
    ]
    
    # Patterns for user name extraction
    USER_NAME_PATTERNS = [
        r"(?:我|用户)?(?:叫|是|名为)?\s*[""']?([^""'，。]{1,10})[""']?",
        r"(?:称呼我|叫我)\s*[""']?([^""'，。]{1,10})[""']?",
        r"(?:我的?名字(?:是|叫))\s*[""']?([^""'，。]+?)[""']?(?:\s|$|[，。])",
    ]
    
    # Patterns for user title extraction
    USER_TITLE_PATTERNS = [
        r"(?:叫我|称呼我)(?:为)?\s*[""']?(主人|先生|女士|老板|领导|老师|朋友|小伙伴)[""']?",
        r"(?:用|以)([""']?)(主人|先生|女士|老板|领导|老师|朋友|小伙伴)\1(?:来)?(?:称呼|叫)",
    ]
    
    # Speaking style keywords
    STYLE_KEYWORDS = {
        "friendly": ["友好", "亲切", "和善", "温柔", "nice", "friendly", "kind"],
        "professional": ["专业", "职业", "正式", "professional", "formal"],
        "humorous": ["幽默", "风趣", "搞笑", "humorous", "funny", "witty"],
        "concise": ["简洁", "简短", "精练", "concise", "brief", "short"],
        "detailed": ["详细", "细致", "具体", "detailed", "thorough"],
        "casual": ["随意", "轻松", " casual", "relaxed", "easy-going"],
        "warm": ["温暖", "温馨", "warm", "heartwarming"],
        "playful": ["活泼", "俏皮", "playful", "lively"],
    }
    
    # Tone keywords
    TONE_KEYWORDS = {
        "formal": ["正式", "庄重", "formal", "serious"],
        "casual": ["随意", " casual", "informal", "relaxed"],
        "warm": ["温暖", "亲切", "warm", "friendly"],
        "professional": ["专业", "professional", "business-like"],
        "playful": ["活泼", "俏皮", "playful", "fun"],
    }
    
    # Personality traits
    PERSONALITY_TRAITS = {
        "humor": ["幽默", "风趣", "搞笑", "爱开玩笑", "humorous", "funny"],
        "empathy": ["有同理心", "体贴", "善解人意", "empathetic", "caring"],
        "patience": ["耐心", "有耐心", "patient"],
        "enthusiasm": ["热情", "热心", "enthusiastic", "passionate"],
        "calmness": ["冷静", "沉稳", "calm", "composed"],
        "creativity": ["有创意", "creative", "imaginative"],
    }
    
    @classmethod
    def parse(cls, text: str) -> ParsedPersona:
        """
        Parse natural language description
        
        Args:
            text: Natural language description
            
        Returns:
            Parsed persona
        """
        text = text.strip()
        if not text:
            return ParsedPersona()
        
        extractions = {}
        
        # Extract AI name
        ai_name = cls._extract_ai_name(text)
        if ai_name:
            extractions["ai_name"] = ai_name
        
        # Extract user name
        user_name = cls._extract_user_name(text)
        if user_name:
            extractions["user_name"] = user_name
        
        # Extract user title
        user_title = cls._extract_user_title(text)
        if user_title:
            extractions["user_title"] = user_title
        
        # Extract speaking style
        speaking_style = cls._extract_speaking_style(text)
        if speaking_style:
            extractions["speaking_style"] = speaking_style
        
        # Extract tone
        tone = cls._extract_tone(text)
        if tone:
            extractions["tone"] = tone
        
        # Extract personality
        personality = cls._extract_personality(text)
        if personality:
            extractions["personality"] = personality
        
        # Calculate confidence
        confidence = len(extractions) / 6  # 6 possible fields
        
        return ParsedPersona(
            ai_name=ai_name,
            user_name=user_name,
            user_title=user_title,
            speaking_style=speaking_style,
            tone=tone,
            personality=personality,
            confidence=confidence,
            raw_extractions=extractions,
        )
    
    @classmethod
    def _extract_ai_name(cls, text: str) -> Optional[str]:
        """Extract AI name from text"""
        for pattern in cls.AI_NAME_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                # Filter out common words
                if name and len(name) <= 10 and not name in ["我", "你", "AI", "助手"]:
                    return name
        return None
    
    @classmethod
    def _extract_user_name(cls, text: str) -> Optional[str]:
        """Extract user name from text"""
        for pattern in cls.USER_NAME_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                if name and len(name) <= 10 and not name in ["我", "你"]:
                    return name
        return None
    
    @classmethod
    def _extract_user_title(cls, text: str) -> Optional[str]:
        """Extract user title from text"""
        for pattern in cls.USER_TITLE_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1) if len(match.groups()) == 1 else match.group(2)
        return None
    
    @classmethod
    def _extract_speaking_style(cls, text: str) -> Optional[str]:
        """Extract speaking style from text"""
        found_styles = []
        
        for style, keywords in cls.STYLE_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text.lower():
                    found_styles.append(style)
                    break
        
        if found_styles:
            # Map to Chinese descriptions
            style_map = {
                "friendly": "友好亲切",
                "professional": "专业正式",
                "humorous": "幽默风趣",
                "concise": "简洁明了",
                "detailed": "详细细致",
                "casual": "轻松随意",
                "warm": "温暖贴心",
                "playful": "活泼俏皮",
            }
            return "、".join([style_map.get(s, s) for s in found_styles[:3]])
        
        return None
    
    @classmethod
    def _extract_tone(cls, text: str) -> Optional[str]:
        """Extract tone from text"""
        for tone, keywords in cls.TONE_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text.lower():
                    return tone
        return None
    
    @classmethod
    def _extract_personality(cls, text: str) -> Optional[str]:
        """Extract personality traits from text"""
        found_traits = []
        
        for trait, keywords in cls.PERSONALITY_TRAITS.items():
            for keyword in keywords:
                if keyword in text.lower():
                    found_traits.append(trait)
                    break
        
        if found_traits:
            trait_map = {
                "humor": "幽默",
                "empathy": "有同理心",
                "patience": "有耐心",
                "enthusiasm": "热情",
                "calmness": "沉稳",
                "creativity": "有创意",
            }
            return "、".join([trait_map.get(t, t) for t in found_traits])
        
        return None
    
    @classmethod
    def to_persona_settings(cls, parsed: ParsedPersona) -> Dict[str, Any]:
        """
        Convert parsed persona to settings dict
        
        Args:
            parsed: Parsed persona
            
        Returns:
            Settings dictionary
        """
        settings = {}
        
        if parsed.ai_name:
            settings["ai_name"] = parsed.ai_name
        if parsed.user_name:
            settings["user_name"] = parsed.user_name
        if parsed.user_title:
            settings["user_title"] = parsed.user_title
        if parsed.speaking_style:
            settings["speaking_style"] = parsed.speaking_style
        if parsed.tone:
            settings["tone"] = parsed.tone
        if parsed.personality:
            settings["personality"] = parsed.personality
        
        # Set defaults based on extracted values
        if "humor" in (parsed.personality or ""):
            settings["humor_level"] = 4
        if "empathy" in (parsed.personality or ""):
            settings["empathy_level"] = 4
        if parsed.tone == "formal":
            settings["formality_level"] = 4
        elif parsed.tone == "casual":
            settings["formality_level"] = 2
        
        return settings


# Example natural language inputs
EXAMPLE_INPUTS = [
    "你叫小智吧，叫我张先生，说话要幽默一点",
    "设定你的名字为'小管家'，称呼我为主人，风格要亲切体贴",
    "AI名字是助手，我叫李总，用专业正式的语气",
    "叫我小王就行，你叫小助手，说话简洁明了",
    "你的名字是小可爱，叫我姐姐，要活泼可爱一点",
]


def test_parser():
    """Test the parser with example inputs"""
    print("=" * 60)
    print("自然语言解析测试")
    print("=" * 60)
    
    for text in EXAMPLE_INPUTS:
        print(f"\n输入: {text}")
        print("-" * 60)
        
        parsed = PersonaNLPParser.parse(text)
        settings = PersonaNLPParser.to_persona_settings(parsed)
        
        print(f"解析结果:")
        print(f"  AI名字: {parsed.ai_name or '未识别'}")
        print(f"  用户名字: {parsed.user_name or '未识别'}")
        print(f"  用户尊称: {parsed.user_title or '未识别'}")
        print(f"  说话风格: {parsed.speaking_style or '未识别'}")
        print(f"  语气: {parsed.tone or '未识别'}")
        print(f"  性格: {parsed.personality or '未识别'}")
        print(f"  置信度: {parsed.confidence:.2f}")
        print(f"  生成设置: {settings}")


if __name__ == "__main__":
    test_parser()
