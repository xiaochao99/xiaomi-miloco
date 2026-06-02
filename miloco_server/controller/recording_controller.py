# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Recording controller for camera recording management API endpoints.
Provides REST API for recording configuration, control, playback, and storage management.

Segment ID format: "{camera_id}:{date}:{filename}"
  e.g., "1180769232:2026-05-28:14-00-00_0001.ts"
Maps to relative file path: "{camera_id}/{date}/{filename}"
"""

import logging
import os
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response, StreamingResponse

from miloco_server.middleware import verify_token
from miloco_server.schema.common_schema import NormalResponse
from miloco_server.schema.recording_schema import (
    RecordingConfig,
    RecordingConfigUpdate,
    RecordingMode,
    RecordingQuery,
    RecordingSegment,
    RecordingSegmentListResponse,
    RecordingStatus,
    RecordingStorageStats,
    TimePeriod,
)
from miloco_server.record_engine import get_record_engine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/recording", tags=["recording"])


# ─── Segment ID helpers ───────────────────────────────────────────────────────

def segment_id_from_path(camera_id: str, date_str: str, filename: str) -> str:
    """Build a segment ID from path components."""
    return f"{camera_id}:{date_str}:{filename}"


def segment_id_to_path(segment_id: str) -> str:
    """Convert segment ID back to relative file path."""
    # Also support URL-encoded IDs (legacy or from frontend encoding)
    decoded = urllib.parse.unquote(segment_id)
    return decoded.replace(":", "/")


def parse_segment_id(segment_id: str) -> Tuple[str, str, str]:
    """Parse segment ID into (camera_id, date_str, filename)."""
    decoded = urllib.parse.unquote(segment_id)
    parts = decoded.split(":", 2)
    if len(parts) != 3:
        raise HTTPException(status_code=400, detail=f"Invalid segment ID format: {segment_id}")
    return parts[0], parts[1], parts[2]


def _resolve_full_path(segment_id: str) -> Path:
    """Resolve a segment ID to a full file system path."""
    engine = get_record_engine()
    relative_path = segment_id_to_path(segment_id)
    return engine._storage.resolve_path(relative_path)


def _segment_from_file(camera_id: str, date_str: str, filename: str, full_path: Path, fast: bool = False) -> Optional[RecordingSegment]:
    """Build a RecordingSegment from a file system path."""
    try:
        stat = full_path.stat()
        file_size = stat.st_size

        # Parse filename: HH-MM-SS_index.ts (legacy) or HH-MM-SS_index_mode.ts (new)
        # mode is: c (continuous), m (motion), p (person)
        name_without_ext = filename.rsplit(".", 1)[0]  # "14-00-00_0001_m"
        parts = name_without_ext.split("_")
        
        if len(parts) >= 3:
            # New format: HH-MM-SS_index_mode
            time_part = parts[0]  # "14-00-00"
            mode_char = parts[-1]  # "c", "m", or "p"
            mode_map = {"c": RecordingMode.CONTINUOUS, "m": RecordingMode.MOTION, "p": RecordingMode.PERSON}
            recording_mode = mode_map.get(mode_char, RecordingMode.CONTINUOUS)
        else:
            # Legacy format: HH-MM-SS_index (no mode indicator)
            time_part = parts[0]  # "14-00-00"
            recording_mode = RecordingMode.CONTINUOUS
        
        # Validate time_part format
        if time_part.count("-") != 2:
            logger.warning("Invalid time format in filename %s: %s", filename, time_part)
            return None
        
        start_time = datetime.fromisoformat(f"{date_str}T{time_part.replace('-', ':')}:00")

        # fast 模式：跳过 ffprobe，仅用文件大小估算时长，大幅加速首屏加载
        # 非 fast 模式：优先用 ffprobe 读取真实视频时长，带缓存
        if fast:
            duration = max(1, round(file_size / (150 * 1024), 1))
        else:
            duration = _detect_duration_from_file(full_path)
            if duration <= 0:
                duration = max(1, round(file_size / (150 * 1024), 1))

        segment_id = segment_id_from_path(camera_id, date_str, filename)
        relative_path = f"{camera_id}/{date_str}/{filename}"

        return RecordingSegment(
            id=segment_id,
            camera_id=camera_id,
            start_time=start_time,
            end_time=start_time + timedelta(seconds=duration),
            duration_seconds=duration,
            file_path=relative_path,
            file_size_bytes=file_size,
            recording_mode=recording_mode,
            created_at=datetime.fromtimestamp(stat.st_mtime),
        )
    except Exception as e:
        logger.warning("Failed to build segment from file %s: %s", full_path, e)
        return None


# ── ffprobe duration cache ─────────────────────────────────────────────────
# key: (str(path), file_mtime) -> duration_seconds
_duration_cache: dict = {}
_DURATION_CACHE_MAX = 2000


def _detect_duration_from_file(full_path: Path) -> float:
    """用 ffprobe 读取视频文件的真实时长（秒），带缓存，失败返回 0。"""
    import json
    import subprocess
    try:
        stat = full_path.stat()
        cache_key = (str(full_path), stat.st_mtime)
        if cache_key in _duration_cache:
            return _duration_cache[cache_key]

        cmd = [
            'ffprobe', '-v', 'quiet',
            '-print_format', 'json',
            '-show_format', '-show_streams',
            str(full_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
        if result.returncode != 0:
            return 0.0
        data = json.loads(result.stdout)
        # 优先从 format.duration 读取
        fmt = data.get('format', {})
        duration = float(fmt.get('duration', 0))
        if duration > 0:
            if len(_duration_cache) >= _DURATION_CACHE_MAX:
                # evict oldest ~25% entries
                keys = list(_duration_cache.keys())
                for k in keys[: len(keys) // 4]:
                    _duration_cache.pop(k, None)
            _duration_cache[cache_key] = duration
            return duration
        # 备选：从视频流读取
        for stream in data.get('streams', []):
            if stream.get('codec_type') == 'video':
                nb_frames = stream.get('nb_frames')
                r_frame_rate = stream.get('r_frame_rate', '')
                if nb_frames and '/' in r_frame_rate:
                    num, den = r_frame_rate.split('/')
                    fps = int(num) / int(den)
                    if fps > 0:
                        d = int(nb_frames) / fps
                        _duration_cache[cache_key] = d
                        return d
        return 0.0
    except FileNotFoundError:
        logger.warning("ffprobe not found, skip duration detection for %s", full_path)
        return 0.0
    except Exception as e:
        logger.warning("Failed to detect duration from %s: %s", full_path, e)
        return 0.0


def scan_segments(
    base_path: Path,
    camera_id: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    page: int = 1,
    page_size: int = 20,
    fast: bool = False,
) -> Tuple[List[RecordingSegment], int]:
    """Scan filesystem for recording segments."""
    segments: List[RecordingSegment] = []

    # Walk through camera/date/file structure
    camera_dirs = [base_path / camera_id] if camera_id else sorted(base_path.iterdir())

    for cam_dir in camera_dirs:
        if not cam_dir.is_dir():
            continue
        cid = cam_dir.name

        for date_dir in sorted(cam_dir.iterdir(), reverse=True):
            if not date_dir.is_dir():
                continue
            date_str = date_dir.name

            # Filter by date range
            if start_time:
                if date_str < start_time.strftime("%Y-%m-%d"):
                    continue
            if end_time:
                if date_str > end_time.strftime("%Y-%m-%d"):
                    continue

            for ts_file in sorted(date_dir.iterdir(), reverse=True):
                if not ts_file.is_file() or not ts_file.suffix == ".ts":
                    continue

                segment = _segment_from_file(cid, date_str, ts_file.name, ts_file, fast=fast)
                if segment:
                    # Filter by time range
                    if start_time and segment.end_time and segment.end_time < start_time:
                        continue
                    if end_time and segment.start_time > end_time:
                        continue
                    segments.append(segment)

    # Sort by start_time descending
    segments.sort(key=lambda s: s.start_time, reverse=True)

    total = len(segments)
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    paged = segments[start_idx:end_idx]

    return paged, total


@router.get("/config", summary="Get all recording configs", response_model=NormalResponse)
async def get_all_recording_configs(current_user: str = Depends(verify_token)):
    """Get recording configurations for all cameras."""
    try:
        engine = get_record_engine()
        configs = engine.get_all_configs()
        return NormalResponse(
            code=0,
            message="Recording configurations retrieved successfully",
            data=[c.model_dump() for c in configs],
        )
    except Exception as e:
        logger.error("Failed to get recording configs: %s", e, exc_info=True)
        return NormalResponse(code=1, message=str(e), data=None)


@router.get("/config/{camera_id}", summary="Get recording config for camera", response_model=NormalResponse)
async def get_recording_config(camera_id: str, current_user: str = Depends(verify_token)):
    """Get recording configuration for a specific camera."""
    try:
        engine = get_record_engine()
        config = engine.get_config(camera_id)
        if not config:
            return NormalResponse(code=0, message="No recording config found", data=None)
        return NormalResponse(
            code=0,
            message="Recording configuration retrieved successfully",
            data=config.model_dump(),
        )
    except Exception as e:
        logger.error("Failed to get recording config for %s: %s", camera_id, e, exc_info=True)
        return NormalResponse(code=1, message=str(e), data=None)


@router.put("/config/{camera_id}", summary="Update recording config", response_model=NormalResponse)
async def update_recording_config(
    camera_id: str,
    request: Request,
    current_user: str = Depends(verify_token),
):
    """Create or update recording configuration for a camera."""
    try:
        body = await request.json()
        logger.info(f"Received recording config update for {camera_id}: {body}")
        engine = get_record_engine()
        existing = engine.get_config(camera_id)
        
        base = existing if existing else None
        enabled = body.get("enabled", base.enabled if base else False)
        mode = body.get("recording_mode", body.get("mode", base.mode if base else "continuous"))
        retention_days = body.get("retention_days", base.retention_days if base else 7)
        segment_duration = body.get("segment_duration", base.segment_duration if base else 300)
        
        # Motion/Person detection settings
        motion_buffer_seconds = body.get("motion_buffer_seconds", base.motion_buffer_seconds if base else 25.0)
        person_buffer_seconds = body.get("person_buffer_seconds", base.person_buffer_seconds if base else 30.0)
        motion_threshold = body.get("motion_threshold", base.motion_threshold if base else 5)
        motion_check_interval = body.get("motion_check_interval", base.motion_check_interval if base else 1.0)

        schedule_periods = body.get("recording_plans", body.get("schedule_periods"))
        if schedule_periods is not None:
            schedule_periods = [TimePeriod(**p) for p in schedule_periods] if schedule_periods else None
        elif base:
            schedule_periods = base.schedule_periods

        config = RecordingConfig(
            camera_id=camera_id,
            enabled=enabled,
            mode=RecordingMode(mode) if isinstance(mode, str) else mode,
            schedule_periods=schedule_periods,
            retention_days=retention_days,
            segment_duration=segment_duration,
            motion_buffer_seconds=motion_buffer_seconds,
            person_buffer_seconds=person_buffer_seconds,
            motion_threshold=motion_threshold,
            motion_check_interval=motion_check_interval,
        )
        logger.info(f"Updating recording config for {camera_id}: enabled={enabled}, mode={mode}, motion_buffer={motion_buffer_seconds}, person_buffer={person_buffer_seconds}")
        success = await engine.update_config(config)
        if success:
            logger.info(f"Recording config updated successfully for {camera_id}")
            return NormalResponse(
                code=0,
                message="Recording configuration updated successfully",
                data=config.model_dump(),
            )
        logger.error(f"Failed to update recording config for {camera_id}")
        return NormalResponse(code=1, message="Failed to update recording configuration", data=None)
    except Exception as e:
        logger.error("Failed to update recording config for %s: %s", camera_id, e, exc_info=True)
        return NormalResponse(code=1, message=str(e), data=None)


@router.delete("/config/{camera_id}", summary="Delete recording config", response_model=NormalResponse)
async def delete_recording_config(camera_id: str, current_user: str = Depends(verify_token)):
    """Delete recording configuration for a camera and stop its recording."""
    try:
        engine = get_record_engine()
        success = await engine.delete_config(camera_id)
        if success:
            return NormalResponse(code=0, message="Recording configuration deleted successfully", data=None)
        return NormalResponse(code=1, message="No recording config found for camera", data=None)
    except Exception as e:
        logger.error("Failed to delete recording config for %s: %s", camera_id, e, exc_info=True)
        return NormalResponse(code=1, message=str(e), data=None)


@router.get("/status", summary="Get all recording statuses", response_model=NormalResponse)
async def get_all_recording_statuses(current_user: str = Depends(verify_token)):
    """Get recording status for all configured cameras."""
    try:
        engine = get_record_engine()
        statuses = engine.get_all_statuses()
        return NormalResponse(
            code=0,
            message="Recording statuses retrieved successfully",
            data=[s.model_dump() for s in statuses],
        )
    except Exception as e:
        logger.error("Failed to get recording statuses: %s", e, exc_info=True)
        return NormalResponse(code=1, message=str(e), data=None)


@router.get("/status/{camera_id}", summary="Get recording status for camera", response_model=NormalResponse)
async def get_recording_status(camera_id: str, current_user: str = Depends(verify_token)):
    """Get recording status for a specific camera."""
    try:
        engine = get_record_engine()
        status = engine.get_status(camera_id)
        if not status:
            return NormalResponse(code=0, message="No recording config found for camera", data=None)
        return NormalResponse(
            code=0,
            message="Recording status retrieved successfully",
            data=status.model_dump(),
        )
    except Exception as e:
        logger.error("Failed to get recording status for %s: %s", camera_id, e, exc_info=True)
        return NormalResponse(code=1, message=str(e), data=None)


@router.get("/segments", summary="Query recording segments", response_model=NormalResponse)
async def query_recording_segments(
    camera_id: Optional[str] = Query(None, description="Filter by camera ID"),
    start_time: Optional[str] = Query(None, description="Filter by start time (e.g., 2026-05-13T00:00:00)"),
    end_time: Optional[str] = Query(None, description="Filter by end time (e.g., 2026-05-13T23:59:59)"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=1000, description="Page size"),
    fast: bool = Query(False, description="Fast mode: skip ffprobe, use file-size estimation for duration"),
    current_user: str = Depends(verify_token),
):
    """Query recording segments. Uses database for fast queries, falls back to filesystem."""
    try:
        from miloco_server.dao.recording_dao import RecordingSegmentDAO
        
        start_dt = datetime.fromisoformat(start_time) if start_time else None
        end_dt = datetime.fromisoformat(end_time) if end_time else None
        
        # Try database query first (fast path)
        try:
            dao = RecordingSegmentDAO()
            segments, total = dao.query(
                camera_id=camera_id,
                start_time=start_dt,
                end_time=end_dt,
                page=page,
                page_size=page_size,
            )
            
            # If database has data, return it
            if total > 0:
                # Repair zero-duration records on-the-fly
                for seg in segments:
                    if seg.duration_seconds <= 0:
                        # Try file_size_bytes estimation first
                        if seg.file_size_bytes > 0:
                            seg.duration_seconds = max(1, round(seg.file_size_bytes / (150 * 1024), 1))
                            seg.end_time = seg.start_time + timedelta(seconds=seg.duration_seconds)
                        else:
                            # file_size_bytes also zero — try to get from filesystem
                            try:
                                engine = get_record_engine()
                                full_path = engine._storage.resolve_path(seg.file_path)
                                if full_path.exists():
                                    file_size = full_path.stat().st_size
                                    seg.duration_seconds = max(1, round(file_size / (150 * 1024), 1))
                                    seg.end_time = seg.start_time + timedelta(seconds=seg.duration_seconds)
                                    seg.file_size_bytes = file_size
                            except Exception:
                                pass
                response = RecordingSegmentListResponse(
                    total=total,
                    page=page,
                    page_size=page_size,
                    segments=segments,
                )
                return NormalResponse(
                    code=0,
                    message="Recording segments retrieved successfully",
                    data=response.model_dump(),
                )
        except Exception as db_error:
            logger.warning("Database query failed, falling back to filesystem: %s", db_error)
        
        # Fallback: filesystem query (slow path)
        engine = get_record_engine()
        base_path = engine._storage.base_path
        
        segments, total = scan_segments(
            base_path=base_path,
            camera_id=camera_id,
            start_time=start_dt,
            end_time=end_dt,
            page=page,
            page_size=page_size,
            fast=fast,
        )

        response = RecordingSegmentListResponse(
            total=total,
            page=page,
            page_size=page_size,
            segments=segments,
        )
        return NormalResponse(
            code=0,
            message="Recording segments retrieved successfully (filesystem)",
            data=response.model_dump(),
        )
    except Exception as e:
        logger.error("Failed to query recording segments: %s", e, exc_info=True)
        return NormalResponse(code=1, message=str(e), data=None)


@router.get("/segments/{segment_id}", summary="Get segment detail", response_model=NormalResponse)
async def get_segment_detail(segment_id: str, current_user: str = Depends(verify_token)):
    """Get recording segment detail by ID (filesystem-based)."""
    try:
        full_path = _resolve_full_path(segment_id)
        if not full_path.exists():
            raise HTTPException(status_code=404, detail="Recording segment not found")

        camera_id, date_str, filename = parse_segment_id(segment_id)
        segment = _segment_from_file(camera_id, date_str, filename, full_path)
        if not segment:
            raise HTTPException(status_code=404, detail="Recording segment not found")

        return NormalResponse(
            code=0,
            message="Recording segment retrieved successfully",
            data=segment.model_dump(),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get segment %s: %s", segment_id, e, exc_info=True)
        return NormalResponse(code=1, message=str(e), data=None)


@router.post("/segments/durations", summary="Batch get accurate durations via ffprobe", response_model=NormalResponse)
async def batch_get_segment_durations(request: Request, current_user: str = Depends(verify_token)):
    """Batch query accurate durations for segments using ffprobe (with cache).

    Accepts a list of segment IDs, returns a map of {segment_id: duration_seconds}.
    Results are cached by (path, mtime), so repeated calls are fast.
    """
    try:
        body = await request.json()
        segment_ids = body.get("segment_ids", [])
        if not segment_ids or not isinstance(segment_ids, list):
            raise HTTPException(status_code=400, detail="segment_ids must be a non-empty list")

        durations = {}
        for segment_id in segment_ids:
            try:
                full_path = _resolve_full_path(segment_id)
                if not full_path.exists():
                    continue
                duration = _detect_duration_from_file(full_path)
                if duration > 0:
                    durations[segment_id] = duration
            except Exception as e:
                logger.warning("Failed to get duration for %s: %s", segment_id, e)

        return NormalResponse(
            code=0,
            message=f"Retrieved durations for {len(durations)}/{len(segment_ids)} segments",
            data=durations,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to batch get durations: %s", e, exc_info=True)
        return NormalResponse(code=1, message=str(e), data=None)


@router.api_route("/play/{segment_id}", methods=["GET", "HEAD"], summary="Play recording segment")
async def play_recording_segment(segment_id: str, request: Request):
    """Stream a recording segment file for playback. Supports HTTP Range requests."""
    full_path = _resolve_full_path(segment_id)
    if not full_path.exists():
        raise HTTPException(status_code=404, detail="Recording file not found on disk")

    if request.method == "HEAD":
        file_size = full_path.stat().st_size
        return Response(status_code=200, headers={
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
            "Content-Type": "video/mp4",
        })

    file_size = full_path.stat().st_size
    range_header = request.headers.get("range")

    if range_header:
        range_spec = range_header.strip().lower()
        if not range_spec.startswith("bytes="):
            raise HTTPException(status_code=416, detail="Invalid Range header")
        range_parts = range_spec[6:].split("-")
        try:
            start = int(range_parts[0]) if range_parts[0] else 0
            end = int(range_parts[1]) if range_parts[1] else file_size - 1
        except ValueError:
            raise HTTPException(status_code=416, detail="Invalid Range values")
        if start >= file_size or end >= file_size or start > end:
            raise HTTPException(status_code=416, detail="Range out of bounds")
        content_length = end - start + 1

        def range_iter():
            with open(str(full_path), "rb") as f:
                f.seek(start)
                remaining = content_length
                chunk_size = 64 * 1024
                while remaining > 0:
                    read_size = min(chunk_size, remaining)
                    chunk = f.read(read_size)
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        return StreamingResponse(
            range_iter(),
            status_code=206,
            media_type="video/mp4",
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(content_length),
            },
        )

    def file_iter():
        with open(str(full_path), "rb") as f:
            chunk_size = 64 * 1024
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                yield chunk

    return StreamingResponse(
        file_iter(),
        media_type="video/mp4",
        headers={
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
        },
    )


@router.get("/thumbnail/{segment_id}", summary="Get recording segment thumbnail")
async def get_segment_thumbnail(
    segment_id: str,
    offset: float = Query(1.0, description="Time offset in seconds for frame extraction"),
):
    """Generate and serve a JPEG thumbnail for a recording segment."""
    try:
        engine = get_record_engine()
        relative_path = segment_id_to_path(segment_id)
        full_path = engine._storage.resolve_path(relative_path)
        if not full_path.exists():
            raise HTTPException(status_code=404, detail="Recording file not found on disk")

        thumbnail_path = engine._storage.generate_thumbnail(relative_path, time_offset=offset)
        if not thumbnail_path or not thumbnail_path.exists():
            raise HTTPException(status_code=404, detail="Thumbnail generation failed")

        return FileResponse(
            path=str(thumbnail_path),
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=86400"},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get thumbnail for %s: %s", segment_id, e, exc_info=True)
        return NormalResponse(code=1, message=str(e), data=None)


@router.get("/info/{segment_id}", summary="Get video info (codec, resolution)")
async def get_segment_video_info(segment_id: str):
    """Detect and return video codec, resolution, and duration info."""
    try:
        engine = get_record_engine()
        relative_path = segment_id_to_path(segment_id)
        full_path = engine._storage.resolve_path(relative_path)
        if not full_path.exists():
            raise HTTPException(status_code=404, detail="Recording file not found on disk")

        video_info = engine._storage.detect_video_info(relative_path)
        if not video_info:
            logger.warning("[Recording API] Could not detect video info for segment %s", segment_id)
            return NormalResponse(code=0, message="Could not detect video info", data=None)

        needs_transcode = video_info.get('codec') in ('hevc', 'h265')
        logger.info("[Recording API] Video info for %s: codec=%s, %sx%s, duration=%.1fs, needs_transcode=%s",
                    segment_id, video_info.get('codec'),
                    video_info.get('width', 0), video_info.get('height', 0),
                    video_info.get('duration', 0), needs_transcode)

        return NormalResponse(
            code=0,
            message="Video info retrieved successfully",
            data={
                **video_info,
                "needs_transcode": needs_transcode,
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get video info for %s: %s", segment_id, e, exc_info=True)
        return NormalResponse(code=1, message=str(e), data=None)


@router.api_route("/transcode/{segment_id}", methods=["GET", "HEAD"], summary="Transcode and play H.265 as H.264")
async def transcode_segment(segment_id: str, request: Request):
    """Transcode a H.265 segment to H.264 on-the-fly for browser compatibility."""
    if request.method == "HEAD":
        full_path = _resolve_full_path(segment_id)
        if not full_path.exists():
            raise HTTPException(status_code=404, detail="Recording file not found on disk")
        return Response(status_code=200, headers={"Accept-Ranges": "bytes", "Content-Type": "video/mp4"})

    import asyncio
    import os
    import shutil
    import subprocess
    import tempfile

    full_path = _resolve_full_path(segment_id)
    if not full_path.exists():
        raise HTTPException(status_code=404, detail="Recording file not found on disk")

    def run_transcode():
        cmd = [
            'ffmpeg', '-y',
            '-i', str(full_path),
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-crf', '23',
            '-movflags', '+faststart',
            '-f', 'mp4',
            str(output_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise Exception(f"Transcode failed: {result.stderr[:200]}")

    tmp_dir = tempfile.mkdtemp(prefix='miloco_transcode_')
    output_path = Path(tmp_dir) / f"{segment_id}_h264.mp4"

    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, run_transcode)

        if not output_path.exists():
            raise HTTPException(status_code=500, detail="Transcode output file not found")

        file_size = output_path.stat().st_size

        def file_iter():
            try:
                with open(str(output_path), "rb") as f:
                    chunk_size = 64 * 1024
                    while True:
                        chunk = f.read(chunk_size)
                        if not chunk:
                            break
                        yield chunk
            finally:
                # Clean up temp directory after streaming is complete
                try:
                    shutil.rmtree(tmp_dir, ignore_errors=True)
                except Exception:
                    pass

        return StreamingResponse(
            file_iter(),
            media_type="video/mp4",
            headers={
                "Accept-Ranges": "bytes",
                "Content-Length": str(file_size),
            },
        )
    except HTTPException:
        # Clean up on HTTP error
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise
    except Exception as e:
        # Clean up on other errors
        shutil.rmtree(tmp_dir, ignore_errors=True)
        logger.error("Failed to transcode %s: %s", segment_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Transcode failed: {str(e)}")


@router.get(
    "/hls/{segment_id}/index.m3u8",
    summary="Get HLS playlist for recording segment",
    response_class=Response,
)
async def get_hls_playlist(segment_id: str):
    """Generate an HLS VOD playlist wrapping a single recording segment for hls.js playback."""
    import math

    full_path = _resolve_full_path(segment_id)
    if not full_path.exists():
        raise HTTPException(status_code=404, detail="Segment file not found")

    # 用 ffprobe 读取真实视频时长，不再按文件大小估算（避免 20fps 视频时长偏差）
    duration = _detect_duration_from_file(full_path)
    if duration <= 0:
        file_size = full_path.stat().st_size
        duration = max(1, int(file_size / (150 * 1024)))  # fallback
    target_duration = max(1, math.ceil(duration))

    # Use absolute path to avoid relative URL ambiguity in hls.js
    encoded_id = urllib.parse.quote(segment_id, safe='')
    playlist = (
        "#EXTM3U\n"
        "#EXT-X-VERSION:3\n"
        f"#EXT-X-TARGETDURATION:{target_duration}\n"
        "#EXT-X-MEDIA-SEQUENCE:0\n"
        f"#EXTINF:{duration:.3f},\n"
        f"/api/recording/play/{encoded_id}\n"
        "#EXT-X-ENDLIST\n"
    )

    return Response(
        content=playlist,
        media_type="application/vnd.apple.mpegurl",
        headers={
            "Cache-Control": "no-cache",
            "Access-Control-Allow-Origin": "*",
        },
    )


@router.delete("/segments/{segment_id}", summary="Delete recording segment", response_model=NormalResponse)
async def delete_recording_segment(segment_id: str, current_user: str = Depends(verify_token)):
    """Delete a recording segment file from disk."""
    try:
        engine = get_record_engine()
        relative_path = segment_id_to_path(segment_id)
        full_path = engine._storage.resolve_path(relative_path)
        if not full_path.exists():
            raise HTTPException(status_code=404, detail="Recording segment not found")
        
        await engine._storage.delete_segment(relative_path)
        return NormalResponse(code=0, message="Recording segment deleted successfully", data=None)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete segment %s: %s", segment_id, e, exc_info=True)
        return NormalResponse(code=1, message=str(e), data=None)


@router.post("/segments/batch-delete", summary="Batch delete recording segments", response_model=NormalResponse)
async def batch_delete_recording_segments(request: Request, current_user: str = Depends(verify_token)):
    """Delete multiple recording segment files from disk."""
    try:
        body = await request.json()
        segment_ids = body.get("segment_ids", [])
        if not segment_ids or not isinstance(segment_ids, list):
            raise HTTPException(status_code=400, detail="segment_ids must be a non-empty list")

        engine = get_record_engine()
        deleted_count = 0
        errors = []

        for segment_id in segment_ids:
            try:
                relative_path = segment_id_to_path(segment_id)
                full_path = engine._storage.resolve_path(relative_path)
                if not full_path.exists():
                    errors.append(f"Segment file not found: {segment_id}")
                    continue
                await engine._storage.delete_segment(relative_path)
                deleted_count += 1
            except Exception as e:
                errors.append(f"Failed to delete {segment_id}: {str(e)}")
                logger.error("Failed to delete segment %s: %s", segment_id, e, exc_info=True)

        return NormalResponse(
            code=0,
            message=f"Successfully deleted {deleted_count} segments" + (f", {len(errors)} errors" if errors else ""),
            data={"deleted_count": deleted_count, "errors": errors},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to batch delete segments: %s", e, exc_info=True)
        return NormalResponse(code=1, message=str(e), data=None)


@router.get("/storage", summary="Get storage stats", response_model=NormalResponse)
async def get_storage_stats(current_user: str = Depends(verify_token)):
    """Get recording storage statistics."""
    try:
        engine = get_record_engine()
        stats = engine.get_storage_stats()
        return NormalResponse(
            code=0,
            message="Storage statistics retrieved successfully",
            data=stats.model_dump(),
        )
    except Exception as e:
        logger.error("Failed to get storage stats: %s", e, exc_info=True)
        return NormalResponse(code=1, message=str(e), data=None)


@router.post("/cleanup", summary="Trigger manual cleanup", response_model=NormalResponse)
async def trigger_cleanup(current_user: str = Depends(verify_token)):
    """Manually trigger cleanup of expired recording segments."""
    try:
        engine = get_record_engine()
        deleted_count = await engine.manual_cleanup()
        return NormalResponse(
            code=0,
            message=f"Cleanup completed, deleted {deleted_count} expired segments",
            data={"deleted_count": deleted_count},
        )
    except Exception as e:
        logger.error("Failed to trigger cleanup: %s", e, exc_info=True)
        return NormalResponse(code=1, message=str(e), data=None)
