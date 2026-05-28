# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
RecordEngine - Core NVR recording engine.

Manages multi-channel concurrent recording with:
- Zero-copy muxing via PyAV
- Streaming write to MPEG-TS format
- Pre-recording buffer for trigger modes
- Keyframe-aligned segment rotation
- Automatic cleanup and retention
"""

import asyncio
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Coroutine, Dict, List, Optional, Set, Tuple

from miloco_server.config.normal_config import RECORDING_CONFIG, STORAGE_DIR
from miloco_server.dao.recording_dao import RecordingConfigDAO, RecordingSegmentDAO
from miloco_server.schema.recording_schema import (
    RecordingConfig,
    RecordingMode,
    RecordingSegment,
    RecordingStatus,
    RecordingStorageStats,
    TimePeriod,
)

from .channel import ChannelRecorder
from .storage import StorageManager

logger = logging.getLogger(__name__)


class RecordEngineConfig:
    """Configuration for RecordEngine."""
    
    def __init__(
        self,
        segment_duration: int = 300,
        pre_buffer_seconds: float = 5.0,
        retention_days: int = 7,
        motion_buffer_seconds: float = 5.0,
        person_buffer_seconds: float = 5.0,
    ):
        self.segment_duration = segment_duration
        self.pre_buffer_seconds = pre_buffer_seconds
        self.retention_days = retention_days
        self.motion_buffer_seconds = motion_buffer_seconds
        self.person_buffer_seconds = person_buffer_seconds


class RecordEngine:
    """Core NVR recording engine managing multi-channel concurrent recording."""
    
    def __init__(
        self,
        config: RecordEngineConfig,
        config_dao: RecordingConfigDAO,
        segment_dao: RecordingSegmentDAO,
        storage: StorageManager,
    ):
        self._config = config
        self._config_dao = config_dao
        self._segment_dao = segment_dao
        self._storage = storage
        
        # Channel recorders: key = (camera_id, channel)
        self._recorders: Dict[Tuple[str, int], ChannelRecorder] = {}
        
        # Camera handlers for raw stream registration
        self._camera_handlers: Dict[str, object] = {}
        
        # State
        self._running = False
        self._cleanup_task: Optional[asyncio.Task] = None
        
        # Statistics
        self._start_time: Optional[float] = None
        
        logger.info("[RecordEngine] Initialized")
    
    async def initialize(self):
        """Initialize the recording engine."""
        self._running = True
        self._start_time = time.time()
        
        # Restore enabled cameras from database
        enabled_configs = self._config_dao.get_enabled()
        logger.info("[RecordEngine] Initializing with %d enabled recording configs", len(enabled_configs))
        
        for config in enabled_configs:
            await self._setup_camera_recording(config)
        
        # Start cleanup task
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        
        logger.info("[RecordEngine] Initialization complete")
    
    async def shutdown(self):
        """Shutdown the recording engine."""
        logger.info("[RecordEngine] Shutting down...")
        
        self._running = False
        
        # Cancel cleanup task
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        # Stop all recorders
        for key, recorder in self._recorders.items():
            await recorder.stop_recording()
        
        self._recorders.clear()
        self._camera_handlers.clear()
        
        logger.info("[RecordEngine] Shutdown complete")
    
    async def register_camera_handler(self, camera_id: str, handler: object):
        """Register a camera handler for recording."""
        logger.info("[RecordEngine] Registering camera handler for %s", camera_id)
        
        self._camera_handlers[camera_id] = handler
        
        # Check if we have an enabled config for this camera
        config = self._config_dao.get_by_camera_id(camera_id)
        if config and config.enabled:
            await self._setup_camera_recording(config, handler)
    
    async def unregister_camera_handler(self, camera_id: str):
        """Unregister a camera handler."""
        logger.info("[RecordEngine] Unregistering camera handler for %s", camera_id)
        
        # Stop all recorders for this camera
        keys_to_remove = [k for k in self._recorders.keys() if k[0] == camera_id]
        for key in keys_to_remove:
            await self._recorders[key].stop_recording()
            del self._recorders[key]
        
        self._camera_handlers.pop(camera_id, None)
    
    async def _setup_camera_recording(self, config: RecordingConfig, handler=None):
        """Set up recording for a camera based on its config."""
        camera_id = config.camera_id
        
        if not handler:
            handler = self._camera_handlers.get(camera_id)
        
        if not handler:
            logger.warning("[RecordEngine] No handler available for camera %s", camera_id)
            return
        
        # Create recorder for channel 0 (main channel)
        recorder = ChannelRecorder(
            camera_id=camera_id,
            channel=0,
            segment_duration=config.segment_duration or self._config.segment_duration,
            pre_buffer_seconds=self._config.pre_buffer_seconds,
            output_dir=self._storage.base_path,
        )
        
        key = (camera_id, 0)
        self._recorders[key] = recorder
        
        # Register raw stream callback
        if hasattr(handler, 'register_raw_stream'):
            callback = recorder.on_raw_frame
            await handler.register_raw_stream(callback, channel=0)
            logger.info("[RecordEngine] Registered raw stream callback for camera %s", camera_id)
        
        # Start recording if enabled
        if config.enabled:
            await recorder.start_recording()
            logger.info("[RecordEngine] Started recording for camera %s", camera_id)
    
    async def on_person_detected(self, camera_id: str):
        """Callback when person is detected (for PERSON mode)."""
        config = self._config_dao.get_by_camera_id(camera_id)
        if not config or config.mode != RecordingMode.PERSON:
            return
        
        key = (camera_id, 0)
        recorder = self._recorders.get(key)
        if recorder and not recorder.active:
            await recorder.start_recording()
            logger.info("[RecordEngine] Person detected, started recording for camera %s", camera_id)
    
    async def on_motion_detected(self, camera_id: str):
        """Callback when motion is detected (for MOTION mode)."""
        config = self._config_dao.get_by_camera_id(camera_id)
        if not config or config.mode != RecordingMode.MOTION:
            return
        
        key = (camera_id, 0)
        recorder = self._recorders.get(key)
        if recorder and not recorder.active:
            await recorder.start_recording()
            logger.info("[RecordEngine] Motion detected, started recording for camera %s", camera_id)
    
    async def update_config(self, config: RecordingConfig) -> bool:
        """Update recording configuration for a camera."""
        success = self._config_dao.upsert(config)
        if not success:
            logger.error("[RecordEngine] Failed to upsert config for camera %s", config.camera_id)
            return False
        
        camera_id = config.camera_id
        key = (camera_id, 0)
        
        # Stop existing recorder
        if key in self._recorders:
            await self._recorders[key].stop_recording()
            del self._recorders[key]
        
        # Set up new recording if enabled
        if config.enabled:
            await self._setup_camera_recording(config)
        
        return True
    
    async def delete_config(self, camera_id: str) -> bool:
        """Delete recording config and stop recording."""
        # Stop recorder
        key = (camera_id, 0)
        if key in self._recorders:
            await self._recorders[key].stop_recording()
            del self._recorders[key]
        
        return self._config_dao.delete(camera_id)
    
    def get_config(self, camera_id: str) -> Optional[RecordingConfig]:
        """Get recording config for a camera."""
        return self._config_dao.get_by_camera_id(camera_id)
    
    def get_all_configs(self) -> List[RecordingConfig]:
        """Get all recording configs."""
        return self._config_dao.get_all()
    
    def get_status(self, camera_id: str) -> Optional[RecordingStatus]:
        """Get recording status for a camera."""
        config = self._config_dao.get_by_camera_id(camera_id)
        if not config:
            return None
        
        key = (camera_id, 0)
        recorder = self._recorders.get(key)
        
        # Get camera name
        camera_name = camera_id
        handler = self._camera_handlers.get(camera_id)
        if handler and hasattr(handler, 'camera_info'):
            ci = handler.camera_info
            if hasattr(ci, 'name'):
                camera_name = ci.name or camera_id
        
        # Get today's segments
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        segments_today, _ = self._segment_dao.query(
            camera_id=camera_id,
            start_time=today_start,
            page_size=1000,
        )
        
        # Get storage stats
        stats = self._segment_dao.get_storage_stats(camera_id)
        storage_mb = round(stats.get("total_size_bytes", 0) / (1024 * 1024), 2)
        
        return RecordingStatus(
            camera_id=camera_id,
            camera_name=camera_name,
            recording_enabled=config.enabled,
            recording_active=recorder.active if recorder else False,
            mode=config.mode,
            current_segment_start=recorder._segment_start if recorder else None,
            segments_today=len(segments_today),
            storage_used_mb=storage_mb,
        )
    
    def get_all_statuses(self) -> List[RecordingStatus]:
        """Get recording status for all cameras."""
        configs = self._config_dao.get_all()
        statuses = []
        for config in configs:
            status = self.get_status(config.camera_id)
            if status:
                statuses.append(status)
        return statuses
    
    def get_storage_stats(self) -> RecordingStorageStats:
        """Get overall storage statistics."""
        db_stats = self._segment_dao.get_storage_stats()
        per_camera = self._segment_dao.get_per_camera_stats()
        total_bytes = db_stats.get("total_size_bytes", 0)
        
        return RecordingStorageStats(
            total_size_bytes=total_bytes,
            total_size_mb=round(total_bytes / (1024 * 1024), 2),
            total_segments=db_stats.get("total_segments", 0),
            per_camera=per_camera,
        )
    
    def get_engine_stats(self) -> dict:
        """Get engine statistics."""
        uptime = time.time() - self._start_time if self._start_time else 0
        
        return {
            "running": self._running,
            "uptime_seconds": uptime,
            "active_recorders": sum(1 for r in self._recorders.values() if r.active),
            "total_recorders": len(self._recorders),
            "camera_handlers": len(self._camera_handlers),
        }
    
    async def manual_cleanup(self) -> int:
        """Manually trigger cleanup of expired recordings."""
        return await self._storage.cleanup_expired()
    
    async def _cleanup_loop(self):
        """Periodically clean up expired recordings."""
        while self._running:
            try:
                await asyncio.sleep(3600)  # Check every hour
                await self._storage.cleanup_expired()
                await self._storage.cleanup_empty_dirs()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("[RecordEngine] Error in cleanup loop: %s", e)


# Global engine instance
_record_engine: Optional[RecordEngine] = None


def get_record_engine() -> RecordEngine:
    """Get the global RecordEngine instance."""
    global _record_engine
    if _record_engine is None:
        raise RuntimeError("RecordEngine not initialized. Call init_record_engine() first.")
    return _record_engine


async def init_record_engine() -> RecordEngine:
    """Initialize and return the RecordEngine."""
    global _record_engine
    
    # Create configuration
    config = RecordEngineConfig(
        segment_duration=int(RECORDING_CONFIG.get("segment_duration", 300)),
        pre_buffer_seconds=float(RECORDING_CONFIG.get("pre_buffer_seconds", 5.0)),
        retention_days=int(RECORDING_CONFIG.get("retention_days", 7)),
        motion_buffer_seconds=float(RECORDING_CONFIG.get("motion_buffer_seconds", 5.0)),
        person_buffer_seconds=float(RECORDING_CONFIG.get("person_buffer_seconds", 5.0)),
    )
    
    # Create storage manager
    storage_path = STORAGE_DIR / "recordings"
    storage = StorageManager(
        base_path=storage_path,
        retention_days=config.retention_days,
    )
    
    # Create DAOs
    config_dao = RecordingConfigDAO()
    segment_dao = RecordingSegmentDAO()
    
    # Create engine
    _record_engine = RecordEngine(
        config=config,
        config_dao=config_dao,
        segment_dao=segment_dao,
        storage=storage,
    )
    
    # Initialize
    await _record_engine.initialize()
    
    logger.info("[RecordEngine] Global instance initialized")
    return _record_engine
