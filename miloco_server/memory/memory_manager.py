# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Memory Manager - Core memory management using Mem0 and ChromaDB.
记忆管理器 - 基于 Mem0 和 ChromaDB 的核心记忆管理
"""

import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

try:
    import chromadb
    from chromadb.config import Settings
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    chromadb = None
    Settings = None

try:
    from mem0 import Memory as Mem0Memory
    MEM0_AVAILABLE = True
except ImportError:
    MEM0_AVAILABLE = False
    Mem0Memory = None

from miloco_server.schema.memory_schema import (
    Memory as MemoryModel,
    MemoryType,
    MemorySearchResult,
    MemoryContext,
    MemoryStats,
)

logger = logging.getLogger(__name__)

DEFAULT_COLLECTION_NAME = "miloco_memory"
MEMORY_CHUNK_SIZE = 1000
MEMORY_OVERLAP = 200


class MemoryManager:
    """核心记忆管理器，提供记忆的 CRUD 和检索功能"""

    def __init__(self, persist_directory: Optional[str] = None):
        self.persist_directory = persist_directory or str(
            Path.home() / ".miloco" / "memory"
        )
        self.collection_name = DEFAULT_COLLECTION_NAME
        self._initialized = False
        self._mem0 = None
        self._collection = None
        self._client = None

    async def initialize(self) -> bool:
        """初始化记忆管理器"""
        if self._initialized:
            return True

        try:
            Path(self.persist_directory).mkdir(parents=True, exist_ok=True)

            if MEM0_AVAILABLE:
                config = {
                    "version": "v1.1",
                    "embedder": {
                        "provider": "huggingface",
                        "config": {
                            "model": "sentence-transformers/all-MiniLM-L6-v2",
                        },
                    },
                    "vector_store": {
                        "provider": "chroma",
                        "config": {
                            "collection_name": self.collection_name,
                            "path": self.persist_directory,
                        },
                    },
                }
                self._mem0 = Mem0Memory.from_config(config)
                logger.info("使用 Mem0 初始化记忆管理器")
            elif CHROMADB_AVAILABLE:
                self._client = chromadb.PersistentClient(
                    path=self.persist_directory,
                    settings=Settings(anonymized_telemetry=False),
                )
                self._collection = self._client.get_or_create_collection(
                    name=self.collection_name,
                    metadata={"hnsw:space": "cosine"},
                )
                logger.info("使用 ChromaDB 初始化记忆管理器")
            else:
                logger.warning("未安装 mem0 或 chromadb，记忆功能将使用内存存储")
                self._storage: Dict[str, MemoryModel] = {}

            self._initialized = True
            logger.info(f"记忆管理器初始化完成，存储目录: {self.persist_directory}")
            return True

        except Exception as e:
            logger.error(f"记忆管理器初始化失败: {e}")
            return False

    async def add_memory(
        self,
        content: str,
        memory_type: MemoryType = MemoryType.CONVERSATION,
        metadata: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        importance: float = 0.5,
    ) -> Optional[MemoryModel]:
        """添加新记忆"""
        await self.initialize()

        memory_id = str(uuid.uuid4())
        now = datetime.now()

        memory = MemoryModel(
            id=memory_id,
            content=content,
            memory_type=memory_type,
            metadata=metadata or {},
            session_id=session_id,
            importance=importance,
            created_at=now,
            updated_at=now,
        )

        try:
            if self._mem0:
                mem_metadata = {
                    "memory_type": memory_type.value,
                    "importance": str(importance),
                    "created_at": now.isoformat(),
                    **(metadata or {}),
                }
                if session_id:
                    mem_metadata["session_id"] = session_id

                result = self._mem0.add(
                    content,
                    user_id="miloco_user",
                    metadata=mem_metadata,
                )
                if result and "results" in result and result["results"]:
                    memory.id = result["results"][0].get("id", memory_id)
                logger.info(f"使用 Mem0 添加记忆: {memory.id}")

            elif self._collection:
                self._collection.add(
                    documents=[content],
                    metadatas=[{
                        "memory_type": memory_type.value,
                        "importance": str(importance),
                        "created_at": now.isoformat(),
                        **(metadata or {}),
                    }],
                    ids=[memory_id],
                )
                logger.info(f"使用 ChromaDB 添加记忆: {memory_id}")

            else:
                self._storage[memory_id] = memory
                logger.info(f"使用内存存储添加记忆: {memory_id}")

            return memory

        except Exception as e:
            logger.error(f"添加记忆失败: {e}")
            return None

    async def search_memories(
        self,
        query: str,
        limit: int = 10,
        memory_type: Optional[MemoryType] = None,
        min_importance: float = 0.0,
    ) -> List[MemorySearchResult]:
        """语义搜索记忆"""
        await self.initialize()

        try:
            results: List[MemorySearchResult] = []

            if self._mem0:
                search_results = self._mem0.search(
                    query,
                    user_id="miloco_user",
                    limit=limit,
                )
                if search_results and "results" in search_results:
                    for r in search_results["results"]:
                        rtype = r.get("metadata", {}).get("memory_type", "conversation")
                        if memory_type and rtype != memory_type.value:
                            continue
                        importance = float(r.get("metadata", {}).get("importance", "0.5"))
                        if importance < min_importance:
                            continue
                        results.append(MemorySearchResult(
                            memory=MemoryModel(
                                id=r.get("id", ""),
                                content=r.get("memory", ""),
                                memory_type=MemoryType(rtype),
                                metadata=r.get("metadata", {}),
                                importance=importance,
                            ),
                            score=r.get("score", 0.0),
                        ))

            elif self._collection:
                where_filter = {}
                if memory_type:
                    where_filter["memory_type"] = memory_type.value
                if min_importance > 0:
                    where_filter["importance"] = {"$gte": str(min_importance)}

                query_params = {
                    "query_texts": [query],
                    "n_results": limit,
                }
                if where_filter:
                    query_params["where"] = where_filter

                search_results = self._collection.query(**query_params)

                if search_results and search_results["documents"]:
                    for i, doc in enumerate(search_results["documents"][0]):
                        meta = (search_results["metadatas"][0][i]
                                if search_results.get("metadatas") else {})
                        distance = (search_results["distances"][0][i]
                                    if search_results.get("distances") else 0.0)
                        score = max(0.0, 1.0 - distance)
                        rid = (search_results["ids"][0][i]
                               if search_results.get("ids") else str(uuid.uuid4()))
                        rtype = meta.get("memory_type", "conversation")
                        importance = float(meta.get("importance", "0.5"))
                        results.append(MemorySearchResult(
                            memory=MemoryModel(
                                id=rid,
                                content=doc,
                                memory_type=MemoryType(rtype),
                                metadata=meta,
                                importance=importance,
                            ),
                            score=score,
                        ))

            else:
                for mem in self._storage.values():
                    if memory_type and mem.memory_type != memory_type:
                        continue
                    if mem.importance < min_importance:
                        continue
                    results.append(MemorySearchResult(memory=mem, score=0.5))
                results.sort(key=lambda x: x.score, reverse=True)
                results = results[:limit]

            results.sort(key=lambda x: x.score, reverse=True)
            logger.info(f"搜索记忆 '{query}'，返回 {len(results)} 条结果")
            return results

        except Exception as e:
            logger.error(f"搜索记忆失败: {e}")
            return []

    async def get_memory(self, memory_id: str) -> Optional[MemoryModel]:
        """获取单条记忆"""
        await self.initialize()

        try:
            if self._collection:
                result = self._collection.get(ids=[memory_id])
                if result and result["documents"]:
                    meta = result["metadatas"][0] if result["metadatas"] else {}
                    return MemoryModel(
                        id=memory_id,
                        content=result["documents"][0],
                        memory_type=MemoryType(meta.get("memory_type", "conversation")),
                        metadata=meta,
                        importance=float(meta.get("importance", "0.5")),
                    )
            elif hasattr(self, "_storage"):
                return self._storage.get(memory_id)
            return None
        except Exception as e:
            logger.error(f"获取记忆失败: {e}")
            return None

    async def delete_memory(self, memory_id: str) -> bool:
        """删除记忆"""
        await self.initialize()

        try:
            if self._collection:
                self._collection.delete(ids=[memory_id])
                logger.info(f"删除记忆: {memory_id}")
                return True
            elif hasattr(self, "_storage"):
                if memory_id in self._storage:
                    del self._storage[memory_id]
                    return True
            return False
        except Exception as e:
            logger.error(f"删除记忆失败: {e}")
            return False

    async def update_memory(
        self,
        memory_id: str,
        content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        importance: Optional[float] = None,
    ) -> Optional[MemoryModel]:
        """更新记忆"""
        existing = await self.get_memory(memory_id)
        if not existing:
            return None

        new_content = content or existing.content
        new_metadata = {**existing.metadata}
        if metadata:
            new_metadata.update(metadata)
        if importance is not None:
            new_metadata["importance"] = str(importance)
        new_metadata["updated_at"] = datetime.now().isoformat()

        await self.delete_memory(memory_id)

        new_memory = await self.add_memory(
            content=new_content,
            memory_type=existing.memory_type,
            metadata=new_metadata,
            session_id=existing.session_id,
            importance=importance or existing.importance,
        )

        if new_memory:
            logger.info(f"更新记忆: {memory_id} -> {new_memory.id}")

        return new_memory

    async def get_context(
        self,
        query: str,
        max_memories: int = 5,
        min_importance: float = 0.3,
    ) -> MemoryContext:
        """获取与查询相关的记忆上下文"""
        search_results = await self.search_memories(
            query=query,
            limit=max_memories,
            min_importance=min_importance,
        )

        relevant_memories = [r.memory for r in search_results]

        summary_parts = []
        for mem in relevant_memories:
            summary_parts.append(f"- {mem.content}")
        summary = "\n".join(summary_parts) if summary_parts else "暂无相关记忆"

        return MemoryContext(
            query=query,
            relevant_memories=relevant_memories,
            summary=summary,
            total_count=len(relevant_memories),
        )

    async def get_stats(self) -> MemoryStats:
        """获取记忆统计信息"""
        await self.initialize()

        total_count = 0
        type_counts: Dict[str, int] = {}
        avg_importance = 0.0

        try:
            if self._collection:
                result = self._collection.get()
                if result and result["documents"]:
                    total_count = len(result["documents"])
                    for meta in (result["metadatas"] or []):
                        mtype = meta.get("memory_type", "conversation")
                        type_counts[mtype] = type_counts.get(mtype, 0) + 1
                    importances = [
                        float(meta.get("importance", "0.5"))
                        for meta in (result["metadatas"] or [])
                    ]
                    if importances:
                        avg_importance = sum(importances) / len(importances)
            elif hasattr(self, "_storage"):
                total_count = len(self._storage)
                for mem in self._storage.values():
                    mtype = mem.memory_type.value
                    type_counts[mtype] = type_counts.get(mtype, 0) + 1
                if self._storage:
                    avg_importance = sum(
                        m.importance for m in self._storage.values()
                    ) / len(self._storage)

        except Exception as e:
            logger.error(f"获取统计信息失败: {e}")

        return MemoryStats(
            total_count=total_count,
            type_counts=type_counts,
            avg_importance=avg_importance,
        )

    async def shutdown(self):
        """关闭记忆管理器"""
        self._client = None
        self._collection = None
        self._initialized = False
        logger.info("记忆管理器已关闭")


_memory_manager: Optional[MemoryManager] = None


def get_memory_manager() -> Optional[MemoryManager]:
    return _memory_manager


async def initialize_memory_manager(
    persist_directory: Optional[str] = None,
) -> MemoryManager:
    global _memory_manager
    _memory_manager = MemoryManager(persist_directory)
    await _memory_manager.initialize()
    return _memory_manager
