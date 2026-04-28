# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Memory Module
记忆模块 - 提供长期记忆管理功能

功能：
1. 记忆存储 - 基于 ChromaDB 的向量存储
2. 记忆检索 - 语义检索 + 关键词检索
3. 记忆提取 - 从对话中自动提取重要信息
4. 记忆管理 - 手动添加、编辑、删除记忆
"""

from miloco_server.memory.memory_manager import (
    MemoryManager,
    get_memory_manager,
    initialize_memory_manager,
)
from miloco_server.memory.memory_retriever import (
    MemoryRetriever,
    get_memory_retriever,
)
from miloco_server.memory.memory_extractor import (
    MemoryExtractor,
    SmartMemoryFilter,
)

__all__ = [
    "MemoryManager",
    "get_memory_manager",
    "initialize_memory_manager",
    "MemoryRetriever",
    "get_memory_retriever",
    "MemoryExtractor",
    "SmartMemoryFilter",
]
