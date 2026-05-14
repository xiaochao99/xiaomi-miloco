# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Recording controller for camera recording management API endpoints.
Provides REST API for recording configuration, control, playback, and storage management.
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response, StreamingResponse

from miloco_server.middleware import verify_token
from miloco_server.schema.common_schema import NormalResponse
from miloco_server.schema.recording_schema import (
    RecordingConfig,
    RecordingConfigUpdate,
    RecordingMode,
    RecordingQuery,
    RecordingSegmentListResponse,
    RecordingStatus,
    RecordingStorageStats,
    TimePeriod,
)
from miloco_server.service.recording_service import get_recording_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/recording", tags=["recording"])


@router.get("/config", summary="Get all recording configs", response_model=NormalResponse)
async def get_all_recording_configs(current_user: str = Depends(verify_token)):
    """Get recording configurations for all cameras."""
    try:
        service = get_recording_service()
        configs = service.get_all_configs()
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
        service = get_recording_service()
        config = service.get_config(camera_id)
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
        service = get_recording_service()
        existing = service.get_config(camera_id)
        
        base = existing if existing else None
        enabled = body.get("enabled", base.enabled if base else False)
        mode = body.get("recording_mode", body.get("mode", base.mode if base else "continuous"))
        retention_days = body.get("retention_days", base.retention_days if base else 7)
        segment_duration = body.get("segment_duration", base.segment_duration if base else 300)

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
        )
        logger.info(f"Updating recording config for {camera_id}: enabled={enabled}, mode={mode}")
        success = await service.update_config(config)
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
        service = get_recording_service()
        success = await service.delete_config(camera_id)
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
        service = get_recording_service()
        statuses = service.get_all_statuses()
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
        service = get_recording_service()
        status = service.get_status(camera_id)
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
    mode: Optional[str] = Query(None, description="Filter by recording mode"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size"),
    current_user: str = Depends(verify_token),
):
    """Query recording segments with filters and pagination."""
    try:
        from miloco_server.dao.recording_dao import RecordingSegmentDAO
        segment_dao = RecordingSegmentDAO()
        logger.info(f"[Recording API] Query segments: camera_id={camera_id}, start_time={start_time}, end_time={end_time}")

        if start_time:
            start_dt = datetime.fromisoformat(start_time)
        else:
            start_dt = None

        if end_time:
            end_dt = datetime.fromisoformat(end_time)
        else:
            end_dt = None

        logger.info(f"[Recording API] Parsed datetime: start_dt={start_dt}, end_dt={end_dt}")
        recording_mode = RecordingMode(mode) if mode else None
        segments, total = segment_dao.query(
            camera_id=camera_id,
            start_time=start_dt,
            end_time=end_dt,
            mode=recording_mode,
            page=page,
            page_size=page_size,
        )
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
    except Exception as e:
        logger.error("Failed to query recording segments: %s", e, exc_info=True)
        return NormalResponse(code=1, message=str(e), data=None)


@router.get("/segments/{segment_id}", summary="Get segment detail", response_model=NormalResponse)
async def get_segment_detail(segment_id: str, current_user: str = Depends(verify_token)):
    """Get recording segment detail by ID."""
    try:
        from miloco_server.dao.recording_dao import RecordingSegmentDAO
        segment_dao = RecordingSegmentDAO()
        segment = segment_dao.get_by_id(segment_id)
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


@router.get("/play/{segment_id}", summary="Play recording segment")
async def play_recording_segment(segment_id: str, request: Request):
    """Stream a recording segment file for playback. Supports HTTP Range requests."""
    from miloco_server.dao.recording_dao import RecordingSegmentDAO
    from miloco_server.service.recording_storage import recording_storage

    segment_dao = RecordingSegmentDAO()
    segment = segment_dao.get_by_id(segment_id)
    if not segment:
        raise HTTPException(status_code=404, detail="Recording segment not found")

    full_path = recording_storage.resolve_path(segment.file_path)
    if not full_path.exists():
        raise HTTPException(status_code=404, detail="Recording file not found on disk")

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
        from miloco_server.dao.recording_dao import RecordingSegmentDAO
        from miloco_server.service.recording_storage import recording_storage

        segment_dao = RecordingSegmentDAO()
        segment = segment_dao.get_by_id(segment_id)
        if not segment:
            raise HTTPException(status_code=404, detail="Recording segment not found")

        thumbnail_path = recording_storage.generate_thumbnail(segment.file_path, time_offset=offset)
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
        from miloco_server.dao.recording_dao import RecordingSegmentDAO
        from miloco_server.service.recording_storage import recording_storage

        segment_dao = RecordingSegmentDAO()
        segment = segment_dao.get_by_id(segment_id)
        if not segment:
            raise HTTPException(status_code=404, detail="Recording segment not found")

        video_info = recording_storage.detect_video_info(segment.file_path)
        if not video_info:
            logger.warning("[Recording API] Could not detect video info for segment %s (mode=%s, path=%s)",
                           segment_id, segment.recording_mode, segment.file_path)
            return NormalResponse(code=0, message="Could not detect video info", data=None)

        needs_transcode = video_info.get('codec') in ('hevc', 'h265')
        logger.info("[Recording API] Video info for %s (mode=%s): codec=%s, %sx%s, duration=%.1fs, needs_transcode=%s",
                    segment_id, segment.recording_mode, video_info.get('codec'),
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


@router.get("/transcode/{segment_id}", summary="Transcode and play H.265 as H.264")
async def transcode_segment(segment_id: str, request: Request):
    """Transcode a H.265 segment to H.264 on-the-fly for browser compatibility."""
    import asyncio
    import os
    import shutil
    import subprocess
    import tempfile

    from miloco_server.dao.recording_dao import RecordingSegmentDAO
    from miloco_server.service.recording_storage import recording_storage

    segment_dao = RecordingSegmentDAO()
    segment = segment_dao.get_by_id(segment_id)
    if not segment:
        raise HTTPException(status_code=404, detail="Recording segment not found")

    full_path = recording_storage.resolve_path(segment.file_path)
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


@router.delete("/segments/{segment_id}", summary="Delete recording segment", response_model=NormalResponse)
async def delete_recording_segment(segment_id: str, current_user: str = Depends(verify_token)):
    """Delete a recording segment."""
    try:
        from miloco_server.dao.recording_dao import RecordingSegmentDAO
        from miloco_server.service.recording_storage import recording_storage

        segment_dao = RecordingSegmentDAO()
        segment = segment_dao.get_by_id(segment_id)
        if not segment:
            raise HTTPException(status_code=404, detail="Recording segment not found")
        await recording_storage.delete_segment(segment.file_path)
        segment_dao.delete_by_id(segment_id)
        return NormalResponse(code=0, message="Recording segment deleted successfully", data=None)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete segment %s: %s", segment_id, e, exc_info=True)
        return NormalResponse(code=1, message=str(e), data=None)


@router.post("/segments/batch-delete", summary="Batch delete recording segments", response_model=NormalResponse)
async def batch_delete_recording_segments(request: Request, current_user: str = Depends(verify_token)):
    """Delete multiple recording segments in batch."""
    try:
        body = await request.json()
        segment_ids = body.get("segment_ids", [])
        if not segment_ids or not isinstance(segment_ids, list):
            raise HTTPException(status_code=400, detail="segment_ids must be a non-empty list")

        from miloco_server.dao.recording_dao import RecordingSegmentDAO
        from miloco_server.service.recording_storage import recording_storage

        segment_dao = RecordingSegmentDAO()
        deleted_count = 0
        errors = []

        for segment_id in segment_ids:
            try:
                segment = segment_dao.get_by_id(segment_id)
                if not segment:
                    errors.append(f"Segment {segment_id} not found")
                    continue
                await recording_storage.delete_segment(segment.file_path)
                segment_dao.delete_by_id(segment_id)
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
        service = get_recording_service()
        stats = service.get_storage_stats()
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
        service = get_recording_service()
        deleted_count = await service.manual_cleanup()
        return NormalResponse(
            code=0,
            message=f"Cleanup completed, deleted {deleted_count} expired segments",
            data={"deleted_count": deleted_count},
        )
    except Exception as e:
        logger.error("Failed to trigger cleanup: %s", e, exc_info=True)
        return NormalResponse(code=1, message=str(e), data=None)
