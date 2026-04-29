# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Memory Manager - Core memory management using Mem0 and ChromaDB.
记忆管理器 - 基于 Mem0 和 ChromaDB 的核心记忆管理
"""

import logging
import uuid
import hashlib
from difflib import SequenceMatcher
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
        self._content_hash_cache: Dict[str, List[str]] = {}  # 内容哈希缓存
        self._similarity_threshold = 0.85  # 相似度阈值

    def _compute_content_hash(self, content: str) -> str:
        """计算内容的哈希值，用于快速去重"""
        return hashlib.md5(content.strip().lower().encode('utf-8')).hexdigest()

    def _compute_similarity(self, text1: str, text2: str) -> float:
        """计算两个文本的相似度"""
        return SequenceMatcher(None, text1.strip().lower(), text2.strip().lower()).ratio()

    async def _find_duplicate_memory(
        self,
        content: str,
        memory_type: Optional[MemoryType] = None,
        session_id: Optional[str] = None,
    ) -> Optional[MemoryModel]:
        """查找重复的记忆"""
        content_hash = self._compute_content_hash(content)
        
        # 1. 快速检查：使用内容哈希缓存
        if content_hash in self._content_hash_cache:
            for mem_id in self._content_hash_cache[content_hash]:
                existing = await self.get_memory(mem_id)
                if existing:
                    if memory_type and existing.memory_type != memory_type:
                        continue
                    if session_id and existing.session_id != session_id:
                        continue
                    return existing
        
        # 2. 精确搜索：使用语义搜索查找相似记忆
        search_results = await self.search_memories(
            query=content,
            limit=5,
            memory_type=memory_type,
            min_importance=0.0,
        )
        
        # 3. 检查相似度
        for result in search_results:
            similarity = self._compute_similarity(content, result.memory.content)
            if similarity >= self._similarity_threshold:
                if session_id and result.memory.session_id != session_id:
                    continue
                return result.memory
        
        return None

    async def _update_content_hash_cache(self):
        """更新内容哈希缓存"""
        self._content_hash_cache = {}
        
        try:
            if self._collection:
                result = self._collection.get()
                if result and result["documents"] and result["ids"]:
                    for i, doc in enumerate(result["documents"]):
                        content_hash = self._compute_content_hash(doc)
                        if content_hash not in self._content_hash_cache:
                            self._content_hash_cache[content_hash] = []
                        self._content_hash_cache[content_hash].append(result["ids"][i])
            elif hasattr(self, "_storage"):
                for mem_id, mem in self._storage.items():
                    content_hash = self._compute_content_hash(mem.content)
                    if content_hash not in self._content_hash_cache:
                        self._content_hash_cache[content_hash] = []
                    self._content_hash_cache[content_hash].append(mem_id)
        except Exception as e:
            logger.warning(f"更新内容哈希缓存失败: {e}")

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
            
            await self._update_content_hash_cache()
            
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
        skip_duplicate_check: bool = False,
        update_if_exists: bool = True,
    ) -> Optional[MemoryModel]:
        """添加新记忆（带去重功能）"""
        await self.initialize()
        
        if not content or not content.strip():
            logger.debug("跳过添加记忆内容为空")
            return None

        # 1. 检查是否存在重复记忆
        if not skip_duplicate_check:
            duplicate = await self._find_duplicate_memory(
                content=content,
                memory_type=memory_type,
                session_id=session_id,
            )
            if duplicate:
                    if update_if_exists:
                        logger.info(f"发现重复记忆，更新现有记忆: {duplicate.id}")
                        return await self.update_memory(
                            memory_id=duplicate.id,
                            content=content,
                            metadata=metadata,
                            importance=max(importance, duplicate.importance),
                        )
                    else:
                        logger.info(f"发现重复记忆，跳过添加: {duplicate.id}")
                        return duplicate

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
            
            # 更新内容哈希缓存
            content_hash = self._compute_content_hash(content)
            if content_hash not in self._content_hash_cache:
                self._content_hash_cache[content_hash] = []
            self._content_hash_cache[content_hash].append(memory_id)

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
            elif hasattr(self, "_storage"):
                if memory_id in self._storage:
                    del self._storage[memory_id]
            
            # 更新内容哈希缓存
            for content_hash, ids in list(self._content_hash_cache.items()):
                if memory_id in ids:
                    ids.remove(memory_id)
                    if not ids:
                        del self._content_hash_cache[content_hash]
            
            return True
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
            skip_duplicate_check=True,  # 更新时跳过重复检查
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

    async def add_memories_batch(
        self,
        memories_data: List[Dict[str, Any]],
    ) -> List[Optional[MemoryModel]]:
        """批量添加记忆"""
        results = []
        skipped = 0
        added = 0
        
        for mem_data in memories_data:
            result = await self.add_memory(
                content=mem_data.get("content", ""),
                memory_type=mem_data.get("memory_type", MemoryType.CONVERSATION),
                metadata=mem_data.get("metadata"),
                session_id=mem_data.get("session_id"),
                importance=mem_data.get("importance", 0.5),
            )
            
            if result:
                # 检查是否是已有记忆（被更新）
                if mem_data.get("content") and result.content == mem_data.get("content"):
                    # 检查是否在哈希缓存中是否已有多个条目
                    content_hash = self._compute_content_hash(mem_data.get("content"))
                    if content_hash in self._content_hash_cache and len(self._content_hash_cache[content_hash]) > 1:
                        skipped += 1
                    else:
                        added += 1
                results.append(result)
            else:
                results.append(None)
        
        logger.info(f"批量添加完成: 新增 {added}, 跳过重复 {skipped}, 总共处理 {len(memories_data)}")
        return results

    async def get_stats(self) -> MemoryStats:
        """获取记忆统计信息"""
        await self.initialize()

        total_count = 0
        type_counts: Dict[str, int] = {}
        avg_importance = 0.0
        cached_hash_count = len(self._content_hash_cache)

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
            metadata={
                "cached_hash_count": cached_hash_count,
                "similarity_threshold": self._similarity_threshold,
            }
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
