# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Recording service module.
Core service for camera recording management, supporting continuous, motion-based, and person-based recording.
Refactored to use time-based pre-recording buffer for all trigger-based modes.
"""

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set, Tuple

from miloco_server.dao.recording_dao import RecordingConfigDAO, RecordingSegmentDAO
from miloco_server.schema.recording_schema import (
    RecordingConfig,
    RecordingMode,
    RecordingSegment,
    RecordingStatus,
    RecordingStorageStats,
)
from miloco_server.service.recording_storage import RecordingStorageManager, recording_storage
from miloco_server.utils.carmera_vision_handler import BaseCameraVisionHandler
from miloco_server.utils.check_img_motion import CheckImgMotionByDHash

logger = logging.getLogger(__name__)

# H.265 NAL type constants
H265_NAL_TRAIL_N = 0
H265_NAL_TRAIL_R = 1
H265_NAL_IDR_W_RADL = 19
H265_NAL_IDR_N_LP = 20
H265_NAL_CRA = 21
H265_NAL_VPS = 32
H265_NAL_SPS = 33
H265_NAL_PPS = 34


class PreRecordingBuffer:
    """Time-based pre-recording buffer for storing recent video frames.
    
    Maintains a rolling buffer of video data for the specified duration.
    When recording is triggered, this buffer provides the pre-trigger footage.
    Ensures buffer data starts with a keyframe to avoid garbled playback.
    """
    
    def __init__(self, duration_seconds: float = 5.0):
        self.duration_seconds = duration_seconds
        # List of (timestamp, data_bytes, is_keyframe) tuples
        self._frames: List[Tuple[float, bytes, bool]] = []
        self._total_bytes = 0
        
    def add_frame(self, timestamp: float, data: bytes, is_keyframe: bool):
        """Add a frame to the buffer."""
        self._frames.append((timestamp, data, is_keyframe))
        self._total_bytes += len(data)
        
        # Remove old frames beyond the time window
        cutoff_time = timestamp - self.duration_seconds
        while self._frames and self._frames[0][0] < cutoff_time:
            _, old_data, _ = self._frames.pop(0)
            self._total_bytes -= len(old_data)
    
    def get_buffer_data_from_keyframe(self) -> bytearray:
        """Get buffer data starting from the first keyframe.
        
        This ensures the recording starts with a decodable frame.
        If no keyframe in buffer, return all data (best effort).
        """
        if not self._frames:
            return bytearray()
        
        # Find first keyframe index
        start_index = 0
        for i, (_, _, is_keyframe) in enumerate(self._frames):
            if is_keyframe:
                start_index = i
                break
        
        # Return data from that index onwards
        result = bytearray()
        for i in range(start_index, len(self._frames)):
            result.extend(self._frames[i][1])
        
        return result
    
    def get_buffer_data(self) -> bytearray:
        """Get all data in the buffer as a bytearray."""
        result = bytearray()
        for _, data, _ in self._frames:
            result.extend(data)
        return result
    
    def clear(self):
        """Clear the buffer."""
        self._frames.clear()
        self._total_bytes = 0
    
    def is_empty(self) -> bool:
        """Check if buffer is empty."""
        return len(self._frames) == 0
    
    def get_duration(self) -> float:
        """Get the actual duration of buffered data."""
        if len(self._frames) < 2:
            return 0.0
        return self._frames[-1][0] - self._frames[0][0]


class CameraRecordingState:
    """Runtime state for a single camera's recording engine."""

    def __init__(self, camera_id: str, config: RecordingConfig):
        self.camera_id = camera_id
        self.config = config
        self.active: bool = False
        
        # Current segment info
        self.current_segment_id: Optional[str] = None
        self.current_segment_start: Optional[datetime] = None
        self.frame_buffer: bytearray = bytearray()
        
        # H.265 header tracking
        self.vps_data: Optional[bytes] = None
        self.sps_data: Optional[bytes] = None
        self.pps_data: Optional[bytes] = None
        
        # Segment timing
        self.segment_start_time: Optional[float] = None
        self.last_rotate_time: Optional[float] = None
        
        # Pre-recording buffer (time-based, for MOTION and PERSON modes)
        pre_buffer_seconds = 5.0  # Default 5 seconds pre-recording
        if config.mode == RecordingMode.MOTION:
            pre_buffer_seconds = 5.0  # Can be configured per mode later
        elif config.mode == RecordingMode.PERSON:
            pre_buffer_seconds = 5.0
        self.pre_buffer = PreRecordingBuffer(duration_seconds=pre_buffer_seconds)
        
        # Motion detection (for MOTION mode)
        self.last_frame_jpeg: Optional[bytes] = None
        self.motion_detected: bool = False
        self.motion_start_time: Optional[float] = None
        self.last_activity_time: float = 0.0
        
        # Person detection (for PERSON mode)
        self.person_detected: bool = False
        self.person_start_time: Optional[float] = None
        
        # Frame timing for FPS calculation
        self.frame_timestamps: list = []
        self.estimated_fps: float = 0.0
        
        # Recording callback registration IDs
        self.raw_reg_id: Optional[int] = None
        self.jpeg_reg_id: Optional[int] = None
        self.camera_handler: Optional[BaseCameraVisionHandler] = None
        
        # Segment awaiting keyframe flag (to avoid garbled frames)
        self.segment_awaiting_keyframe: bool = False


class RecordingService:
    """Core recording service managing recording lifecycle for all cameras."""

    def __init__(
        self,
        recording_config_dao: RecordingConfigDAO,
        recording_segment_dao: RecordingSegmentDAO,
        storage_manager: RecordingStorageManager,
    ):
        self._config_dao = recording_config_dao
        self._segment_dao = recording_segment_dao
        self._storage = storage_manager
        self._camera_states: Dict[str, CameraRecordingState] = {}
        self._camera_handlers: Dict[str, BaseCameraVisionHandler] = {}
        self._running = False
        self._cleanup_task: Optional[asyncio.Task] = None
        
        # Global settings (can be overridden by config)
        self._segment_duration: int = 300
        self._motion_buffer_seconds: int = 5
        self._person_buffer_seconds: int = 5
        self._motion_check_interval: float = 1.0
        self._motion_threshold: int = 5

    def configure(
        self,
        segment_duration: int = 300,
        motion_buffer_seconds: int = 5,
        person_buffer_seconds: int = 5,
        motion_check_interval: float = 1.0,
        motion_threshold: int = 5,
    ):
        """Apply global recording settings from config."""
        self._segment_duration = segment_duration
        self._motion_buffer_seconds = motion_buffer_seconds
        self._person_buffer_seconds = person_buffer_seconds
        self._motion_check_interval = motion_check_interval
        self._motion_threshold = motion_threshold

    async def initialize(self):
        """Initialize recording service: restore enabled cameras, start cleanup task."""
        self._running = True
        enabled_configs = self._config_dao.get_enabled()
        logger.info("[Recording] Initializing with %d enabled recording configs", len(enabled_configs))
        for config in enabled_configs:
            state = CameraRecordingState(config.camera_id, config)
            self._camera_states[config.camera_id] = state
            handler = self._camera_handlers.get(config.camera_id)
            if handler:
                logger.info("[Recording] Handler already registered for camera %s, starting recording", config.camera_id)
                state.camera_handler = handler
                await self._start_camera_recording(config.camera_id)
        self._cleanup_task = asyncio.create_task(self._periodic_cleanup_loop())
        logger.info("[Recording] Service initialized")

    async def shutdown(self):
        """Shutdown recording service: stop all recordings, cancel cleanup task."""
        self._running = False
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        for camera_id in list(self._camera_states.keys()):
            await self._stop_camera_recording(camera_id)
        self._camera_states.clear()
        self._camera_handlers.clear()
        logger.info("[Recording] Service shutdown complete")

    async def register_camera_handler(self, camera_id: str, handler: BaseCameraVisionHandler):
        """Register a camera handler for recording. Called when camera becomes available."""
        logger.info("[Recording] Registering camera handler for %s", camera_id)
        self._camera_handlers[camera_id] = handler
        state = self._camera_states.get(camera_id)
        if state and state.config.enabled and not state.active:
            state.camera_handler = handler
            logger.info("[Recording] Starting recording for camera %s after handler registration", camera_id)
            await self._start_camera_recording(camera_id)

    async def unregister_camera_handler(self, camera_id: str):
        """Unregister a camera handler. Called when camera goes offline."""
        await self._stop_camera_recording(camera_id)
        self._camera_handlers.pop(camera_id, None)
        state = self._camera_states.get(camera_id)
        if state:
            state.camera_handler = None

    async def on_person_detected(self, camera_id: str):
        """Callback from DetectionService when a person is detected."""
        state = self._camera_states.get(camera_id)
        if not state or not state.active:
            return
        if state.config.mode != RecordingMode.PERSON:
            return
        
        now = time.time()
        state.last_activity_time = now
        state.person_detected = True
        state.person_start_time = now
        
        if not state.current_segment_id:
            logger.info("[Recording] Person detected for camera %s, starting recording with pre-buffer", camera_id)
            await self._begin_segment(camera_id, trigger="person_detected")

    async def on_person_lost(self, camera_id: str):
        """Callback when person is no longer detected."""
        state = self._camera_states.get(camera_id)
        if not state or not state.active:
            return
        if state.config.mode != RecordingMode.PERSON:
            return
        
        state.person_detected = False
        logger.info("[Recording] Person lost for camera %s, will end segment after buffer time", camera_id)

    async def on_motion_detected(self, camera_id: str):
        """Called when motion detection triggers (from JPEG callback)."""
        state = self._camera_states.get(camera_id)
        if not state or not state.active:
            return
        if state.config.mode != RecordingMode.MOTION:
            return
        
        now = time.time()
        state.last_activity_time = now
        state.motion_detected = True
        state.motion_start_time = now
        
        if not state.current_segment_id:
            logger.info("[Recording] Motion detected for camera %s, starting recording with pre-buffer", camera_id)
            await self._begin_segment(camera_id, trigger="motion_detected")

    async def update_config(self, config: RecordingConfig) -> bool:
        """Update recording configuration for a camera."""
        success = self._config_dao.upsert(config)
        if not success:
            logger.error("[Recording] Failed to upsert config for camera %s", config.camera_id)
            return False
        
        camera_id = config.camera_id
        old_state = self._camera_states.get(camera_id)
        was_active = old_state.active if old_state else False
        
        if was_active:
            await self._stop_camera_recording(camera_id)
        
        # Recreate state with new config
        state = CameraRecordingState(camera_id, config)
        self._camera_states[camera_id] = state
        
        if config.enabled:
            handler = self._camera_handlers.get(camera_id)
            if handler:
                state.camera_handler = handler
                await self._start_camera_recording(camera_id)
            else:
                logger.warning("[Recording] No handler available for camera %s, recording will start when handler registers", camera_id)
        
        return True

    async def delete_config(self, camera_id: str) -> bool:
        """Delete recording config and stop recording for a camera."""
        await self._stop_camera_recording(camera_id)
        self._camera_states.pop(camera_id, None)
        return self._config_dao.delete(camera_id)

    def get_config(self, camera_id: str) -> Optional[RecordingConfig]:
        """Get recording config for a camera."""
        return self._config_dao.get_by_camera_id(camera_id)

    def get_all_configs(self) -> List[RecordingConfig]:
        """Get all recording configs."""
        return self._config_dao.get_all()

    def get_status(self, camera_id: str) -> Optional[RecordingStatus]:
        """Get recording status for a camera."""
        state = self._camera_states.get(camera_id)
        config = self._config_dao.get_by_camera_id(camera_id)
        if not config:
            return None
        
        camera_name = camera_id
        handler = self._camera_handlers.get(camera_id)
        if handler and hasattr(handler, 'camera_info'):
            ci = handler.camera_info
            if hasattr(ci, 'name'):
                camera_name = ci.name or camera_id
        
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        segments_today, _ = self._segment_dao.query(
            camera_id=camera_id,
            start_time=today_start,
            page_size=1000,
        )
        stats = self._segment_dao.get_storage_stats(camera_id)
        storage_mb = round(stats.get("total_size_bytes", 0) / (1024 * 1024), 2)
        
        return RecordingStatus(
            camera_id=camera_id,
            camera_name=camera_name,
            recording_enabled=config.enabled,
            recording_active=state.active if state else False,
            mode=config.mode,
            current_segment_start=state.current_segment_start if state else None,
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

    async def manual_cleanup(self) -> int:
        """Manually trigger cleanup of expired recordings."""
        return await self._cleanup_expired_recordings()

    async def _start_camera_recording(self, camera_id: str):
        """Start recording for a camera based on its config."""
        state = self._camera_states.get(camera_id)
        if not state:
            logger.warning("[Recording] Cannot start recording for %s: no state", camera_id)
            return
        if not state.config.enabled:
            logger.warning("[Recording] Cannot start recording for %s: config not enabled", camera_id)
            return
        if state.active:
            logger.warning("[Recording] Cannot start recording for %s: already active", camera_id)
            return
        
        handler = state.camera_handler or self._camera_handlers.get(camera_id)
        if not handler:
            logger.warning("[Recording] No camera handler available for %s, will start when handler registers", camera_id)
            return
        
        try:
            mode = state.config.mode
            logger.info("[Recording] Starting %s recording for camera %s", mode.value, camera_id)
            
            if mode == RecordingMode.CONTINUOUS:
                # Continuous mode: register raw stream and start segment immediately
                callback = self._create_raw_video_callback(camera_id)
                reg_id = await handler.register_raw_stream(callback, channel=0)
                state.raw_reg_id = reg_id
                logger.info("[Recording] Continuous mode: registered raw stream callback, reg_id=%s", reg_id)
                await self._begin_segment(camera_id, trigger="continuous")
                
            elif mode == RecordingMode.MOTION:
                # Motion mode: register both raw stream (for recording) and JPEG stream (for motion detection)
                # Raw stream maintains pre-recording buffer
                raw_callback = self._create_raw_video_callback(camera_id)
                raw_reg_id = await handler.register_raw_stream(raw_callback, channel=0)
                state.raw_reg_id = raw_reg_id
                logger.info("[Recording] Motion mode: registered raw stream callback, reg_id=%s", raw_reg_id)
                
                # JPEG stream for motion detection
                jpeg_callback = self._create_jpeg_callback_for_motion(camera_id)
                jpeg_reg_id = await handler.register_jpeg_stream(jpeg_callback, channel=0)
                state.jpeg_reg_id = jpeg_reg_id
                logger.info("[Recording] Motion mode: registered JPEG stream callback for motion detection, reg_id=%s", jpeg_reg_id)
                
            elif mode == RecordingMode.PERSON:
                # Person mode: register raw stream (for recording and pre-buffer)
                raw_callback = self._create_raw_video_callback(camera_id)
                raw_reg_id = await handler.register_raw_stream(raw_callback, channel=0)
                state.raw_reg_id = raw_reg_id
                logger.info("[Recording] Person mode: registered raw stream callback, reg_id=%s", raw_reg_id)
                # Note: Person detection is handled by DetectionService calling on_person_detected()
                
            state.active = True
            state.last_activity_time = time.time()
            logger.info("[Recording] Started %s recording for camera %s", mode.value, camera_id)
            
        except Exception as e:
            logger.error("[Recording] Error starting recording for camera %s: %s", camera_id, e, exc_info=True)

    async def _stop_camera_recording(self, camera_id: str):
        """Stop recording for a camera."""
        state = self._camera_states.get(camera_id)
        if not state:
            return
        
        handler = state.camera_handler or self._camera_handlers.get(camera_id)
        if handler:
            if state.raw_reg_id is not None:
                try:
                    await handler.unregister_raw_stream(channel=0)
                except Exception:
                    pass
                state.raw_reg_id = None
            if state.jpeg_reg_id is not None:
                try:
                    await handler.unregister_jpeg_stream(channel=0)
                except Exception:
                    pass
                state.jpeg_reg_id = None
        
        if state.current_segment_id:
            await self._end_segment(camera_id)
        
        state.active = False
        logger.info("[Recording] Stopped recording for camera %s", camera_id)

    async def _begin_segment(self, camera_id: str, trigger: str = "continuous"):
        """Begin a new recording segment.
        
        For MOTION and PERSON modes: includes pre-buffer data (footage before trigger).
        For all modes: prepends VPS/SPS/PPS headers for independent decodability.
        """
        state = self._camera_states.get(camera_id)
        if not state:
            return
        
        segment_id = str(uuid.uuid4())
        now = datetime.now()
        state.current_segment_id = segment_id
        state.current_segment_start = now
        state.frame_buffer = bytearray()
        
        # For trigger-based modes, copy pre-buffer data from first keyframe
        pre_buffer_bytes = 0
        if trigger in ("motion_detected", "person_detected"):
            pre_buffer_data = state.pre_buffer.get_buffer_data_from_keyframe()
            if pre_buffer_data:
                state.frame_buffer.extend(pre_buffer_data)
                pre_buffer_bytes = len(pre_buffer_data)
                pre_buffer_duration = state.pre_buffer.get_duration()
                logger.info("[Recording] Segment %s: copied %d bytes from pre-buffer (%.1fs) starting from keyframe", 
                           segment_id, pre_buffer_bytes, pre_buffer_duration)
        
        # Prepend VPS/SPS/PPS headers if not already present
        self._ensure_headers(state)
        
        # Initialize segment timing
        current_time = time.time()
        state.segment_start_time = current_time
        state.last_rotate_time = current_time
        
        # Set awaiting keyframe flag if no pre-buffer data (continuous mode or rotation)
        state.segment_awaiting_keyframe = (pre_buffer_bytes == 0)
        
        logger.info("[Recording] Began segment %s for camera %s (trigger=%s, pre_buffer=%d bytes, headers=%s, total=%d bytes, awaiting_keyframe=%s)",
                   segment_id, camera_id, trigger, pre_buffer_bytes,
                   f"VPS={bool(state.vps_data)} SPS={bool(state.sps_data)} PPS={bool(state.pps_data)}",
                   len(state.frame_buffer), state.segment_awaiting_keyframe)

    async def _end_segment(self, camera_id: str):
        """End the current recording segment and save to storage."""
        logger.info("[Recording] _end_segment called for camera %s", camera_id)
        state = self._camera_states.get(camera_id)
        if not state:
            logger.warning("[Recording] _end_segment: no state for camera %s", camera_id)
            return
        if not state.current_segment_id:
            logger.warning("[Recording] _end_segment: no current_segment_id for camera %s", camera_id)
            return
        
        segment_id = state.current_segment_id
        start_time = state.current_segment_start
        end_time = datetime.now()
        duration = int((end_time - start_time).total_seconds()) if start_time else 0
        data_size = len(state.frame_buffer)
        
        logger.info("[Recording] Ending segment %s for camera %s, duration=%ds, data_size=%d bytes",
                   segment_id, camera_id, duration, data_size)
        
        if duration < 1:
            logger.warning("[Recording] Segment %s duration too short (%ds), discarding", segment_id, duration)
            state.current_segment_id = None
            state.current_segment_start = None
            state.frame_buffer = bytearray()
            return
        
        data = bytes(state.frame_buffer)
        state.current_segment_id = None
        state.current_segment_start = None
        state.frame_buffer = bytearray()
        
        if not data:
            logger.warning("[Recording] Segment %s has no data, discarding", segment_id)
            return
        
        # Calculate segment FPS from frame timestamps
        segment_fps = state.estimated_fps if state.estimated_fps > 0 else 15.0
        logger.info("[Recording] Saving segment %s to storage (estimated_fps=%.1f)", segment_id, segment_fps)
        
        try:
            relative_path, file_size = await self._storage.save_segment(
                camera_id=camera_id,
                segment_id=segment_id,
                data=data,
                date=start_time,
                fps=segment_fps,
            )
            segment = RecordingSegment(
                id=segment_id,
                camera_id=camera_id,
                start_time=start_time,
                end_time=end_time,
                duration_seconds=duration,
                file_path=relative_path,
                file_size_bytes=file_size,
                recording_mode=state.config.mode,
                trigger_event=None,
                created_at=start_time,
            )
            self._segment_dao.create(segment)
            logger.info("[Recording] Saved segment %s for camera %s (%d bytes, %ds)",
                       segment_id, camera_id, file_size, duration)
        except Exception as e:
            logger.error("[Recording] Error saving segment %s for camera %s: %s", segment_id, camera_id, e)

    def _ensure_headers(self, state: CameraRecordingState):
        """Ensure VPS/SPS/PPS headers are prepended to frame_buffer if missing.
        
        Headers must be at the BEGINNING of the frame buffer for proper decoding.
        """
        # Build header data in correct order: VPS -> SPS -> PPS
        header_data = bytearray()
        if state.vps_data:
            header_data.extend(state.vps_data)
        if state.sps_data:
            header_data.extend(state.sps_data)
        if state.pps_data:
            header_data.extend(state.pps_data)
        
        if not header_data:
            return
        
        # Check if frame_buffer already starts with headers
        if state.frame_buffer and state.frame_buffer[:len(header_data)] == header_data:
            return  # Headers already at beginning
        
        # Prepend headers to the beginning
        logger.info("[Recording] Prepending headers to segment (%d bytes)", len(header_data))
        state.frame_buffer = header_data + state.frame_buffer

    def _parse_h265_nal_type(self, data: bytes) -> int:
        """Parse H.265 NAL unit type from Annex B data."""
        if not data or len(data) < 5:
            return -1
        
        # Find NAL header after start code
        if data[0] == 0x00 and data[1] == 0x00:
            if data[2] == 0x00 and data[3] == 0x01:
                nal_byte = data[4]
            elif data[2] == 0x01:
                nal_byte = data[3]
            else:
                return -1
        else:
            return -1
        
        # H.265 NAL type is in bits [6:1] of the first NAL byte
        return (nal_byte >> 1) & 0x3F

    def _create_raw_video_callback(self, camera_id: str) -> Callable:
        """Create a raw video callback for recording.
        
        This callback:
        1. Tracks VPS/SPS/PPS headers
        2. Maintains pre-recording buffer (for MOTION and PERSON modes)
        3. Accumulates data for active segments
        4. Handles segment rotation at IDR/VPS boundaries
        """
        # NAL type statistics tracking
        nal_type_stats = {}
        
        async def on_raw_video(did: str, data: bytes, ts: int, seq: int, channel: int):
            state = self._camera_states.get(camera_id)
            if not state or not state.active:
                return
            
            # Check schedule
            if not self._is_in_schedule(state.config):
                if state.current_segment_id:
                    await self._end_segment(camera_id)
                return
            
            now = time.time()
            nal_type = self._parse_h265_nal_type(data)
            
            # Track NAL type statistics
            nal_type_stats[nal_type] = nal_type_stats.get(nal_type, 0) + 1
            
            # Track VPS/SPS/PPS headers
            if nal_type == H265_NAL_VPS:
                state.vps_data = data
                logger.debug("[Recording] Camera %s: captured VPS (%d bytes)", camera_id, len(data))
            elif nal_type == H265_NAL_SPS:
                state.sps_data = data
                logger.debug("[Recording] Camera %s: captured SPS (%d bytes)", camera_id, len(data))
            elif nal_type == H265_NAL_PPS:
                state.pps_data = data
                logger.debug("[Recording] Camera %s: captured PPS (%d bytes)", camera_id, len(data))
            
            is_idr = nal_type in (H265_NAL_IDR_W_RADL, H265_NAL_IDR_N_LP, H265_NAL_CRA)
            is_keyframe = is_idr or nal_type == H265_NAL_VPS
            
            # Update frame timestamps for FPS calculation
            state.frame_timestamps.append(now)
            if len(state.frame_timestamps) > 500:
                state.frame_timestamps = state.frame_timestamps[-500:]
            if len(state.frame_timestamps) >= 2:
                time_span = state.frame_timestamps[-1] - state.frame_timestamps[0]
                if time_span > 0:
                    state.estimated_fps = (len(state.frame_timestamps) - 1) / time_span
            
            # Always add frame to pre-recording buffer (for MOTION and PERSON modes)
            # This ensures we always have recent footage ready when trigger occurs
            # Pass is_keyframe to track keyframe positions for clean segment starts
            state.pre_buffer.add_frame(now, data, is_keyframe)
            
            # Handle active segment
            if state.current_segment_id:
                # Wait for keyframe at segment start to avoid garbled frames
                if state.segment_awaiting_keyframe:
                    if not is_keyframe:
                        return  # Skip non-keyframe data
                    state.segment_awaiting_keyframe = False
                    logger.info("[Recording] Camera %s: got keyframe (type=%d), beginning accumulation", 
                               camera_id, nal_type)
                
                # Add data to frame buffer
                state.frame_buffer.extend(data)
                
                # Check if we need to rotate segment
                segment_duration = state.config.segment_duration if state.config.segment_duration else self._segment_duration
                if state.last_rotate_time:
                    elapsed = now - state.last_rotate_time
                    
                    # Determine if we should rotate
                    # Use IDR if available, otherwise use VPS as boundary
                    has_idr_in_stream = any(t in nal_type_stats for t in (H265_NAL_IDR_W_RADL, H265_NAL_IDR_N_LP, H265_NAL_CRA))
                    should_rotate = elapsed >= segment_duration and (
                        is_idr or (not has_idr_in_stream and nal_type == H265_NAL_VPS)
                    )
                    
                    if should_rotate:
                        boundary = "IDR" if is_idr else "VPS"
                        logger.info("[Recording] Rotating segment for camera %s at %s after %.1fs", 
                                   camera_id, boundary, elapsed)
                        await self._end_segment(camera_id)
                        
                        # Start new segment with headers
                        await self._begin_segment(camera_id, trigger="rotation")
                        # Add current frame to new segment
                        state.frame_buffer.extend(data)
                        state.segment_awaiting_keyframe = False
                        state.last_rotate_time = now
            
            # For trigger-based modes, check if we should end segment
            if state.current_segment_id and state.config.mode in (RecordingMode.MOTION, RecordingMode.PERSON):
                buffer_seconds = self._motion_buffer_seconds if state.config.mode == RecordingMode.MOTION else self._person_buffer_seconds
                
                if state.config.mode == RecordingMode.MOTION and not state.motion_detected:
                    # Motion stopped, check if we should end segment
                    if now - state.last_activity_time > buffer_seconds:
                        logger.info("[Recording] Motion ended for camera %s, ending segment after %.1fs buffer", 
                                   camera_id, buffer_seconds)
                        await self._end_segment(camera_id)
                
                elif state.config.mode == RecordingMode.PERSON and not state.person_detected:
                    # Person left, check if we should end segment
                    if now - state.last_activity_time > buffer_seconds:
                        logger.info("[Recording] Person left for camera %s, ending segment after %.1fs buffer", 
                                   camera_id, buffer_seconds)
                        await self._end_segment(camera_id)
        
        return on_raw_video

    def _create_jpeg_callback_for_motion(self, camera_id: str) -> Callable:
        """Create a JPEG callback for motion detection.
        
        This callback detects motion by comparing consecutive JPEG frames.
        When motion is detected, it signals to start recording (if not already started).
        """
        last_check_time = [0.0]
        
        async def on_jpeg_frame(did: str, data: bytes, ts: int, channel: int):
            state = self._camera_states.get(camera_id)
            if not state or not state.active:
                return
            
            now = time.time()
            if now - last_check_time[0] < self._motion_check_interval:
                return
            last_check_time[0] = now
            
            prev_frame = state.last_frame_jpeg
            state.last_frame_jpeg = data
            
            if prev_frame:
                try:
                    changed, distance = CheckImgMotionByDHash.is_image_changed(prev_frame, data)
                    if changed:
                        await self.on_motion_detected(camera_id)
                except Exception as e:
                    logger.debug("[Recording] Motion check error for %s: %s", camera_id, e)
        
        return on_jpeg_frame

    def _is_in_schedule(self, config: RecordingConfig) -> bool:
        """Check if current time is within the configured schedule."""
        if not config.schedule_periods:
            return True
        
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        
        for period in config.schedule_periods:
            if period.start_time <= period.end_time:
                if period.start_time <= current_time <= period.end_time:
                    return True
            else:
                if current_time >= period.start_time or current_time <= period.end_time:
                    return True
        
        return False

    async def _periodic_cleanup_loop(self):
        """Periodically clean up expired recordings."""
        while self._running:
            try:
                await asyncio.sleep(3600)  # Check every hour
                await self._cleanup_expired_recordings()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("[Recording] Error in cleanup loop: %s", e)

    async def _cleanup_expired_recordings(self) -> int:
        """Clean up expired recordings across all cameras."""
        total_deleted = 0
        configs = self._config_dao.get_all()
        
        for config in configs:
            expired = self._segment_dao.get_expired(config.retention_days)
            for segment in expired:
                await self._storage.delete_segment(segment.file_path)
                self._segment_dao.delete_by_id(segment.id)
                total_deleted += 1
        
        await self._storage.cleanup_empty_dirs()
        
        if total_deleted > 0:
            logger.info("[Recording] Cleaned up %d expired recording segments", total_deleted)
        
        return total_deleted


# Global service instance
recording_service: Optional[RecordingService] = None


def get_recording_service() -> RecordingService:
    """Get the global recording service instance."""
    global recording_service
    if recording_service is None:
        recording_service = RecordingService(
            recording_config_dao=RecordingConfigDAO(),
            recording_segment_dao=RecordingSegmentDAO(),
            storage_manager=recording_storage,
        )
    return recording_service


async def init_recording_service() -> RecordingService:
    """Initialize and return the recording service."""
    service = get_recording_service()
    service.configure()
    await service.initialize()
    return service
