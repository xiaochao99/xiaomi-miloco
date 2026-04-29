# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Memory Extractor - Extract important information from conversations.
记忆提取器 - 从对话中自动提取重要信息
"""

import logging
import re
import hashlib
from typing import List, Dict, Any, Optional
from datetime import datetime

from miloco_server.schema.memory_schema import (
    Memory,
    MemoryType,
    MemoryExtractionResult,
)

logger = logging.getLogger(__name__)

USER_PREFERENCE_KEYWORDS = [
    "喜欢", "偏好", "习惯", "喜欢用", "经常", "总是",
    "不喜欢", "不要", "别", "别用", "不用", "不需要",
    "prefer", "like", "always", "usually", "dislike", "hate",
    "want", "need", "don't want", "never",
]

IMPORTANT_KEYWORDS = [
    "重要", "记住", "备注", "注意", "关键", "务必",
    "important", "remember", "note", "key", "must",
]

ROOM_OBJECT_KEYWORDS = [
    "客厅", "卧室", "厨房", "卫生间", "书房", "阳台",
    "房间", "门口", "走廊", "花园", "车库",
    "living room", "bedroom", "kitchen", "bathroom",
    "study", "balcony", "room", "doorway", "hallway",
]

PET_KEYWORDS = [
    "猫", "狗", "宠物", "小猫", "小狗", "喵", "汪",
    "cat", "dog", "pet", "kitten", "puppy",
]

SCHEDULE_KEYWORDS = [
    "每天", "定时", "早上", "晚上", "中午", "下午",
    "上午", "深夜", "凌晨", "每周", "工作日", "周末",
    "daily", "morning", "evening", "noon", "afternoon",
    "night", "midnight", "weekly", "weekday", "weekend",
]


class SmartMemoryFilter:
    """智能过滤器，判断对话是否包含值得记忆的信息"""

    def __init__(self):
        self._history: List[str] = []
        self._max_history = 50

    def should_extract(self, messages: List[Dict[str, str]]) -> bool:
        if not messages:
            return False

        last_user_msg = None
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_user_msg = msg.get("content", "")
                break

        if not last_user_msg:
            return False

        text = last_user_msg.lower()

        has_keywords = (
            any(kw in text for kw in USER_PREFERENCE_KEYWORDS)
            or any(kw in text for kw in IMPORTANT_KEYWORDS)
            or any(kw in text for kw in SCHEDULE_KEYWORDS)
        )

        is_question = any(c in text for c in ["？", "?", "吗", "呢"])
        is_short = len(text) < 5

        if has_keywords:
            return True

        if is_short:
            return False

        self._history.append(last_user_msg)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        if len(messages) >= 4:
            return True

        return False

    def get_extraction_hints(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        hints: Dict[str, Any] = {}

        all_text = " ".join(
            msg.get("content", "")
            for msg in messages
            if msg.get("role") == "user"
        ).lower()

        if any(kw in all_text for kw in USER_PREFERENCE_KEYWORDS):
            hints["check_preferences"] = True
        if any(kw in all_text for kw in ROOM_OBJECT_KEYWORDS):
            hints["check_spatial"] = True
        if any(kw in all_text for kw in PET_KEYWORDS):
            hints["check_pet_info"] = True
        if any(kw in all_text for kw in SCHEDULE_KEYWORDS):
            hints["check_schedule"] = True

        return hints


class MemoryExtractor:
    """对话记忆提取器"""

    def __init__(self):
        self.smart_filter = SmartMemoryFilter()
        self._extraction_cache: Dict[str, MemoryExtractionResult] = {}
        self._processed_message_hashes: set = set()  # 已处理消息的哈希集合
        self._max_cache_size = 1000

    def _compute_message_hash(self, message: Dict[str, str]) -> str:
        """计算消息的哈希值（使用原始内容）"""
        content = message.get("content", "")
        role = message.get("role", "")
        combined = f"{role}:{content}"
        return hashlib.md5(combined.encode('utf-8')).hexdigest()

    def _get_new_messages(self, messages: List[Dict[str, str]], session_id: Optional[str] = None) -> List[Dict[str, str]]:
        """获取尚未处理过的新消息"""
        new_messages = []
        session_key = f"session:{session_id}" if session_id else "global"
        
        if not hasattr(self, "_session_processed_hashes"):
            self._session_processed_hashes: Dict[str, set] = {}
        
        if session_key not in self._session_processed_hashes:
            self._session_processed_hashes[session_key] = set()
        
        session_hashes = self._session_processed_hashes[session_key]
        
        for msg in messages:
            msg_hash = self._compute_message_hash(msg)
            if msg_hash not in session_hashes:
                new_messages.append(msg)
                session_hashes.add(msg_hash)
        
        if len(session_hashes) > self._max_cache_size:
            oldest_keys = list(self._session_processed_hashes.keys())[:-self._max_cache_size//10]
            for key in oldest_keys:
                del self._session_processed_hashes[key]
        
        return new_messages

    def _clear_cache(self):
        """清理缓存"""
        if hasattr(self, "_session_processed_hashes"):
            self._session_processed_hashes.clear()
        self._extraction_cache.clear()

    def extract_from_conversation(
        self,
        messages: List[Dict[str, str]],
        session_id: Optional[str] = None,
        only_new_messages: bool = True,
    ) -> MemoryExtractionResult:
        """从对话历史中提取记忆（避免重复提取）"""
        if not messages:
            return MemoryExtractionResult(
                memories=[], extraction_time=datetime.now()
            )
        
        # 只处理新消息
        target_messages = messages
        if only_new_messages:
            target_messages = self._get_new_messages(messages, session_id)
            if not target_messages:
                logger.debug("没有新消息需要处理，跳过记忆提取")
                return MemoryExtractionResult(
                    memories=[], extraction_time=datetime.now()
                )

        if not self.smart_filter.should_extract(target_messages):
            return MemoryExtractionResult(
                memories=[], extraction_time=datetime.now()
            )

        hints = self.smart_filter.get_extraction_hints(target_messages)
        memories: List[Memory] = []

        user_msgs = [m for m in target_messages if m.get("role") == "user"]
        assistant_msgs = [m for m in target_messages if m.get("role") == "assistant"]

        if hints.get("check_preferences"):
            prefs = self._extract_preferences(user_msgs, session_id)
            memories.extend(prefs)

        if hints.get("check_spatial"):
            spatial = self._extract_spatial_info(user_msgs, session_id)
            memories.extend(spatial)

        if hints.get("check_pet_info"):
            pet_info = self._extract_pet_info(user_msgs, session_id)
            memories.extend(pet_info)

        if hints.get("check_schedule"):
            schedules = self._extract_schedule_info(user_msgs, session_id)
            memories.extend(schedules)

        if len(target_messages) >= 4 and not memories:
            summary = self._generate_conversation_summary(
                user_msgs, assistant_msgs
            )
            if summary:
                memories.append(Memory(
                    content=summary,
                    memory_type=MemoryType.CONVERSATION,
                    metadata={"type": "conversation_summary"},
                    session_id=session_id,
                    importance=0.4,
                ))

        result = MemoryExtractionResult(
            memories=memories,
            extraction_time=datetime.now(),
            metadata={"hints": hints, "message_count": len(target_messages), "total_messages": len(messages)},
        )

        logger.info(
            f"从 {len(target_messages)} 条新消息中提取了 {len(memories)} 条记忆，"
            f"提示: {list(hints.keys())}"
        )
        return result

    def _extract_preferences(
        self,
        messages: List[Dict[str, str]],
        session_id: Optional[str],
    ) -> List[Memory]:
        memories: List[Memory] = []
        patterns = [
            r"我(?:喜欢|偏好|习惯|想要|需要|不想|不要|别)",
            r"(?:please|i|I)\s+(?:like|prefer|want|need|don't want|avoid)",
        ]

        for msg in messages:
            content = msg.get("content", "")
            for pattern in patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    memories.append(Memory(
                        content=content,
                        memory_type=MemoryType.USER_PREFERENCE,
                        metadata={
                            "type": "user_preference",
                            "source_message": content[:200],
                        },
                        session_id=session_id,
                        importance=0.7,
                    ))
                    break

        return memories

    def _extract_spatial_info(
        self,
        messages: List[Dict[str, str]],
        session_id: Optional[str],
    ) -> List[Memory]:
        memories: List[Memory] = []

        for msg in messages:
            content = msg.get("content", "")
            for room in ROOM_OBJECT_KEYWORDS:
                if room in content.lower():
                    memories.append(Memory(
                        content=content,
                        memory_type=MemoryType.OBJECT_LOCATION,
                        metadata={
                            "type": "spatial_info",
                            "room": room,
                            "source_message": content[:200],
                        },
                        session_id=session_id,
                        importance=0.6,
                    ))
                    break

        return memories

    def _extract_pet_info(
        self,
        messages: List[Dict[str, str]],
        session_id: Optional[str],
    ) -> List[Memory]:
        memories: List[Memory] = []

        for msg in messages:
            content = msg.get("content", "")
            for pet in PET_KEYWORDS:
                if pet in content.lower():
                    memories.append(Memory(
                        content=content,
                        memory_type=MemoryType.PET_BEHAVIOR,
                        metadata={
                            "type": "pet_info",
                            "pet_type": pet,
                            "source_message": content[:200],
                        },
                        session_id=session_id,
                        importance=0.6,
                    ))
                    break

        return memories

    def _extract_schedule_info(
        self,
        messages: List[Dict[str, str]],
        session_id: Optional[str],
    ) -> List[Memory]:
        memories: List[Memory] = []

        for msg in messages:
            content = msg.get("content", "")
            for time_word in SCHEDULE_KEYWORDS:
                if time_word in content.lower():
                    memories.append(Memory(
                        content=content,
                        memory_type=MemoryType.SCHEDULE,
                        metadata={
                            "type": "schedule_info",
                            "time_ref": time_word,
                            "source_message": content[:200],
                        },
                        session_id=session_id,
                        importance=0.7,
                    ))
                    break

        return memories

    def _generate_conversation_summary(
        self,
        user_msgs: List[Dict[str, str]],
        assistant_msgs: List[Dict[str, str]],
    ) -> Optional[str]:
        if not user_msgs:
            return None

        topics = []
        for msg in user_msgs[-3:]:
            content = msg.get("content", "")
            if len(content) > 10:
                short = content[:100] + ("..." if len(content) > 100 else "")
                topics.append(short)

        if topics:
            return f"用户讨论了: {'; '.join(topics)}"
        return None
