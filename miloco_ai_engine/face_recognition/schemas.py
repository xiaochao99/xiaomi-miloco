# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Pydantic models for face HTTP API."""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class FaceAnalyzeRequest(BaseModel):
    image_base64: str = Field(..., description="Base64 image (optionally data URL)")
    with_embedding: bool = Field(False, description="Return face embeddings")
    min_face_score: float = Field(0.1, ge=0.0, le=1.0)
    max_faces: int = Field(10, ge=1, le=32)


class FaceItem(BaseModel):
    bbox_px: List[int]
    bbox_norm: List[float]
    det_score: float
    embedding: Optional[List[float]] = None


class FaceAnalyzeResponse(BaseModel):
    success: bool = True
    faces: List[FaceItem] = Field(default_factory=list)
    provider: str = Field("cpu", description="FACE_INFERENCE_PROVIDER value")
    timings_ms: Optional[Dict[str, float]] = Field(
        default=None,
        description="Breakdown timings (ms) for decode/detect/embedding/postprocess",
    )
    message: Optional[str] = None
