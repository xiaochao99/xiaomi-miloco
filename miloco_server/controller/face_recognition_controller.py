# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
"""
Face recognition REST API (CPU friendly).

Endpoints:
  - POST /api/face/library/enroll
  - GET  /api/face/library/list
  - DELETE /api/face/library/{profile_id}
  - POST /api/face/search
"""

from __future__ import annotations

import base64
import logging
from typing import List

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from miloco_server.face_recognition.face_library_service import FaceLibraryService
from miloco_server.detection.detection_service import get_detection_service, DetectionService
from miloco_server.detection.face_detector import FaceDetector, FaceInfo

logger = logging.getLogger(__name__)

face_recognition_router = APIRouter(prefix="/face", tags=["face"])


async def _ensure_face_detector(
    detection_service: DetectionService,
) -> FaceDetector:
    """
    Ensure we have an initialized face detector.

    Pure remote mode:
    - face inference must come from ai_engine (/face/analyze)
    - if ai_engine is unavailable, we do NOT fall back to local InsightFace
    """
    detector = getattr(detection_service, "_face_detector", None)
    if detector and detector.is_initialized():
        logger.info("[FaceAPI] use detection_service face detector")
        return detector

    # Try to initialize detection service once, then re-check.
    try:
        if not detection_service.is_running():
            logger.info("[FaceAPI] detection service not running, try initialize")
            await detection_service.initialize()
            detector = getattr(detection_service, "_face_detector", None)
            if detector and detector.is_initialized():
                logger.info("[FaceAPI] detection_service face detector initialized")
                return detector
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.exception("[FaceAPI] DetectionService initialize failed while preparing face detector: %s", e)

    raise HTTPException(
        status_code=503,
        detail=(
            "Face recognition service is unavailable because ai_engine face API "
            "is not reachable. Please start the ai_engine container (with /face/analyze), "
            "then restart backend."
        ),
    )


def _decode_image_base64(image_base64: str) -> bytes:
    raw = image_base64
    if "," in raw:
        raw = raw.split(",", 1)[1]
    try:
        decoded = base64.b64decode(raw, validate=True)
        logger.info("[FaceAPI] base64 decoded: bytes=%d", len(decoded))
        return decoded
    except Exception as e:  # pylint: disable=broad-exception-caught
        raise HTTPException(status_code=400, detail=f"Invalid base64 image: {e}") from e


class FaceEnrollRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    image_base64: str


class FaceEnrollResponse(BaseModel):
    success: bool
    id: str
    name: str


class FaceProfileListItem(BaseModel):
    id: str
    name: str


class FaceSearchRequest(BaseModel):
    image_base64: str
    top_k: int = Field(5, ge=1, le=20)
    accept_threshold: float = Field(0.35, ge=-1.0, le=1.0)


class FaceSearchResponse(BaseModel):
    success: bool
    matches: List["FaceMatchItem"]


class FaceMatchItem(BaseModel):
    id: str
    name: str
    score: float


def get_face_library_service() -> FaceLibraryService:
    return FaceLibraryService()


@face_recognition_router.post("/library/enroll")
async def enroll_face(
    request: FaceEnrollRequest,
    face_library: FaceLibraryService = Depends(get_face_library_service),
    detection_service: DetectionService = Depends(get_detection_service),
):
    logger.info("[FaceAPI] enroll request start: name=%s", request.name)
    face_detector = await _ensure_face_detector(detection_service)

    # Analyze image and get embedding from the largest face (by det_score).
    image_bytes = _decode_image_base64(request.image_base64)
    faces: List[FaceInfo] = face_detector.analyze(image_bytes, with_embedding=True)
    logger.info("[FaceAPI] enroll analyze result: faces=%d", len(faces))

    if not faces:
        raise HTTPException(status_code=400, detail="No face detected in the image")

    best = max(faces, key=lambda f: f.det_score)
    logger.info("[FaceAPI] enroll best face score=%.4f bbox=%s", best.det_score, best.bbox_px)
    if best.embedding is None or best.embedding.size == 0:
        raise HTTPException(status_code=400, detail="Failed to extract face embedding")

    result = face_library.enroll(request.name, np.asarray(best.embedding, dtype=np.float32))
    return {
        "code": 0,
        "message": "ok",
        "data": FaceEnrollResponse(success=True, id=result["id"], name=result["name"]).model_dump(),
    }


@face_recognition_router.get("/library/list")
async def list_faces(
    face_library: FaceLibraryService = Depends(get_face_library_service),
):
    profiles = face_library.list_profiles()
    return {
        "code": 0,
        "message": "ok",
        "data": [FaceProfileListItem(**p).model_dump() for p in profiles],
    }


@face_recognition_router.delete("/library/{profile_id}")
async def delete_face_profile(
    profile_id: str,
    face_library: FaceLibraryService = Depends(get_face_library_service),
):
    if not profile_id:
        raise HTTPException(status_code=400, detail="profile_id is required")

    ok = face_library.delete_profile(profile_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Face profile not found")

    return {"code": 0, "message": "ok", "data": {"success": True}}


@face_recognition_router.post("/search")
async def search_faces(
    request: FaceSearchRequest,
    face_library: FaceLibraryService = Depends(get_face_library_service),
    detection_service: DetectionService = Depends(get_detection_service),
):
    logger.info(
        "[FaceAPI] search request start: top_k=%d accept_threshold=%.3f",
        request.top_k,
        request.accept_threshold,
    )
    face_detector = await _ensure_face_detector(detection_service)

    image_bytes = _decode_image_base64(request.image_base64)
    faces: List[FaceInfo] = face_detector.analyze(image_bytes, with_embedding=True)
    logger.info("[FaceAPI] search analyze result: faces=%d", len(faces))

    if not faces:
        raise HTTPException(status_code=400, detail="No face detected in the image")

    # MVP: use the best face embedding.
    best = max(faces, key=lambda f: f.det_score)
    logger.info("[FaceAPI] search best face score=%.4f bbox=%s", best.det_score, best.bbox_px)
    if best.embedding is None or best.embedding.size == 0:
        raise HTTPException(status_code=400, detail="Failed to extract face embedding")

    matches = face_library.search(
        query_embedding=np.asarray(best.embedding, dtype=np.float32),
        top_k=request.top_k,
        accept_threshold=request.accept_threshold,
    )
    logger.info("[FaceAPI] search matches=%d", len(matches))

    data = FaceSearchResponse(
        success=True,
        matches=[FaceMatchItem(id=m.id, name=m.name, score=m.score) for m in matches],
    )
    return {"code": 0, "message": "ok", "data": data.model_dump()}

