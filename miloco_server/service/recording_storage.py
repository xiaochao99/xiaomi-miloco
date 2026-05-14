# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Recording storage manager.
Handles file I/O for recording segments, including path management, streaming playback, and cleanup.
"""

import asyncio
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import BinaryIO, Optional, Tuple

import aiofiles

from miloco_server.config.normal_config import STORAGE_DIR

logger = logging.getLogger(__name__)

RECORDING_SUBDIR = "recordings"


def _get_recording_root() -> Path:
    """Get the root directory for recording storage."""
    return STORAGE_DIR / RECORDING_SUBDIR


class RecordingStorageManager:
    """Manages recording file storage on disk."""

    def __init__(self, base_path: Optional[str] = None):
        self._base_path = Path(base_path) if base_path else _get_recording_root()
        os.makedirs(self._base_path, exist_ok=True)

    @property
    def base_path(self) -> Path:
        return self._base_path

    def get_segment_path(self, camera_id: str, segment_id: str, date: Optional[datetime] = None) -> Path:
        """Get the full file path for a recording segment."""
        dt = date or datetime.now()
        date_dir = dt.strftime("%Y-%m-%d")
        return self._base_path / camera_id / date_dir / f"{segment_id}.mp4"

    def get_relative_path(self, camera_id: str, segment_id: str, date: Optional[datetime] = None) -> str:
        """Get the relative path (from base_path) for database storage."""
        dt = date or datetime.now()
        date_dir = dt.strftime("%Y-%m-%d")
        return os.path.join(camera_id, date_dir, f"{segment_id}.mp4")

    def resolve_path(self, relative_path: str) -> Path:
        """Resolve a relative path to a full path."""
        return self._base_path / relative_path

    async def save_segment(
        self,
        camera_id: str,
        segment_id: str,
        data: bytes,
        date: Optional[datetime] = None,
        fps: float = 15.0,
    ) -> Tuple[str, int]:
        """Save a recording segment to disk.
        Uses FFmpeg to mux raw H.265 stream into MP4 container.

        Args:
            fps: Estimated frame rate of the raw H.265 stream.

        Returns:
            Tuple of (relative_path, file_size_bytes)
        """
        full_path = self.get_segment_path(camera_id, segment_id, date)
        os.makedirs(full_path.parent, exist_ok=True)

        try:
            # Use FFmpeg to mux H.265 stream into MP4 container
            file_size = await self._mux_h265_to_mp4(data, full_path, fps=fps)
            relative_path = str(full_path.relative_to(self._base_path))
            logger.info("Saved recording segment %s (%d bytes)", relative_path, file_size)
            return relative_path, file_size
        except Exception as e:
            logger.error("Error saving recording segment %s: %s", segment_id, e)
            raise

    async def _mux_h265_to_mp4(self, data: bytes, output_path: Path, fps: float = 15.0) -> int:
        """Mux raw H.265 stream into MP4 container using FFmpeg.
        
        Args:
            fps: Input frame rate for the raw H.265 stream.
        
        Returns:
            File size in bytes
        """
        import tempfile
        import subprocess
        
        logger.info("[Storage] Starting FFmpeg mux for %s, data size: %d bytes, fps: %.1f", output_path, len(data), fps)
        
        # Create temporary input file
        with tempfile.NamedTemporaryFile(suffix='.265', delete=False) as input_file:
            input_file.write(data)
            input_path = input_file.name
        logger.info("[Storage] Created temp input file: %s", input_path)
        
        try:
            # FFmpeg command to mux H.265 to MP4 (no re-encoding)
            # Use -r before input to specify the correct input frame rate
            # This prevents FFmpeg from guessing 25fps for raw H.265 streams
            cmd = [
                'ffmpeg',
                '-y',
                '-r', str(fps),  # Specify input frame rate BEFORE input
                '-fflags', '+genpts+discardcorrupt+enable_ts_discontinuity_detection',
                '-analyzeduration', '10000000',  # 10 seconds analysis time for better probing
                '-probesize', '10000000',  # 10MB probe size
                '-err_detect', 'ignore_err',
                '-i', input_path,
                '-c:v', 'copy',  # Copy video stream without re-encoding
                '-movflags', '+faststart+default_base_moof',
                '-max_muxing_queue_size', '9999',
                '-f', 'mp4',
                str(output_path)
            ]
            logger.info("[Storage] Running FFmpeg command: %s", ' '.join(cmd[:8]) + ' ...')
            
            # Run FFmpeg in executor to not block event loop
            loop = asyncio.get_event_loop()
            try:
                result = await loop.run_in_executor(
                    None, 
                    lambda: subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                )
                
                if result.returncode != 0:
                    logger.warning("[Storage] FFmpeg copy mux failed (code %d), trying re-encode fallback", result.returncode)
                    if result.stderr:
                        logger.warning("[Storage] FFmpeg stderr: %s", result.stderr[:500])
                    # Fallback 2: try re-encoding (handles missing headers better)
                    cmd_reencode = [
                        'ffmpeg',
                        '-y',
                        '-r', str(fps),  # Specify input frame rate BEFORE input
                        '-fflags', '+genpts+discardcorrupt',
                        '-analyzeduration', '10000000',
                        '-probesize', '10000000',
                        '-err_detect', 'ignore_err',
                        '-i', input_path,
                        '-c:v', 'libx264',  # Re-encode to H.264 for compatibility
                        '-preset', 'ultrafast',
                        '-crf', '23',
                        '-movflags', '+faststart',
                        '-f', 'mp4',
                        str(output_path)
                    ]
                    logger.info("[Storage] Running FFmpeg re-encode fallback")
                    result2 = await loop.run_in_executor(
                        None,
                        lambda: subprocess.run(cmd_reencode, capture_output=True, text=True, timeout=180)
                    )
                    if result2.returncode != 0:
                        logger.warning("[Storage] FFmpeg re-encode also failed (code %d), saving raw data", result2.returncode)
                        async with aiofiles.open(str(output_path), "wb") as f:
                            await f.write(data)
                        logger.info("[Storage] Raw data saved to %s as final fallback", output_path)
                    else:
                        logger.info("[Storage] FFmpeg re-encode successful")
                else:
                    logger.info("[Storage] FFmpeg copy mux successful")
            except FileNotFoundError:
                logger.warning("[Storage] FFmpeg not found, falling back to raw data save")
                async with aiofiles.open(str(output_path), "wb") as f:
                    await f.write(data)
                logger.info("[Storage] Raw data saved to %s", output_path)
            
            if output_path.exists():
                file_size = output_path.stat().st_size
                logger.info("[Storage] Output file created: %s (%d bytes)", output_path, file_size)
                return file_size
            else:
                logger.error("[Storage] Output file not created!")
                return 0
            
        finally:
            # Clean up temp file
            try:
                os.unlink(input_path)
                logger.info("[Storage] Cleaned up temp file: %s", input_path)
            except Exception as e:
                logger.warning("[Storage] Failed to clean up temp file: %s", e)

    async def open_segment_for_read(self, relative_path: str) -> Optional[bytes]:
        """Read a recording segment file."""
        full_path = self.resolve_path(relative_path)
        if not full_path.exists():
            logger.warning("Recording segment file not found: %s", full_path)
            return None
        try:
            async with aiofiles.open(str(full_path), "rb") as f:
                return await f.read()
        except Exception as e:
            logger.error("Error reading recording segment %s: %s", relative_path, e)
            return None

    def open_segment_stream(self, relative_path: str) -> Optional[BinaryIO]:
        """Open a recording segment for streaming (synchronous)."""
        full_path = self.resolve_path(relative_path)
        if not full_path.exists():
            logger.warning("Recording segment file not found: %s", full_path)
            return None
        try:
            return open(str(full_path), "rb")
        except Exception as e:
            logger.error("Error opening recording segment %s: %s", relative_path, e)
            return None

    def get_file_size(self, relative_path: str) -> int:
        """Get the file size of a recording segment."""
        full_path = self.resolve_path(relative_path)
        if not full_path.exists():
            return 0
        return full_path.stat().st_size

    async def delete_segment(self, relative_path: str) -> bool:
        """Delete a recording segment file."""
        full_path = self.resolve_path(relative_path)
        if not full_path.exists():
            return True
        try:
            # Use asyncio.to_thread for async file deletion (compatible with all Python versions)
            await asyncio.to_thread(os.remove, str(full_path))
            logger.info("Deleted recording segment: %s", relative_path)
            return True
        except Exception as e:
            logger.error("Error deleting recording segment %s: %s", relative_path, e)
            return False

    def delete_segment_sync(self, relative_path: str) -> bool:
        """Delete a recording segment file (synchronous)."""
        full_path = self.resolve_path(relative_path)
        if not full_path.exists():
            return True
        try:
            full_path.unlink()
            logger.info("Deleted recording segment: %s", relative_path)
            return True
        except Exception as e:
            logger.error("Error deleting recording segment %s: %s", relative_path, e)
            return False

    async def delete_camera_recordings(self, camera_id: str) -> int:
        """Delete all recording files for a camera. Returns count of deleted files."""
        camera_dir = self._base_path / camera_id
        if not camera_dir.exists():
            return 0
        try:
            count = 0
            for item in camera_dir.rglob("*.mp4"):
                item.unlink()
                count += 1
            shutil.rmtree(str(camera_dir), ignore_errors=True)
            logger.info("Deleted %d recording files for camera %s", count, camera_id)
            return count
        except Exception as e:
            logger.error("Error deleting recordings for camera %s: %s", camera_id, e)
            return 0

    async def cleanup_empty_dirs(self) -> None:
        """Remove empty date directories under each camera directory."""
        try:
            for camera_dir in self._base_path.iterdir():
                if not camera_dir.is_dir():
                    continue
                for date_dir in camera_dir.iterdir():
                    if date_dir.is_dir() and not any(date_dir.iterdir()):
                        date_dir.rmdir()
                if camera_dir.is_dir() and not any(camera_dir.iterdir()):
                    camera_dir.rmdir()
        except Exception as e:
            logger.warning("Error during empty directory cleanup: %s", e)

    def get_storage_usage(self) -> dict:
        """Get total storage usage."""
        total_size = 0
        total_files = 0
        try:
            for mp4_file in self._base_path.rglob("*.mp4"):
                total_size += mp4_file.stat().st_size
                total_files += 1
        except Exception as e:
            logger.warning("Error calculating storage usage: %s", e)
        return {
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "total_files": total_files,
            "base_path": str(self._base_path),
        }

    def generate_thumbnail(self, relative_path: str, time_offset: float = 1.0) -> Optional[Path]:
        """Generate a JPEG thumbnail from a video segment using FFmpeg.

        Args:
            relative_path: Relative path to the video file.
            time_offset: Time offset in seconds to extract the frame.

        Returns:
            Path to the generated thumbnail file, or None on failure.
        """
        import subprocess

        full_path = self.resolve_path(relative_path)
        if not full_path.exists():
            logger.warning("Video file not found for thumbnail: %s", full_path)
            return None

        thumbnail_dir = full_path.parent / ".thumbnails"
        os.makedirs(thumbnail_dir, exist_ok=True)
        thumbnail_path = thumbnail_dir / f"{full_path.stem}_thumb.jpg"

        if thumbnail_path.exists():
            return thumbnail_path

        cmd = [
            'ffmpeg', '-y',
            '-ss', str(time_offset),
            '-i', str(full_path),
            '-vframes', '1',
            '-vf', 'scale=320:-1',
            '-q:v', '3',
            str(thumbnail_path),
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if result.returncode == 0 and thumbnail_path.exists():
                return thumbnail_path
            logger.warning("FFmpeg thumbnail generation failed: %s", result.stderr[:200] if result.stderr else "unknown")
        except FileNotFoundError:
            logger.warning("FFmpeg not found for thumbnail generation")
        except subprocess.TimeoutExpired:
            logger.warning("FFmpeg thumbnail generation timed out")
        except Exception as e:
            logger.error("Error generating thumbnail: %s", e)

        return None

    def detect_video_info(self, relative_path: str) -> Optional[dict]:
        """Detect video codec and resolution information using FFprobe.

        Returns:
            Dict with codec, width, height, duration, or None on failure.
        """
        import subprocess

        full_path = self.resolve_path(relative_path)
        if not full_path.exists():
            return None

        # Check if ffprobe is available
        try:
            subprocess.run(['ffprobe', '-version'], capture_output=True, timeout=5)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            logger.warning("FFprobe not found for video info detection, attempting raw H.265 detection")
            # Fallback: check if file starts with H.265 NAL unit headers
            try:
                with open(str(full_path), 'rb') as f:
                    header = f.read(32)
                # H.265 NAL unit starts with 0x00 0x00 0x00 0x01 followed by NAL type
                # The NAL type for H.265 VPS is 0x40, SPS is 0x42, PPS is 0x44
                if len(header) >= 5:
                    if header[:4] == b'\x00\x00\x00\x01' and (header[4] & 0x7E) in (0x40, 0x42, 0x44):
                        logger.info("Detected raw H.265 stream in file: %s", full_path)
                        return {
                            'codec': 'hevc',
                            'width': 0,
                            'height': 0,
                            'duration': 0,
                        }
            except Exception as e:
                logger.warning("Raw H.265 detection failed: %s", e)
            return None

        cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-select_streams', 'v:0',
            '-show_entries', 'stream=codec_name,width,height,duration',
            '-show_entries', 'format=duration',
            '-of', 'json',
            str(full_path),
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                logger.warning("FFprobe failed: %s", result.stderr[:200] if result.stderr else "unknown")
                return None

            import json
            probe = json.loads(result.stdout)
            stream_info = probe.get('streams', [{}])[0]
            format_info = probe.get('format', {})

            return {
                'codec': stream_info.get('codec_name', 'unknown'),
                'width': stream_info.get('width', 0),
                'height': stream_info.get('height', 0),
                'duration': float(stream_info.get('duration', format_info.get('duration', 0)) or 0),
            }
        except FileNotFoundError:
            logger.warning("FFprobe not found for video info detection")
        except Exception as e:
            logger.error("Error detecting video info: %s", e)

        return None


recording_storage = RecordingStorageManager()
logger.info("[Storage] RecordingStorageManager initialized with base_path: %s", recording_storage.base_path)
