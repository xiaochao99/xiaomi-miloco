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

from miloco_server.utils.check_img_motion import CheckImgMotionByDHash

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
        motion_threshold: int = 5,
        motion_check_interval: float = 1.0,
    ):
        self.segment_duration = segment_duration
        self.pre_buffer_seconds = pre_buffer_seconds
        self.retention_days = retention_days
        self.motion_buffer_seconds = motion_buffer_seconds
        self.person_buffer_seconds = person_buffer_seconds
        self.motion_threshold = motion_threshold
        self.motion_check_interval = motion_check_interval


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
        
        # Motion detection state per camera (for MOTION mode)
        self._motion_states: Dict[str, dict] = {}
        
        # State
        self._running = False
        self._cleanup_task: Optional[asyncio.Task] = None
        self._trigger_monitor_task: Optional[asyncio.Task] = None
        
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
        # Start trigger monitor for MOTION/PERSON modes
        self._trigger_monitor_task = asyncio.create_task(self._trigger_monitor_loop())
        
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
        
        # Cancel trigger monitor task
        if self._trigger_monitor_task:
            self._trigger_monitor_task.cancel()
            try:
                await self._trigger_monitor_task
            except asyncio.CancelledError:
                pass
        
        # Stop all recorders
        for key, recorder in self._recorders.items():
            await recorder.stop_recording()
        
        self._recorders.clear()
        self._camera_handlers.clear()
        self._motion_states.clear()
        
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
        
        # Clean up motion state
        self._motion_states.pop(camera_id, None)
        
        # Unregister JPEG stream if handler supports it
        handler = self._camera_handlers.get(camera_id)
        if handler and hasattr(handler, 'unregister_jpeg_stream'):
            try:
                await handler.unregister_jpeg_stream(channel=0)
            except Exception:
                pass
        
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
            recording_mode=config.mode.value if config.mode else "continuous",
        )
        
        key = (camera_id, 0)
        self._recorders[key] = recorder
        
        # Register raw stream callback (needed for all modes to fill pre-buffer)
        if hasattr(handler, 'register_raw_stream'):
            callback = recorder.on_raw_frame
            await handler.register_raw_stream(callback, channel=0)
            logger.info("[RecordEngine] Registered raw stream callback for camera %s", camera_id)
        
        if not config.enabled:
            return
        
        if config.mode == RecordingMode.CONTINUOUS:
            # Continuous mode: start recording immediately
            await recorder.start_recording()
            logger.info("[RecordEngine] Started continuous recording for camera %s", camera_id)
        
        elif config.mode == RecordingMode.MOTION:
            # Motion mode: register JPEG stream for motion detection, wait for trigger
            if hasattr(handler, 'register_jpeg_stream'):
                jpeg_callback = self._create_motion_jpeg_callback(camera_id)
                await handler.register_jpeg_stream(jpeg_callback, channel=0)
                logger.info("[RecordEngine] Motion mode: registered JPEG stream for camera %s", camera_id)
            else:
                logger.warning("[RecordEngine] Motion mode requires JPEG stream support, handler missing register_jpeg_stream for camera %s", camera_id)
            
            self._motion_states[camera_id] = {
                "mode": "motion",
                "detected": False,
                "last_activity_time": 0,
            }
            logger.info("[RecordEngine] Motion mode setup for camera %s, waiting for motion detection", camera_id)
        
        elif config.mode == RecordingMode.PERSON:
            # Person mode: wait for detection service callback
            self._motion_states[camera_id] = {
                "mode": "person",
                "detected": False,
                "last_activity_time": 0,
            }
            logger.info("[RecordEngine] Person mode setup for camera %s, waiting for person detection", camera_id)
    
    async def on_person_detected(self, camera_id: str):
        """Callback when person is detected (for PERSON mode)."""
        config = self._config_dao.get_by_camera_id(camera_id)
        if not config or config.mode != RecordingMode.PERSON:
            return
        
        state = self._motion_states.get(camera_id)
        if state:
            state["last_activity_time"] = time.time()
            if not state.get("detected"):
                state["detected"] = True
                logger.info("[RecordEngine] Person detected for camera %s", camera_id)
        
        key = (camera_id, 0)
        recorder = self._recorders.get(key)
        if recorder and not recorder.active:
            await recorder.start_recording()
            logger.info("[RecordEngine] Person detected, started recording for camera %s", camera_id)
    
    async def on_person_lost(self, camera_id: str):
        """Callback when person is no longer detected (for PERSON mode)."""
        config = self._config_dao.get_by_camera_id(camera_id)
        if not config or config.mode != RecordingMode.PERSON:
            return
        
        state = self._motion_states.get(camera_id)
        if state and state.get("detected"):
            state["detected"] = False
            logger.info("[RecordEngine] Person lost for camera %s, will end recording after buffer time", camera_id)
    
    async def on_motion_detected(self, camera_id: str):
        """Callback when motion is detected (for MOTION mode)."""
        config = self._config_dao.get_by_camera_id(camera_id)
        if not config or config.mode != RecordingMode.MOTION:
            return
        
        state = self._motion_states.get(camera_id)
        if state:
            state["last_activity_time"] = time.time()
            if not state.get("detected"):
                state["detected"] = True
                logger.info("[RecordEngine] Motion detected for camera %s", camera_id)
        
        key = (camera_id, 0)
        recorder = self._recorders.get(key)
        if recorder and not recorder.active:
            await recorder.start_recording()
            logger.info("[RecordEngine] Motion detected, started recording for camera %s", camera_id)
    
    async def on_motion_lost(self, camera_id: str):
        """Callback when motion is no longer detected (for MOTION mode)."""
        config = self._config_dao.get_by_camera_id(camera_id)
        if not config or config.mode != RecordingMode.MOTION:
            return
        
        state = self._motion_states.get(camera_id)
        if state and state.get("detected"):
            state["detected"] = False
            logger.info("[RecordEngine] Motion lost for camera %s, will end recording after buffer time", camera_id)
    
    def _create_motion_jpeg_callback(self, camera_id: str) -> Callable:
        """Create a JPEG callback for motion detection using DHash.
        
        Only signals motion_detected when frames differ. Motion stop is handled
        by _trigger_monitor_loop based on last_activity_time timeout, not by
        individual unchanged frames, to avoid rapid start/stop toggling.
        
        Features:
        - Configurable check interval to reduce CPU usage
        - Logs DHash distance for debugging
        - Cooldown period to prevent rapid start/stop
        - Configurable motion threshold for sensitivity adjustment
        """
        last_check_time = 0.0
        last_frame: Optional[bytes] = None
        last_motion_time = 0.0  # For cooldown
        COOLDOWN_SECONDS = 2.0  # Minimum time between motion start events
        motion_threshold = self._config.motion_threshold
        check_interval = self._config.motion_check_interval
        
        async def on_jpeg_frame(did: str, data: bytes, ts: int, channel: int):
            nonlocal last_check_time, last_frame, last_motion_time
            
            state = self._motion_states.get(camera_id)
            if not state or state.get("mode") != "motion":
                return
            
            now = time.time()
            if now - last_check_time < check_interval:
                return
            last_check_time = now
            
            prev_frame = last_frame
            last_frame = data
            
            if prev_frame:
                try:
                    changed, distance = CheckImgMotionByDHash.is_image_changed(prev_frame, data, threshold=motion_threshold)
                    
                    # Log distance for debugging
                    if distance >= 0:
                        logger.debug("[RecordEngine] Motion check for %s: distance=%d, threshold=%d, changed=%s",
                                   camera_id, distance, motion_threshold, changed)
                    
                    if changed:
                        # Apply cooldown to prevent rapid start/stop
                        if now - last_motion_time < COOLDOWN_SECONDS:
                            logger.debug("[RecordEngine] Motion detected but in cooldown for %s", camera_id)
                            return
                        
                        last_motion_time = now
                        await self.on_motion_detected(camera_id)
                    # Do NOT call on_motion_lost here; let _trigger_monitor_loop
                    # decide when to stop based on last_activity_time timeout.
                except Exception as e:
                    logger.debug("[RecordEngine] Motion check error for %s: %s", camera_id, e)
        
        return on_jpeg_frame
    
    async def _trigger_monitor_loop(self):
        """Monitor MOTION/PERSON mode recorders and stop them after buffer timeout.
        
        Logic: Stop recording when last_activity_time exceeds buffer_seconds.
        The 'detected' flag is used for logging, not for controlling stop logic.
        
        Buffer seconds are read from each camera's config in the database,
        not from the global engine config.
        """
        logger.info("[RecordEngine] Trigger monitor loop started (using per-camera config from DB)")
        
        while self._running:
            try:
                await asyncio.sleep(1)
                now = time.time()
                
                for camera_id, state in list(self._motion_states.items()):
                    key = (camera_id, 0)
                    recorder = self._recorders.get(key)
                    if not recorder or not recorder.active:
                        continue
                    
                    # Get buffer seconds from camera's config in database
                    camera_config = self._config_dao.get_by_camera_id(camera_id)
                    if camera_config:
                        buffer_seconds = (
                            camera_config.motion_buffer_seconds
                            if state.get("mode") == "motion"
                            else camera_config.person_buffer_seconds
                        )
                    else:
                        # Fallback to global config
                        buffer_seconds = (
                            self._config.motion_buffer_seconds
                            if state.get("mode") == "motion"
                            else self._config.person_buffer_seconds
                        )
                    
                    last_activity = state.get("last_activity_time", 0)
                    elapsed = now - last_activity
                    if elapsed > buffer_seconds:
                        # Log recording stats before stopping
                        stats = recorder.get_stats()
                        logger.info("[RecordEngine] %s ended for camera %s after %.1fs buffer "
                                   "(recorded %d frames, %d bytes, %d segments)",
                                   state.get("mode", "trigger").capitalize(), camera_id,
                                   elapsed, stats.get("total_frames", 0),
                                   stats.get("total_bytes", 0), stats.get("total_segments", 0))
                        await recorder.stop_recording()
                        state["detected"] = False
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("[RecordEngine] Error in trigger monitor loop: %s", e)
    
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
        
        # Clean up motion state
        self._motion_states.pop(camera_id, None)
        
        return self._config_dao.delete(camera_id)
    
    def get_config(self, camera_id: str) -> Optional[RecordingConfig]:
        """Get recording config for a camera."""
        return self._config_dao.get_by_camera_id(camera_id)
    
    def get_all_configs(self) -> List[RecordingConfig]:
        """Get all recording configs."""
        return self._config_dao.get_all()
    
    def get_status(self, camera_id: str) -> Optional[RecordingStatus]:
        """Get recording status for a camera (filesystem-based)."""
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
        
        # Count today's segments from filesystem
        today_str = datetime.now().strftime("%Y-%m-%d")
        today_dir = self._storage.base_path / camera_id / today_str
        segments_today = 0
        try:
            segments_today = len(list(today_dir.glob("*.ts")))
        except Exception:
            pass
        
        # Get storage stats from filesystem
        storage_mb = 0.0
        try:
            total_size = 0
            camera_dir = self._storage.base_path / camera_id
            if camera_dir.exists():
                for f in camera_dir.rglob("*.ts"):
                    total_size += f.stat().st_size
            storage_mb = round(total_size / (1024 * 1024), 2)
        except Exception:
            pass
        
        return RecordingStatus(
            camera_id=camera_id,
            camera_name=camera_name,
            recording_enabled=config.enabled,
            recording_active=recorder.active if recorder else False,
            mode=config.mode,
            current_segment_start=recorder._segment_start if recorder else None,
            segments_today=segments_today,
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
        """Get overall storage statistics from filesystem."""
        usage = self._storage.get_storage_usage()
        per_camera = self._storage.get_per_camera_stats()
        
        return RecordingStorageStats(
            total_size_bytes=usage["total_size_bytes"],
            total_size_mb=usage["total_size_mb"],
            total_segments=usage["total_files"],
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
    logger.info("[RecordEngine] Loading config from RECORDING_CONFIG: %s", RECORDING_CONFIG)
    
    config = RecordEngineConfig(
        segment_duration=int(RECORDING_CONFIG.get("segment_duration", 300)),
        pre_buffer_seconds=float(RECORDING_CONFIG.get("pre_buffer_seconds", 5.0)),
        retention_days=int(RECORDING_CONFIG.get("retention_days", 7)),
        motion_buffer_seconds=float(RECORDING_CONFIG.get("motion_buffer_seconds", 5.0)),
        person_buffer_seconds=float(RECORDING_CONFIG.get("person_buffer_seconds", 5.0)),
        motion_threshold=int(RECORDING_CONFIG.get("motion_threshold", 5)),
        motion_check_interval=float(RECORDING_CONFIG.get("motion_check_interval", 1.0)),
    )
    
    logger.info("[RecordEngine] Config loaded: motion_buffer=%.1fs, person_buffer=%.1fs, threshold=%d",
               config.motion_buffer_seconds, config.person_buffer_seconds, config.motion_threshold)
    
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
