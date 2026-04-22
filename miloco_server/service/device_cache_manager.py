# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
设备状态缓存管理器
集成到现有服务架构中，复用 HaStateListener 的 WebSocket 连接
"""

import logging
from typing import Optional, Dict, Any, List

from miloco_server.dao.kv_dao import KVDao
from miloco_server.proxy.ha_listener import HaStateListener
from miloco_server.schema.miot_schema import HAConfig

logger = logging.getLogger(__name__)


class DeviceCacheManager:
    """
    设备状态缓存管理器
    
    复用现有的 HaStateListener WebSocket 连接，避免重复创建连接
    提供高速缓存查询接口给 MCP 使用
    """
    
    _instance: Optional["DeviceCacheManager"] = None
    
    def __new__(cls, *args, **kwargs):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, kv_dao: Optional[KVDao] = None):
        if self._initialized:
            return
        
        self._kv_dao = kv_dao
        self._ha_listener: Optional[HaStateListener] = None
        self._initialized = True
        self._started = False
    
    def set_ha_listener(self, ha_listener: HaStateListener) -> None:
        """
        设置 HaStateListener 实例
        
        由 TriggerRuleRunner 在创建 HaStateListener 后调用
        """
        self._ha_listener = ha_listener
        if ha_listener is not None:
            self._started = True
            logger.info("DeviceCacheManager connected to HaStateListener")
        else:
            self._started = False
    
    @property
    def is_started(self) -> bool:
        """是否已启动（是否有可用的 HaStateListener）"""
        # 只要设置了 HaStateListener 就认为已启动
        # WebSocket 连接是异步的，可能还没连接成功，但缓存仍然可用
        return self._started and self._ha_listener is not None
    
    def get_state(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """
        获取设备状态（从 HaStateListener 缓存）
        
        这是一个同步方法，直接读取内存，响应速度极快（<1ms）
        """
        if not self._ha_listener:
            return None
        return self._ha_listener.get_state(entity_id)
    
    def get_all_states(self) -> Dict[str, Dict[str, Any]]:
        """获取所有设备状态"""
        if not self._ha_listener:
            return {}
        return self._ha_listener.get_all_states()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计"""
        if not self._ha_listener:
            return {"status": "not_initialized"}
        
        states = self._ha_listener.get_all_states()
        return {
            "status": "running" if self._ha_listener.is_connected else "disconnected",
            "total_cached": len(states),
            "is_connected": self._ha_listener.is_connected
        }


# 全局实例（用于单例模式）
_device_cache_manager: Optional[DeviceCacheManager] = None


def get_device_cache_manager(kv_dao: Optional[KVDao] = None) -> DeviceCacheManager:
    """
    获取 DeviceCacheManager 单例
    
    Args:
        kv_dao: KV DAO 实例，首次调用时需要提供
    
    Returns:
        DeviceCacheManager 实例
    """
    global _device_cache_manager
    
    if _device_cache_manager is None:
        _device_cache_manager = DeviceCacheManager(kv_dao)
    
    return _device_cache_manager
