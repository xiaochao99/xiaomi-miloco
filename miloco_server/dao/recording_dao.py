# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Recording data access objects.
Handles CRUD operations for recording_config and recording_segments tables.
"""

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from miloco_server.schema.recording_schema import (
    RecordingConfig,
    RecordingMode,
    RecordingSegment,
    TimePeriod,
)
from miloco_server.utils.database import get_db_connector

logger = logging.getLogger(__name__)


class RecordingConfigDAO:
    """Recording configuration data access object."""

    def __init__(self):
        self.db_connector = get_db_connector()

    def _row_to_config(self, row: Dict[str, Any]) -> RecordingConfig:
        """Convert database row to RecordingConfig."""
        schedule_periods = None
        if row.get("schedule_periods"):
            try:
                periods_data = json.loads(row["schedule_periods"])
                schedule_periods = [TimePeriod(**p) for p in periods_data]
            except (json.JSONDecodeError, TypeError):
                schedule_periods = None
        return RecordingConfig(
            camera_id=row["camera_id"],
            enabled=bool(row["enabled"]),
            mode=RecordingMode(row["mode"]),
            schedule_periods=schedule_periods,
            retention_days=row["retention_days"],
            segment_duration=row.get("segment_duration", 300),
            motion_buffer_seconds=row.get("motion_buffer_seconds", 25.0),
            person_buffer_seconds=row.get("person_buffer_seconds", 30.0),
            motion_threshold=row.get("motion_threshold", 5),
            motion_check_interval=row.get("motion_check_interval", 1.0),
        )

    def get_by_camera_id(self, camera_id: str) -> Optional[RecordingConfig]:
        """Get recording config for a camera."""
        sql = "SELECT * FROM recording_config WHERE camera_id = ?"
        rows = self.db_connector.execute_query(sql, (camera_id,))
        if not rows:
            return None
        return self._row_to_config(rows[0])

    def get_all(self) -> List[RecordingConfig]:
        """Get all recording configs."""
        sql = "SELECT * FROM recording_config ORDER BY camera_id"
        rows = self.db_connector.execute_query(sql)
        return [self._row_to_config(row) for row in rows]

    def get_enabled(self) -> List[RecordingConfig]:
        """Get all enabled recording configs."""
        sql = "SELECT * FROM recording_config WHERE enabled = 1 ORDER BY camera_id"
        rows = self.db_connector.execute_query(sql)
        return [self._row_to_config(row) for row in rows]

    def upsert(self, config: RecordingConfig) -> bool:
        """Create or update recording config."""
        schedule_json = None
        if config.schedule_periods:
            schedule_json = json.dumps([p.model_dump() for p in config.schedule_periods])

        now = datetime.now().isoformat()
        sql = """
            INSERT INTO recording_config (camera_id, enabled, mode, schedule_periods, retention_days, segment_duration, 
                                          motion_buffer_seconds, person_buffer_seconds, motion_threshold, motion_check_interval,
                                          created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(camera_id) DO UPDATE SET
                enabled = excluded.enabled,
                mode = excluded.mode,
                schedule_periods = excluded.schedule_periods,
                retention_days = excluded.retention_days,
                segment_duration = excluded.segment_duration,
                motion_buffer_seconds = excluded.motion_buffer_seconds,
                person_buffer_seconds = excluded.person_buffer_seconds,
                motion_threshold = excluded.motion_threshold,
                motion_check_interval = excluded.motion_check_interval,
                updated_at = excluded.updated_at
        """
        params = (
            config.camera_id,
            config.enabled,
            config.mode.value,
            schedule_json,
            config.retention_days,
            config.segment_duration,
            config.motion_buffer_seconds,
            config.person_buffer_seconds,
            config.motion_threshold,
            config.motion_check_interval,
            now,
            now,
        )
        try:
            self.db_connector.execute_update(sql, params)
            return True
        except Exception as e:
            logger.error("Error upserting recording config for camera %s: %s", config.camera_id, e)
            return False

    def delete(self, camera_id: str) -> bool:
        """Delete recording config."""
        sql = "DELETE FROM recording_config WHERE camera_id = ?"
        try:
            affected = self.db_connector.execute_update(sql, (camera_id,))
            return affected > 0
        except Exception as e:
            logger.error("Error deleting recording config for camera %s: %s", camera_id, e)
            return False


class RecordingSegmentDAO:
    """Recording segment data access object."""

    def __init__(self):
        self.db_connector = get_db_connector()

    def _row_to_segment(self, row: Dict[str, Any]) -> RecordingSegment:
        """Convert database row to RecordingSegment."""
        return RecordingSegment(
            id=row["id"],
            camera_id=row["camera_id"],
            start_time=datetime.fromisoformat(row["start_time"]) if isinstance(row["start_time"], str) else row["start_time"],
            end_time=datetime.fromisoformat(row["end_time"]) if isinstance(row["end_time"], str) else row["end_time"],
            duration_seconds=row["duration_seconds"],
            file_path=row["file_path"],
            file_size_bytes=row.get("file_size_bytes", 0),
            recording_mode=RecordingMode(row["recording_mode"]),
            trigger_event=row.get("trigger_event"),
            created_at=datetime.fromisoformat(row["created_at"]) if isinstance(row.get("created_at"), str) else row.get("created_at", datetime.now()),
        )

    def _to_naive(self, dt: datetime) -> datetime:
        """Convert datetime to naive datetime for SQLite storage."""
        if dt.tzinfo:
            return dt.replace(tzinfo=None)
        return dt

    def create(self, segment: RecordingSegment) -> Optional[str]:
        """Create a new recording segment record."""
        if not segment.id:
            segment.id = str(uuid.uuid4())
        sql = """
            INSERT INTO recording_segments
            (id, camera_id, start_time, end_time, duration_seconds, file_path, file_size_bytes, recording_mode, trigger_event, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        # Convert to naive datetime for SQLite storage
        start_time = self._to_naive(segment.start_time) if isinstance(segment.start_time, datetime) else segment.start_time
        end_time = self._to_naive(segment.end_time) if isinstance(segment.end_time, datetime) else segment.end_time
        created_at = self._to_naive(segment.created_at) if isinstance(segment.created_at, datetime) else segment.created_at
        
        params = (
            segment.id,
            segment.camera_id,
            start_time.isoformat() if isinstance(start_time, datetime) else start_time,
            end_time.isoformat() if isinstance(end_time, datetime) else end_time,
            segment.duration_seconds,
            segment.file_path,
            segment.file_size_bytes,
            segment.recording_mode.value,
            segment.trigger_event,
            created_at.isoformat() if isinstance(created_at, datetime) else created_at,
        )
        try:
            self.db_connector.execute_update(sql, params)
            return segment.id
        except Exception as e:
            logger.error("Error creating recording segment: %s", e)
            return None

    def get_by_id(self, segment_id: str) -> Optional[RecordingSegment]:
        """Get recording segment by ID."""
        sql = "SELECT * FROM recording_segments WHERE id = ?"
        rows = self.db_connector.execute_query(sql, (segment_id,))
        if not rows:
            return None
        return self._row_to_segment(rows[0])

    def query(
        self,
        camera_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        mode: Optional[RecordingMode] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[RecordingSegment], int]:
        """Query recording segments with filters and pagination."""
        conditions = []
        params = []

        if camera_id:
            conditions.append("camera_id = ?")
            params.append(camera_id)
        if start_time:
            # Convert to naive datetime for comparison
            start_dt = self._to_naive(start_time) if isinstance(start_time, datetime) else start_time
            conditions.append("start_time >= ?")
            params.append(start_dt.isoformat() if isinstance(start_dt, datetime) else start_dt)
        if end_time:
            # Convert to naive datetime for comparison
            end_dt = self._to_naive(end_time) if isinstance(end_time, datetime) else end_time
            conditions.append("end_time <= ?")
            params.append(end_dt.isoformat() if isinstance(end_dt, datetime) else end_dt)
        if mode:
            conditions.append("recording_mode = ?")
            params.append(mode.value)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        count_sql = f"SELECT COUNT(*) as total FROM recording_segments WHERE {where_clause}"
        count_rows = self.db_connector.execute_query(count_sql, tuple(params))
        total = count_rows[0]["total"] if count_rows else 0

        offset = (page - 1) * page_size
        query_sql = f"""
            SELECT * FROM recording_segments
            WHERE {where_clause}
            ORDER BY start_time DESC
            LIMIT ? OFFSET ?
        """
        query_params = tuple(params) + (page_size, offset)
        rows = self.db_connector.execute_query(query_sql, query_params)
        segments = [self._row_to_segment(row) for row in rows]

        return segments, total

    def get_expired(self, retention_days: int) -> List[RecordingSegment]:
        """Get segments older than retention_days."""
        cutoff = (datetime.now() - timedelta(days=retention_days)).isoformat()
        sql = "SELECT * FROM recording_segments WHERE start_time < ? ORDER BY start_time"
        rows = self.db_connector.execute_query(sql, (cutoff,))
        return [self._row_to_segment(row) for row in rows]

    def delete_expired(self, retention_days: int) -> int:
        """Delete segments older than retention_days. Returns count of deleted rows."""
        cutoff = (datetime.now() - timedelta(days=retention_days)).isoformat()
        sql = "DELETE FROM recording_segments WHERE start_time < ?"
        try:
            affected = self.db_connector.execute_update(sql, (cutoff,))
            logger.info("Deleted %d expired recording segments (retention=%d days)", affected, retention_days)
            return affected
        except Exception as e:
            logger.error("Error deleting expired recording segments: %s", e)
            return 0

    def delete_by_id(self, segment_id: str) -> bool:
        """Delete a recording segment by ID."""
        sql = "DELETE FROM recording_segments WHERE id = ?"
        try:
            affected = self.db_connector.execute_update(sql, (segment_id,))
            return affected > 0
        except Exception as e:
            logger.error("Error deleting recording segment %s: %s", segment_id, e)
            return False

    def delete_by_camera_id(self, camera_id: str) -> int:
        """Delete all segments for a camera."""
        sql = "DELETE FROM recording_segments WHERE camera_id = ?"
        try:
            return self.db_connector.execute_update(sql, (camera_id,))
        except Exception as e:
            logger.error("Error deleting recording segments for camera %s: %s", camera_id, e)
            return 0

    def update_file_size(self, segment_id: str, file_size_bytes: int) -> bool:
        """Update the file size for a segment."""
        sql = "UPDATE recording_segments SET file_size_bytes = ? WHERE id = ?"
        try:
            self.db_connector.execute_update(sql, (file_size_bytes, segment_id))
            return True
        except Exception as e:
            logger.error("Error updating file size for segment %s: %s", segment_id, e)
            return False

    def get_storage_stats(self, camera_id: Optional[str] = None) -> Dict[str, Any]:
        """Get storage statistics."""
        if camera_id:
            sql = """
                SELECT
                    COUNT(*) as total_segments,
                    COALESCE(SUM(file_size_bytes), 0) as total_size_bytes,
                    COALESCE(SUM(duration_seconds), 0) as total_duration_seconds
                FROM recording_segments WHERE camera_id = ?
            """
            rows = self.db_connector.execute_query(sql, (camera_id,))
        else:
            sql = """
                SELECT
                    COUNT(*) as total_segments,
                    COALESCE(SUM(file_size_bytes), 0) as total_size_bytes,
                    COALESCE(SUM(duration_seconds), 0) as total_duration_seconds
                FROM recording_segments
            """
            rows = self.db_connector.execute_query(sql)

        if not rows:
            return {"total_segments": 0, "total_size_bytes": 0, "total_duration_seconds": 0}

        return dict(rows[0])

    def get_per_camera_stats(self) -> List[Dict[str, Any]]:
        """Get storage statistics per camera."""
        sql = """
            SELECT
                camera_id,
                COUNT(*) as segment_count,
                COALESCE(SUM(file_size_bytes), 0) as total_size_bytes,
                COALESCE(SUM(duration_seconds), 0) as total_duration_seconds,
                MIN(start_time) as earliest_recording,
                MAX(end_time) as latest_recording
            FROM recording_segments
            GROUP BY camera_id
            ORDER BY total_size_bytes DESC
        """
        rows = self.db_connector.execute_query(sql)
        return [dict(row) for row in rows]
