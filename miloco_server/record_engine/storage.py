# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
StorageManager - Recording storage management.

Handles:
- Directory structure management
- File cleanup and retention
- Storage statistics
- Thumbnail generation
"""

import asyncio
import logging
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class StorageManager:
    """Manages recording file storage on disk."""
    
    def __init__(self, base_path: Path, retention_days: int = 7):
        self.base_path = base_path
        self.retention_days = retention_days
        
        # Create base directory
        os.makedirs(self.base_path, exist_ok=True)
        
        logger.info("[StorageManager] Initialized with base_path: %s, retention: %d days", 
                   self.base_path, self.retention_days)
    
    def get_camera_dir(self, camera_id: str, date: Optional[datetime] = None) -> Path:
        """Get directory for camera recordings."""
        dt = date or datetime.now()
        date_dir = dt.strftime("%Y-%m-%d")
        camera_dir = self.base_path / camera_id / date_dir
        os.makedirs(camera_dir, exist_ok=True)
        return camera_dir
    
    def get_relative_path(self, full_path: Path) -> str:
        """Get relative path from base_path."""
        try:
            return str(full_path.relative_to(self.base_path))
        except ValueError:
            return str(full_path)
    
    def resolve_path(self, relative_path: str) -> Path:
        """Resolve a relative path to a full path."""
        return self.base_path / relative_path
    
    async def delete_file(self, relative_path: str) -> bool:
        """Delete a recording file."""
        full_path = self.resolve_path(relative_path)
        if not full_path.exists():
            return True
        
        try:
            await asyncio.to_thread(os.remove, str(full_path))
            logger.info("[StorageManager] Deleted file: %s", relative_path)
            return True
        except Exception as e:
            logger.error("[StorageManager] Error deleting file %s: %s", relative_path, e)
            return False
    
    async def delete_camera_recordings(self, camera_id: str) -> int:
        """Delete all recordings for a camera. Returns count of deleted files."""
        camera_dir = self.base_path / camera_id
        if not camera_dir.exists():
            return 0
        
        try:
            count = 0
            for item in camera_dir.rglob("*.ts"):
                item.unlink()
                count += 1
            for item in camera_dir.rglob("*.mp4"):
                item.unlink()
                count += 1
            shutil.rmtree(str(camera_dir), ignore_errors=True)
            logger.info("[StorageManager] Deleted %d files for camera %s", count, camera_id)
            return count
        except Exception as e:
            logger.error("[StorageManager] Error deleting recordings for camera %s: %s", camera_id, e)
            return 0
    
    async def cleanup_expired(self) -> int:
        """Clean up expired recordings. Returns count of deleted files."""
        if self.retention_days <= 0:
            return 0
        
        cutoff_date = datetime.now() - timedelta(days=self.retention_days)
        cutoff_str = cutoff_date.strftime("%Y-%m-%d")
        
        total_deleted = 0
        
        try:
            # Iterate through camera directories
            for camera_dir in self.base_path.iterdir():
                if not camera_dir.is_dir():
                    continue
                
                # Iterate through date directories
                for date_dir in camera_dir.iterdir():
                    if not date_dir.is_dir():
                        continue
                    
                    # Check if date is before cutoff
                    dir_name = date_dir.name  # e.g., "2026-05-27"
                    if dir_name < cutoff_str:
                        # Delete all files in this directory
                        for file in date_dir.iterdir():
                            if file.is_file():
                                file.unlink()
                                total_deleted += 1
                        
                        # Remove empty directory
                        try:
                            date_dir.rmdir()
                        except OSError:
                            pass
                
                # Remove empty camera directory
                try:
                    if not any(camera_dir.iterdir()):
                        camera_dir.rmdir()
                except OSError:
                    pass
            
            if total_deleted > 0:
                logger.info("[StorageManager] Cleaned up %d expired recording files", total_deleted)
            
            return total_deleted
            
        except Exception as e:
            logger.error("[StorageManager] Error during cleanup: %s", e)
            return 0
    
    async def cleanup_empty_dirs(self) -> None:
        """Remove empty date directories under each camera directory."""
        try:
            for camera_dir in self.base_path.iterdir():
                if not camera_dir.is_dir():
                    continue
                for date_dir in camera_dir.iterdir():
                    if date_dir.is_dir() and not any(date_dir.iterdir()):
                        date_dir.rmdir()
                if camera_dir.is_dir() and not any(camera_dir.iterdir()):
                    camera_dir.rmdir()
        except Exception as e:
            logger.warning("[StorageManager] Error during empty directory cleanup: %s", e)
    
    def get_storage_usage(self) -> dict:
        """Get total storage usage."""
        total_size = 0
        total_files = 0
        
        try:
            for file in self.base_path.rglob("*.ts"):
                total_size += file.stat().st_size
                total_files += 1
            for file in self.base_path.rglob("*.mp4"):
                total_size += file.stat().st_size
                total_files += 1
        except Exception as e:
            logger.warning("[StorageManager] Error calculating storage usage: %s", e)
        
        return {
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "total_files": total_files,
            "base_path": str(self.base_path),
        }
    
    def get_per_camera_stats(self) -> List[dict]:
        """Get storage statistics per camera."""
        stats = []
        
        try:
            for camera_dir in self.base_path.iterdir():
                if not camera_dir.is_dir():
                    continue
                
                camera_id = camera_dir.name
                total_size = 0
                total_files = 0
                earliest = None
                latest = None
                
                for file in camera_dir.rglob("*.ts"):
                    total_size += file.stat().st_size
                    total_files += 1
                    mtime = datetime.fromtimestamp(file.stat().st_mtime)
                    if earliest is None or mtime < earliest:
                        earliest = mtime
                    if latest is None or mtime > latest:
                        latest = mtime
                
                for file in camera_dir.rglob("*.mp4"):
                    total_size += file.stat().st_size
                    total_files += 1
                    mtime = datetime.fromtimestamp(file.stat().st_mtime)
                    if earliest is None or mtime < earliest:
                        earliest = mtime
                    if latest is None or mtime > latest:
                        latest = mtime
                
                if total_files > 0:
                    stats.append({
                        "camera_id": camera_id,
                        "total_files": total_files,
                        "total_size_bytes": total_size,
                        "total_size_mb": round(total_size / (1024 * 1024), 2),
                        "earliest_recording": earliest.isoformat() if earliest else None,
                        "latest_recording": latest.isoformat() if latest else None,
                    })
        except Exception as e:
            logger.warning("[StorageManager] Error getting per-camera stats: %s", e)
        
        return sorted(stats, key=lambda x: x["total_size_bytes"], reverse=True)
    
    def get_file_size(self, relative_path: str) -> int:
        """Get the file size of a recording."""
        full_path = self.resolve_path(relative_path)
        if not full_path.exists():
            return 0
        return full_path.stat().st_size
    
    def file_exists(self, relative_path: str) -> bool:
        """Check if a recording file exists."""
        full_path = self.resolve_path(relative_path)
        return full_path.exists()
    
    async def delete_segment(self, relative_path: str) -> bool:
        """Delete a recording segment file. Alias for delete_file."""
        return await self.delete_file(relative_path)
    
    def generate_thumbnail(self, relative_path: str, time_offset: float = 1.0) -> Optional[Path]:
        """Generate a JPEG thumbnail from a recording segment."""
        import subprocess
        import tempfile
        
        full_path = self.resolve_path(relative_path)
        if not full_path.exists():
            logger.error("[StorageManager] File not found for thumbnail: %s", relative_path)
            return None
        
        # Create thumbnail in same directory as source
        thumb_dir = full_path.parent / ".thumbs"
        os.makedirs(thumb_dir, exist_ok=True)
        
        thumb_name = full_path.stem + f"_thumb_{int(time_offset)}s.jpg"
        thumb_path = thumb_dir / thumb_name
        
        # Skip if thumbnail already exists
        if thumb_path.exists():
            return thumb_path
        
        try:
            cmd = [
                'ffmpeg', '-y',
                '-ss', str(time_offset),
                '-i', str(full_path),
                '-vframes', '1',
                '-vf', 'scale=320:-1',
                '-q:v', '3',
                str(thumb_path),
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                logger.error("[StorageManager] Thumbnail generation failed: %s", result.stderr[:200])
                return None
            
            return thumb_path
        except Exception as e:
            logger.error("[StorageManager] Error generating thumbnail: %s", e)
            return None
    
    def detect_video_info(self, relative_path: str) -> Optional[dict]:
        """Detect video codec, resolution, and duration from a recording file."""
        import json
        import subprocess
        
        full_path = self.resolve_path(relative_path)
        if not full_path.exists():
            logger.error("[StorageManager] File not found for video info: %s", relative_path)
            return None
        
        try:
            cmd = [
                'ffprobe',
                '-v', 'quiet',
                '-print_format', 'json',
                '-show_format',
                '-show_streams',
                str(full_path),
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                logger.error("[StorageManager] ffprobe failed: %s", result.stderr[:200])
                return None
            
            data = json.loads(result.stdout)
            
            video_info = {
                'codec': None,
                'width': 0,
                'height': 0,
                'duration': 0.0,
                'bitrate': 0,
                'fps': None,
            }
            
            # Extract video stream info
            for stream in data.get('streams', []):
                if stream.get('codec_type') == 'video':
                    video_info['codec'] = stream.get('codec_name')
                    video_info['width'] = stream.get('width', 0)
                    video_info['height'] = stream.get('height', 0)
                    
                    # Parse FPS from r_frame_rate (e.g., "15/1" or "30000/1001")
                    r_frame_rate = stream.get('r_frame_rate', '')
                    if '/' in r_frame_rate:
                        num, den = r_frame_rate.split('/')
                        try:
                            video_info['fps'] = round(int(num) / int(den), 2)
                        except (ValueError, ZeroDivisionError):
                            pass
                    break
            
            # Extract duration from format
            format_info = data.get('format', {})
            video_info['duration'] = float(format_info.get('duration', 0))
            video_info['bitrate'] = int(format_info.get('bit_rate', 0))
            
            return video_info
            
        except Exception as e:
            logger.error("[StorageManager] Error detecting video info: %s", e)
            return None
