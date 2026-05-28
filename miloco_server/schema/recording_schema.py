# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Recording schema definitions.
Used for camera recording configuration, segments, and playback.
"""

from datetime import datetime
from enum import Enum
from typing import Annotated, List, Optional

from pydantic import BaseModel, Field


class RecordingMode(str, Enum):
    """Recording mode enumeration."""
    CONTINUOUS = "continuous"
    MOTION = "motion"
    PERSON = "person"


class TimePeriod(BaseModel):
    """Time period for recording schedule."""
    start_time: str = Field(..., description="Start time in HH:MM format", pattern=r"^\d{2}:\d{2}$")
    end_time: str = Field(..., description="End time in HH:MM format", pattern=r"^\d{2}:\d{2}$")
    days_of_week: Optional[List[Annotated[int, Field(ge=0, le=6)]]] = Field(
        default=None,
        description="Days of week (0=Monday to 6=Sunday), null means every day",
    )


class RecordingConfig(BaseModel):
    """Recording configuration for a camera."""
    camera_id: str = Field(..., description="Camera device ID")
    enabled: bool = Field(default=False, description="Whether recording is enabled")
    mode: RecordingMode = Field(default=RecordingMode.CONTINUOUS, description="Recording mode")
    schedule_periods: Optional[List[TimePeriod]] = Field(
        default=None,
        description="Recording time periods, null means 24/7"
    )
    retention_days: int = Field(default=7, description="Recording retention days", ge=1, le=365)
    segment_duration: int = Field(default=300, description="Segment duration in seconds", ge=60, le=3600)


class RecordingConfigUpdate(BaseModel):
    """Request model for updating recording configuration."""
    enabled: Optional[bool] = Field(default=None, description="Whether recording is enabled")
    mode: Optional[RecordingMode] = Field(default=None, description="Recording mode")
    schedule_periods: Optional[List[TimePeriod]] = Field(
        default=None,
        description="Recording time periods"
    )
    retention_days: Optional[int] = Field(default=None, description="Recording retention days", ge=1, le=365)
    segment_duration: Optional[int] = Field(default=None, description="Segment duration in seconds", ge=60, le=3600)


class RecordingSegment(BaseModel):
    """Recording segment metadata."""
    id: str = Field(..., description="Segment ID (UUID)")
    camera_id: str = Field(..., description="Camera device ID")
    start_time: datetime = Field(..., description="Recording start time")
    end_time: Optional[datetime] = Field(default=None, description="Recording end time (None if still recording)")
    duration_seconds: int = Field(..., description="Duration in seconds")
    file_path: str = Field(..., description="Relative file path")
    file_size_bytes: int = Field(default=0, description="File size in bytes")
    recording_mode: RecordingMode = Field(..., description="Recording mode when segment was created")
    trigger_event: Optional[str] = Field(default=None, description="Trigger event description")
    created_at: Optional[datetime] = Field(default=None, description="Creation timestamp")
    is_live: bool = Field(default=False, description="Whether this segment is currently being recorded")


class RecordingQuery(BaseModel):
    """Query parameters for recording segments."""
    camera_id: Optional[str] = Field(default=None, description="Filter by camera ID")
    start_time: Optional[datetime] = Field(default=None, description="Filter by start time")
    end_time: Optional[datetime] = Field(default=None, description="Filter by end time")
    mode: Optional[RecordingMode] = Field(default=None, description="Filter by recording mode")
    page: int = Field(default=1, description="Page number", ge=1)
    page_size: int = Field(default=20, description="Page size", ge=1, le=100)


class RecordingSegmentListResponse(BaseModel):
    """Response model for recording segment list."""
    total: int = Field(..., description="Total number of segments")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Page size")
    segments: List[RecordingSegment] = Field(..., description="Recording segments")


class RecordingStatus(BaseModel):
    """Recording status for a camera."""
    camera_id: str = Field(..., description="Camera device ID")
    camera_name: str = Field(default="", description="Camera display name")
    recording_enabled: bool = Field(default=False, description="Whether recording is configured")
    recording_active: bool = Field(default=False, description="Whether recording is currently active")
    mode: Optional[RecordingMode] = Field(default=None, description="Current recording mode")
    current_segment_start: Optional[datetime] = Field(default=None, description="Current segment start time")
    segments_today: int = Field(default=0, description="Number of segments recorded today")
    storage_used_mb: float = Field(default=0.0, description="Storage used in MB")


class RecordingStorageStats(BaseModel):
    """Storage statistics for recordings."""
    total_size_bytes: int = Field(default=0, description="Total storage used in bytes")
    total_size_mb: float = Field(default=0.0, description="Total storage used in MB")
    total_segments: int = Field(default=0, description="Total number of segments")
    per_camera: List[dict] = Field(default_factory=list, description="Per-camera storage stats")
