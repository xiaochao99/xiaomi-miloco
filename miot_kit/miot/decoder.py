# -*- coding: utf-8 -*-
# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
"""
MIoT Decoder.
"""
import asyncio
from collections import deque
import logging
import subprocess
import threading
import time
from typing import List, Callable, Coroutine, Optional
from io import BytesIO
from av.packet import Packet
from av.codec import CodecContext
from av.video.codeccontext import VideoCodecContext
from av.audio.codeccontext import AudioCodecContext
from av.audio.resampler import AudioResampler
from av.video.frame import VideoFrame
from av.audio.frame import AudioFrame
from PIL import Image

from .types import MIoTCameraFrameType, MIoTCameraCodec, MIoTCameraFrameData
from .error import MIoTMediaDecoderError

_LOGGER = logging.getLogger(__name__)


class MIoTMediaRingBuffer():
    """Ring buffer."""
    _maxlen: int
    _video_buffer: deque[MIoTCameraFrameData]
    _audio_buffer: deque[MIoTCameraFrameData]
    _cond: threading.Condition

    def __init__(self, maxlen: int = 20):
        self._maxlen = maxlen
        self._video_buffer = deque(maxlen=maxlen)
        self._audio_buffer = deque(maxlen=maxlen)
        self._cond = threading.Condition()

    def put_video(self, item: MIoTCameraFrameData) -> None:
        with self._cond:
            # When the queue is full, non-key frames are discarded first
            if len(self._video_buffer) >= self._maxlen:
                if item.frame_type == MIoTCameraFrameType.FRAME_I:
                    removed: bool = False
                    for i in range(len(self._video_buffer)):
                        if self._video_buffer[i].frame_type != MIoTCameraFrameType.FRAME_I:
                            del self._video_buffer[i]
                            removed = True
                            break
                    if not removed:
                        self._video_buffer.popleft()
                    self._video_buffer.append(item)
                    self._cond.notify()
                else:
                    # Drop non-I frame
                    pass
                _LOGGER.info("drop non-I frame, %s, %s", item.codec_id, item.timestamp)
            else:
                self._video_buffer.append(item)
                self._cond.notify()

    def put_audio(self, item: MIoTCameraFrameData) -> None:
        with self._cond:
            self._audio_buffer.append(item)
            self._cond.notify()

    def step(
        self,
        on_video_frame: Callable[[MIoTCameraFrameData], None],
        on_audio_frame: Callable[[MIoTCameraFrameData], None],
        timeout: float = 0.2
    ) -> None:
        on_frame: Callable[[MIoTCameraFrameData], None] = on_video_frame
        frame_data: Optional[MIoTCameraFrameData] = None
        # get frame
        with self._cond:
            if self._video_buffer:
                frame_data = self._video_buffer.popleft()
            elif self._audio_buffer:
                frame_data = self._audio_buffer.popleft()
                on_frame = on_audio_frame
            else:
                self._cond.wait(timeout=timeout)
        # handle frame
        if frame_data:
            on_frame(frame_data)

    def stop(self):
        del self._cond
        self._video_buffer.clear()
        self._audio_buffer.clear()


class MIoTMediaDecoder(threading.Thread):
    """MIoT Decoder."""
    _main_loop: asyncio.AbstractEventLoop
    _running: bool
    _frame_interval: int
    _enable_hw_accel: bool
    _enable_audio: bool
    _vision_img_resolution: int  # Target resolution for AI vision analysis (width)

    # format: did, data, ts, channel
    _video_callback: Callable[[bytes, int, int], Coroutine]
    # format: did, data, ts, channel
    _audio_callback: Callable[[bytes, int, int], Coroutine]

    _queue: MIoTMediaRingBuffer
    _video_decoder: Optional[CodecContext]
    _audio_decoder: Optional[CodecContext]
    _resampler: AudioResampler

    _current_jpg_width: int
    _current_jpg_height: int
    _last_jpeg_ts: int

    # H265 VPS/SPS/PPS cache for fixing decoder initialization
    _h265_vps: Optional[bytes]
    _h265_sps: Optional[bytes]
    _h265_pps: Optional[bytes]

    def __init__(
        self,
        frame_interval: int,
        video_callback: Callable[[bytes, int, int], Coroutine],
        audio_callback: Optional[Callable[[bytes, int, int], Coroutine]] = None,
        enable_hw_accel: bool = False,
        enable_audio: bool = False,
        main_loop: Optional[asyncio.AbstractEventLoop] = None,
        vision_img_resolution: int = 0,  # 0 means use original resolution
    ) -> None:
        super().__init__()
        self._main_loop = main_loop or asyncio.get_running_loop()
        self._running = False
        self._frame_interval = frame_interval
        self._enable_hw_accel = enable_hw_accel
        self._enable_audio = enable_audio
        self._vision_img_resolution = vision_img_resolution

        self._video_callback = video_callback
        if enable_audio:
            if not audio_callback:
                raise MIoTMediaDecoderError("audio_callback is required when enable audio")
            else:
                self._audio_callback = audio_callback

        self._queue = MIoTMediaRingBuffer()
        self._video_decoder = None
        self._audio_decoder = None
        self._resampler = None  # type: ignore

        self._last_jpeg_ts = 0
        self._h265_vps = None
        self._h265_sps = None
        self._h265_pps = None

    def run(self) -> None:
        """Start the decoder."""
        self._running = True
        while self._running:
            try:
                self._queue.step(
                    on_video_frame=self._on_video_callback,
                    on_audio_frame=self._on_audio_callback
                )
            except Exception as e:  # pylint: disable=broad-except
                _LOGGER.error("frame data handle error, %s", e)
                if self._main_loop.is_closed():
                    break
        _LOGGER.info("decoder stopped")

    def stop(self) -> None:
        """Stop the decoder."""
        self._running = False
        self._queue.stop()
        self._video_decoder = None
        self._audio_decoder = None
        self.join()

    def push_video_frame(self, frame_data: MIoTCameraFrameData) -> None:
        self._queue.put_video(frame_data)

    def push_audio_frame(self, frame_data: MIoTCameraFrameData) -> None:
        self._queue.put_audio(frame_data)

    def detect_hwaccel(self):
        try:
            result = subprocess.run(
                ["ffmpeg", "-hwaccels"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=True
            )
            hw_list = result.stdout.strip().split("\n")[1:]
            return hw_list
        except FileNotFoundError:
            return []

    def choose_hw_decoder(self, codec_name, hw_methods):
        if codec_name in ("h264", "hevc"):
            if f"{codec_name}_v4l2m2m" in hw_methods:
                return f"{codec_name}_v4l2m2m"
        return codec_name

    @staticmethod
    def _find_h265_nalu_start(data: bytes, offset: int = 0) -> int:
        """Find the start of next H265 NAL unit (scans for 00 00 01 or 00 00 00 01)."""
        i = offset
        while i < len(data) - 3:
            if data[i] == 0x00 and data[i + 1] == 0x00:
                if data[i + 2] == 0x01:
                    return i
                if i + 3 < len(data) and data[i + 2] == 0x00 and data[i + 3] == 0x01:
                    return i
            i += 1
        return -1

    def _extract_h265_nalu_header(self, data: bytes, frame_type: MIoTCameraFrameType) -> None:
        """Extract VPS/SPS/PPS from H265 data for decoder initialization."""
        # Only extract from I-frames which should contain VPS/SPS/PPS
        if frame_type != MIoTCameraFrameType.FRAME_I:
            return

        pos = 0
        while pos < len(data) - 4:
            start = self._find_h265_nalu_start(data, pos)
            if start < 0:
                break

            # Determine start code length
            sc_len = 4 if (start + 3 < len(data) and data[start + 2] == 0x00 and data[start + 3] == 0x01) else 3
            header_byte = data[start + sc_len]
            nalu_type = (header_byte >> 1) & 0x3F

            # Find next NAL unit to determine this NAL's length
            next_start = self._find_h265_nalu_start(data, start + sc_len + 1)
            nalu_end = next_start if next_start > 0 else len(data)
            nalu_data = data[start + sc_len:nalu_end]

            if nalu_type == 32:  # VPS
                self._h265_vps = nalu_data
                _LOGGER.debug("Extracted H265 VPS: %d bytes", len(nalu_data))
            elif nalu_type == 33:  # SPS
                self._h265_sps = nalu_data
                _LOGGER.debug("Extracted H265 SPS: %d bytes", len(nalu_data))
            elif nalu_type == 34:  # PPS
                self._h265_pps = nalu_data
                _LOGGER.debug("Extracted H265 PPS: %d bytes", len(nalu_data))

            pos = nalu_end

    def _inject_h265_header(self, data: bytes) -> bytes:
        """Inject cached VPS/SPS/PPS before frame data if decoder needs them."""
        if not (self._h265_vps and self._h265_sps and self._h265_pps):
            return data

        # Check if data already contains VPS/SPS/PPS
        first_nalu_pos = self._find_h265_nalu_start(data, 0)
        if first_nalu_pos >= 0:
            sc_len = 4 if (first_nalu_pos + 3 < len(data) and
                          data[first_nalu_pos + 2] == 0x00 and
                          data[first_nalu_pos + 3] == 0x01) else 3
            header_byte = data[first_nalu_pos + sc_len]
            nalu_type = (header_byte >> 1) & 0x3F
            # If first NAL is already VPS/SPS/PPS, no injection needed
            if nalu_type in (32, 33, 34):
                return data

        # Prepend VPS + SPS + PPS with start codes
        header = b'\x00\x00\x00\x01'
        return (header + self._h265_vps +
                header + self._h265_sps +
                header + self._h265_pps +
                data)

    def _on_video_callback(self, frame_data: MIoTCameraFrameData) -> None:
        # Fast path: skip frames we don't need yet (before expensive decode)
        now_ts = int(time.time() * 1000)
        if now_ts - self._last_jpeg_ts < self._frame_interval:
            return

        if not self._video_decoder:
            # Create video decoder
            if frame_data.codec_id == MIoTCameraCodec.VIDEO_H264:
                self._video_decoder = VideoCodecContext.create("h264", "r")
            elif frame_data.codec_id == MIoTCameraCodec.VIDEO_H265:
                self._video_decoder = VideoCodecContext.create("hevc", "r")
            _LOGGER.info("video decoder created, %s", frame_data.codec_id)

        # H265 fix: extract and inject VPS/SPS/PPS if missing from stream
        data = frame_data.data
        if frame_data.codec_id == MIoTCameraCodec.VIDEO_H265:
            self._extract_h265_nalu_header(data, frame_data.frame_type)
            data = self._inject_h265_header(data)

        pkt = Packet(data)
        frames: List[VideoFrame] = self._video_decoder.decode(pkt)  # type: ignore
        if not frames:
            _LOGGER.debug("video frame is empty, %d, %d", frame_data.codec_id, frame_data.timestamp)
            return
        frame = frames[0]
        rgb_frame: VideoFrame = frame.to_rgb()
        img: Image.Image = rgb_frame.to_image()

        # Resize image for AI vision analysis if configured
        if self._vision_img_resolution > 0 and img.width > self._vision_img_resolution:
            aspect_ratio = img.height / img.width
            new_height = int(self._vision_img_resolution * aspect_ratio)
            img = img.resize(
                (self._vision_img_resolution, new_height),
                Image.Resampling.BILINEAR
            )

        buf: BytesIO = BytesIO()
        img.save(buf, format="JPEG", quality=85)
        jpeg_data = buf.getvalue()
        self._main_loop.call_soon_threadsafe(
            self._main_loop.create_task,
            self._video_callback(jpeg_data, frame_data.timestamp, frame_data.channel)
        )
        self._last_jpeg_ts = now_ts

    def _on_audio_callback(self, frame_data: MIoTCameraFrameData) -> None:
        if not self._audio_decoder:
            # Create audio decoder
            if frame_data.codec_id == MIoTCameraCodec.AUDIO_OPUS:
                self._audio_decoder = AudioCodecContext.create("opus", "r")
            self._resampler = AudioResampler(format="s16", layout="mono", rate=16000)
            _LOGGER.info("audio decoder created, %s", frame_data.codec_id)
        pkt = Packet(frame_data.data)
        frames: List[AudioFrame] = self._audio_decoder.decode(pkt)  # type: ignore
        pcm_bytes: bytes = b""
        for frame in frames:
            rs_frames = self._resampler.resample(frame)
            for rs_frame in rs_frames:
                pcm_bytes += rs_frame.to_ndarray().tobytes()
        self._main_loop.call_soon_threadsafe(
            self._main_loop.create_task,
            self._audio_callback(pcm_bytes, frame_data.timestamp, frame_data.channel)
        )


class MIoTMediaRecorder(threading.Thread):
    """MIoT Recorder."""
    _main_loop: asyncio.AbstractEventLoop
