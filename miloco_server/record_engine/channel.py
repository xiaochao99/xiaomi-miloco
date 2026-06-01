# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
ChannelRecorder - Per-camera channel recording implementation.

Handles raw H.265/H.264 stream muxing with:
- Zero-copy recording via PyAV
- Streaming write to MPEG-TS format
- Pre-recording buffer for trigger-based modes
- Keyframe-aligned segment rotation
"""

import asyncio
import logging
import os
import time
from collections import deque
from datetime import datetime
from fractions import Fraction
from pathlib import Path
from typing import Callable, Coroutine, Deque, Dict, List, Optional, Tuple

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

# H.264 NAL type constants
H264_NAL_SLICE = 1
H264_NAL_IDR = 5
H264_NAL_SPS = 7
H264_NAL_PPS = 8


def parse_nal_type(data: bytes) -> Tuple[int, str]:
    """Parse NAL unit type from Annex B data.
    
    Returns:
        Tuple of (nal_type, codec) where codec is 'h264' or 'h265'
    """
    if not data or len(data) < 5:
        return -1, ""
    
    # Find NAL header after start code
    if data[0] == 0 and data[1] == 0:
        if data[2] == 0 and data[3] == 1:
            nal_byte = data[4]
        elif data[2] == 1:
            nal_byte = data[3]
        else:
            return -1, ""
    else:
        return -1, ""
    
    # Try H.265 first (NAL type in bits [6:1])
    h265_type = (nal_byte >> 1) & 0x3F
    if h265_type >= 32:  # VPS/SPS/PPS are H.265 specific
        return h265_type, "h265"
    
    # Try H.264 (NAL type in bits [4:0])
    h264_type = nal_byte & 0x1F
    if h264_type in (H264_NAL_SPS, H264_NAL_PPS, H264_NAL_IDR):
        return h264_type, "h264"
    
    # Default to H.265 for other types
    return h265_type, "h265"


def is_keyframe(nal_type: int, codec: str) -> bool:
    """Check if NAL unit is a keyframe."""
    if codec == "h264":
        return nal_type in (H264_NAL_IDR, H264_NAL_SPS, H264_NAL_PPS)
    else:  # h265
        return nal_type in (H265_NAL_IDR_W_RADL, H265_NAL_IDR_N_LP, H265_NAL_CRA, H265_NAL_VPS)


def is_header(nal_type: int, codec: str) -> bool:
    """Check if NAL unit is a header (VPS/SPS/PPS)."""
    if codec == "h264":
        return nal_type in (H264_NAL_SPS, H264_NAL_PPS)
    else:  # h265
        return nal_type in (H265_NAL_VPS, H265_NAL_SPS, H265_NAL_PPS)


class PreRecordingBuffer:
    """Time-based pre-recording buffer for storing recent video frames.
    
    Maintains a rolling buffer of video data for the specified duration.
    When recording is triggered, this buffer provides the pre-trigger footage.
    Ensures buffer data starts with a keyframe to avoid garbled playback.
    """
    
    def __init__(self, duration_seconds: float = 5.0, max_bytes: int = 50 * 1024 * 1024):
        """Initialize the pre-recording buffer.
        
        Args:
            duration_seconds: Maximum duration to keep in buffer
            max_bytes: Maximum buffer size in bytes (default 50MB)
        """
        self.duration_seconds = duration_seconds
        self.max_bytes = max_bytes
        # List of (timestamp, data_bytes, is_keyframe) tuples
        self._frames: Deque[Tuple[float, bytes, bool]] = deque()
        self._total_bytes = 0
        
    def add_frame(self, timestamp: float, data: bytes, is_keyframe: bool):
        """Add a frame to the buffer."""
        self._frames.append((timestamp, data, is_keyframe))
        self._total_bytes += len(data)
        
        # Remove old frames beyond the time window
        cutoff_time = timestamp - self.duration_seconds
        while self._frames and self._frames[0][0] < cutoff_time:
            _, old_data, _ = self._frames.popleft()
            self._total_bytes -= len(old_data)
        
        # Also remove frames if buffer exceeds max bytes (keep at least 1 keyframe)
        while self._frames and self._total_bytes > self.max_bytes:
            # Find the second keyframe to keep at least one
            first_keyframe_idx = -1
            for i, (_, _, is_kf) in enumerate(self._frames):
                if is_kf:
                    if first_keyframe_idx == -1:
                        first_keyframe_idx = i
                    else:
                        # Found second keyframe, remove everything before it
                        break
            
            if first_keyframe_idx > 0:
                # Remove frames up to (but not including) the first keyframe
                for _ in range(first_keyframe_idx):
                    _, old_data, _ = self._frames.popleft()
                    self._total_bytes -= len(old_data)
            else:
                # Only one or zero keyframes, remove oldest frame
                _, old_data, _ = self._frames.popleft()
                self._total_bytes -= len(old_data)
    
    def get_buffer_data_from_keyframe(self) -> List[Tuple[float, bytes, bool]]:
        """Get buffer data starting from the first keyframe.
        
        This ensures the recording starts with a decodable frame.
        If no keyframe in buffer, return all data (best effort).
        """
        if not self._frames:
            return []
        
        # Find first keyframe index
        start_index = 0
        for i, (_, _, is_keyframe) in enumerate(self._frames):
            if is_keyframe:
                start_index = i
                break
        
        # Return data from that index onwards
        return list(self._frames)[start_index:]
    
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


class ChannelRecorder:
    """Per-camera channel recorder using PyAV for zero-copy muxing.
    
    Records raw H.265/H.264 stream to MPEG-TS format with:
    - Streaming write (no memory buffering)
    - Keyframe-aligned segment rotation
    - Pre-recording buffer for trigger modes
    """
    
    def __init__(
        self,
        camera_id: str,
        channel: int,
        segment_duration: int = 300,
        pre_buffer_seconds: float = 5.0,
        output_dir: Path = Path("recordings"),
        recording_mode: str = "continuous",
    ):
        self.camera_id = camera_id
        self.channel = channel
        self.segment_duration = segment_duration
        self.output_dir = output_dir
        self.recording_mode = recording_mode  # "continuous", "motion", "person"
        
        # Pre-recording buffer
        self.pre_buffer = PreRecordingBuffer(duration_seconds=pre_buffer_seconds)
        
        # Segment state
        self._active = False
        self._container = None  # av.OutputContainer
        self._stream = None     # av.OutputStream
        self._segment_path: Optional[Path] = None
        self._segment_start: Optional[datetime] = None
        self._segment_start_time: Optional[float] = None
        self._last_rotate_time: Optional[float] = None
        self._frame_count = 0
        self._awaiting_keyframe = False
        self._first_pts_offset: Optional[float] = None  # 保证 PTS 从 0 开始
        
        # Codec headers
        self._vps_data: Optional[bytes] = None
        self._sps_data: Optional[bytes] = None
        self._pps_data: Optional[bytes] = None
        self._detected_codec: str = ""
        
        # FPS estimation
        self._frame_timestamps: List[float] = []
        self._estimated_fps: float = 15.0
        
        # Statistics
        self._total_frames = 0
        self._total_bytes = 0
        self._total_segments = 0
        
        logger.info("[ChannelRecorder] Initialized for camera %s channel %d", camera_id, channel)
    
    @property
    def active(self) -> bool:
        return self._active
    
    @property
    def current_segment_path(self) -> Optional[Path]:
        return self._segment_path
    
    @property
    def estimated_fps(self) -> float:
        return self._estimated_fps
    
    def _get_segment_path(self) -> Path:
        """Generate path for new segment.
        
        Filename format: {HH-MM-SS}_{index}_{mode}.ts
        mode is: c (continuous), m (motion), p (person)
        """
        now = datetime.now()
        date_dir = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H-%M-%S")
        # Encode mode in filename: continuous->c, motion->m, person->p
        mode_short = {"continuous": "c", "motion": "m", "person": "p"}.get(self.recording_mode, "c")
        segment_id = f"{time_str}_{self._total_segments:04d}_{mode_short}"
        
        camera_dir = self.output_dir / self.camera_id / date_dir
        os.makedirs(camera_dir, exist_ok=True)
        
        return camera_dir / f"{segment_id}.ts"
    
    def _open_segment(self) -> bool:
        """Open a new segment for writing."""
        try:
            import av
            
            self._segment_path = self._get_segment_path()
            self._container = av.open(str(self._segment_path), 'w', format='mpegts')
            
            # Add video stream
            # PyAV uses "hevc" for H.265, not "h265"
            if self._detected_codec == "h265":
                codec_name = "hevc"
            elif self._detected_codec == "h264":
                codec_name = "h264"
            else:
                codec_name = self._detected_codec or "hevc"
            self._stream = self._container.add_stream(codec_name, rate=15)
            self._stream.time_base = Fraction(1, 90000)
            
            # Set extradata if we have headers
            if self._detected_codec == "h265" and self._vps_data and self._sps_data and self._pps_data:
                # Build extradata for H.265
                extradata = self._build_h265_extradata()
                if extradata:
                    self._stream.codec_context.extradata = extradata
            elif self._detected_codec == "h264" and self._sps_data and self._pps_data:
                # Build extradata for H.264
                extradata = self._build_h264_extradata()
                if extradata:
                    self._stream.codec_context.extradata = extradata
            
            self._segment_start = datetime.now()
            self._segment_start_time = time.time()
            self._last_rotate_time = time.time()
            self._frame_count = 0
            self._awaiting_keyframe = True
            self._first_pts_offset = None  # 新 segment 重置 PTS 偏移基准
            self._total_segments += 1
            
            logger.info("[ChannelRecorder] Opened segment: %s", self._segment_path)
            return True
            
        except Exception as e:
            logger.error("[ChannelRecorder] Failed to open segment: %s", e, exc_info=True)
            self._close_container()
            return False
    
    def _close_container(self):
        """Close the current container."""
        if self._container:
            try:
                self._container.close()
            except Exception as e:
                logger.warning("[ChannelRecorder] Error closing container: %s", e)
            self._container = None
            self._stream = None
    
    def _build_h265_extradata(self) -> Optional[bytes]:
        """Build HEVCDecoderConfigurationRecord from VPS/SPS/PPS."""
        if not self._vps_data or not self._sps_data or not self._pps_data:
            return None
        
        # Simple approach: concatenate with start codes
        # PyAV/FFmpeg will handle the conversion
        extradata = bytearray()
        extradata.extend(self._vps_data)
        extradata.extend(self._sps_data)
        extradata.extend(self._pps_data)
        return bytes(extradata)
    
    def _build_h264_extradata(self) -> Optional[bytes]:
        """Build AVCC extradata from SPS/PPS."""
        if not self._sps_data or not self._pps_data:
            return None
        
        # Simple approach: concatenate with start codes
        extradata = bytearray()
        extradata.extend(self._sps_data)
        extradata.extend(self._pps_data)
        return bytes(extradata)
    
    def _mux_frame(self, data: bytes, timestamp: float, is_keyframe: bool):
        """Mux a single frame to the container."""
        if not self._container or not self._stream:
            return False
        
        try:
            import av
            
            # Create packet from raw data
            packet = av.Packet(data)
            packet.stream = self._stream
            
            # Calculate PTS in stream timebase (90kHz)
            # 以第一个写入帧的时间为基准，确保 PTS 严格从 0 开始
            if self._segment_start_time is not None:
                relative_time = timestamp - self._segment_start_time
                if self._first_pts_offset is None:
                    self._first_pts_offset = relative_time
                # 减去第一个帧的偏移，保证 PTS 从 0 起算
                normalized_time = relative_time - self._first_pts_offset
                pts = int(normalized_time * 90000)  # Convert to 90kHz timebase
            else:
                pts = self._frame_count * 6000  # Assume 15fps
            
            packet.pts = pts
            packet.dts = pts
            # PyAV 12+ auto-detects keyframe from NAL unit, older versions need explicit set
            if hasattr(packet, 'keyframe'):
                packet.keyframe = is_keyframe
            
            # Mux the packet
            self._container.mux_one(packet)
            self._frame_count += 1
            self._total_frames += 1
            self._total_bytes += len(data)
            
            return True
            
        except Exception as e:
            logger.error("[ChannelRecorder] Mux error: %s", e)
            return False
    
    def _update_fps(self, timestamp: float):
        """Update FPS estimation."""
        self._frame_timestamps.append(timestamp)
        if len(self._frame_timestamps) > 100:
            self._frame_timestamps = self._frame_timestamps[-100:]
        
        if len(self._frame_timestamps) >= 2:
            time_span = self._frame_timestamps[-1] - self._frame_timestamps[0]
            if time_span > 0:
                self._estimated_fps = (len(self._frame_timestamps) - 1) / time_span
    
    async def on_raw_frame(self, did: str, data: bytes, ts: int, seq: int, channel: int):
        """Callback for raw video frames from camera.
        
        This is the main entry point for frame processing:
        1. Parse NAL type and detect codec
        2. Track VPS/SPS/PPS headers
        3. Add to pre-recording buffer
        4. If active, mux frame to segment
        5. Check for segment rotation
        """
        timestamp = ts / 1000.0  # Convert ms to seconds
        
        # Parse NAL type
        nal_type, codec = parse_nal_type(data)
        if nal_type < 0:
            return
        
        # Detect codec
        if not self._detected_codec and codec:
            self._detected_codec = codec
            logger.info("[ChannelRecorder] Detected codec: %s for camera %s", codec, self.camera_id)
        
        # Track headers
        if codec == "h265":
            if nal_type == H265_NAL_VPS:
                self._vps_data = data
            elif nal_type == H265_NAL_SPS:
                self._sps_data = data
            elif nal_type == H265_NAL_PPS:
                self._pps_data = data
        elif codec == "h264":
            if nal_type == H264_NAL_SPS:
                self._sps_data = data
            elif nal_type == H264_NAL_PPS:
                self._pps_data = data
        
        # Check if keyframe
        frame_is_keyframe = is_keyframe(nal_type, codec)
        
        # Update FPS
        self._update_fps(timestamp)
        
        # Add to pre-recording buffer
        self.pre_buffer.add_frame(timestamp, data, frame_is_keyframe)
        
        # If not active, just buffer
        if not self._active:
            return
        
        # If awaiting keyframe, skip until we get one
        if self._awaiting_keyframe:
            if not frame_is_keyframe:
                return
            self._awaiting_keyframe = False
            logger.info("[ChannelRecorder] Got keyframe, starting mux for camera %s", self.camera_id)
        
        # Mux frame
        self._mux_frame(data, timestamp, frame_is_keyframe)
        
        # Check segment rotation
        await self._check_rotation(frame_is_keyframe)
    
    async def _check_rotation(self, is_keyframe: bool):
        """Check if we need to rotate the segment."""
        if not self._active or not self._last_rotate_time:
            return
        
        current_time = time.time()
        elapsed = current_time - self._last_rotate_time
        
        # Rotate at keyframe boundary after segment duration
        if elapsed >= self.segment_duration and is_keyframe:
            logger.info("[ChannelRecorder] Rotating segment for camera %s after %.1fs", 
                       self.camera_id, elapsed)
            
            # Close current segment
            self._close_container()
            
            # Open new segment
            if self._open_segment():
                # Prepend headers to new segment
                self._awaiting_keyframe = False
                self._last_rotate_time = current_time
    
    async def start_recording(self):
        """Start recording for this channel."""
        if self._active:
            logger.warning("[ChannelRecorder] Already active for camera %s channel %d", 
                          self.camera_id, self.channel)
            return
        
        logger.info("[ChannelRecorder] Starting recording for camera %s channel %d (mode: %s)", 
                   self.camera_id, self.channel, self.recording_mode)
        
        # Open first segment
        if self._open_segment():
            self._active = True
            
            # Mux pre-buffer data
            pre_buffer_frames = self.pre_buffer.get_buffer_data_from_keyframe()
            if pre_buffer_frames:
                buffer_duration = self.pre_buffer.get_duration()
                buffer_size_mb = self.pre_buffer._total_bytes / (1024 * 1024)
                logger.info("[ChannelRecorder] Muxing %d pre-buffer frames for camera %s (%.1fs, %.2fMB)", 
                           len(pre_buffer_frames), self.camera_id, buffer_duration, buffer_size_mb)
                for timestamp, data, is_kf in pre_buffer_frames:
                    self._mux_frame(data, timestamp, is_kf)
            
            logger.info("[ChannelRecorder] Recording started for camera %s", self.camera_id)
        else:
            logger.error("[ChannelRecorder] Failed to start recording for camera %s", self.camera_id)
    
    async def stop_recording(self):
        """Stop recording for this channel."""
        if not self._active:
            return
        
        logger.info("[ChannelRecorder] Stopping recording for camera %s channel %d", 
                   self.camera_id, self.channel)
        
        self._active = False
        self._close_container()
        
        logger.info("[ChannelRecorder] Recording stopped for camera %s (%d frames, %d bytes, %d segments)",
                   self.camera_id, self._total_frames, self._total_bytes, self._total_segments)
    
    def get_stats(self) -> dict:
        """Get recording statistics."""
        return {
            "camera_id": self.camera_id,
            "channel": self.channel,
            "active": self._active,
            "total_frames": self._total_frames,
            "total_bytes": self._total_bytes,
            "total_segments": self._total_segments,
            "estimated_fps": self._estimated_fps,
            "current_segment": str(self._segment_path) if self._segment_path else None,
            "segment_frame_count": self._frame_count,
            "detected_codec": self._detected_codec,
        }
