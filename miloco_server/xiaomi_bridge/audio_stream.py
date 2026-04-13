# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
WebSocket音频流处理器
接收小米音箱的音频流并处理
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional, Dict, Set
from dataclasses import dataclass

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


@dataclass
class AudioStreamConfig:
    """音频流配置"""
    sample_rate: int = 16000
    channels: int = 1
    chunk_size: int = 320  # 20ms at 16kHz


class AudioStreamManager:
    """
    WebSocket音频流管理器
    接收来自小米音箱的音频流
    """
    
    _instance: Optional[AudioStreamManager] = None
    
    def __init__(self):
        self._connections: Dict[str, WebSocket] = {}
        self._audio_handler = None
        self._running = False
        self._config = AudioStreamConfig()
    
    @classmethod
    def instance(cls) -> AudioStreamManager:
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def set_audio_handler(self, handler):
        """设置音频处理回调"""
        self._audio_handler = handler
    
    async def start(self):
        """启动音频流管理器"""
        self._running = True
        logger.info("Audio stream manager started")
    
    async def stop(self):
        """停止音频流管理器"""
        self._running = False
        
        # 关闭所有连接
        for client_id, ws in list(self._connections.items()):
            try:
                await ws.close()
            except Exception:
                pass
        
        self._connections.clear()
        logger.info("Audio stream manager stopped")
    
    async def handle_connection(self, websocket: WebSocket, client_id: str = "default"):
        """处理WebSocket连接"""
        await websocket.accept()
        
        if client_id in self._connections:
            # 关闭旧连接
            try:
                await self._connections[client_id].close()
            except Exception:
                pass
        
        self._connections[client_id] = websocket
        logger.info("Audio stream client connected: %s", client_id)
        
        try:
            while self._running:
                # 接收音频数据
                try:
                    data = await websocket.receive_bytes()
                    await self._process_audio(data)
                except WebSocketDisconnect:
                    break
                except Exception as e:
                    logger.error("Error receiving audio: %s", e)
                    break
        finally:
            if client_id in self._connections:
                del self._connections[client_id]
            logger.info("Audio stream client disconnected: %s", client_id)
    
    async def _process_audio(self, audio_data: bytes):
        """处理接收到的音频数据"""
        if self._audio_handler:
            try:
                await self._audio_handler(audio_data)
            except Exception as e:
                logger.error("Audio handler error: %s", e)
    
    async def send_audio(self, client_id: str, audio_data: bytes):
        """向客户端发送音频数据"""
        if client_id in self._connections:
            try:
                await self._connections[client_id].send_bytes(audio_data)
            except Exception as e:
                logger.error("Error sending audio to %s: %s", client_id, e)
    
    async def broadcast_audio(self, audio_data: bytes):
        """向所有客户端广播音频"""
        for client_id in list(self._connections.keys()):
            await self.send_audio(client_id, audio_data)
    
    @property
    def is_running(self) -> bool:
        return self._running
    
    @property
    def connected_clients(self) -> Set[str]:
        return set(self._connections.keys())


# 全局单例
_manager: Optional[AudioStreamManager] = None


def get_audio_stream_manager() -> AudioStreamManager:
    """获取全局音频流管理器"""
    global _manager
    if _manager is None:
        _manager = AudioStreamManager.instance()
    return _manager