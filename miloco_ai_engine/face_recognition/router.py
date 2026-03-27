# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""FastAPI routes for face recognition."""

from __future__ import annotations

import base64
import logging
import os

from fastapi import APIRouter, HTTPException

from miloco_ai_engine.face_recognition.schemas import FaceAnalyzeRequest, FaceAnalyzeResponse, FaceItem
from miloco_ai_engine.face_recognition.service import get_face_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/face", tags=["face"])


def _decode_b64(image_base64: str) -> bytes:
    raw = image_base64
    if "," in raw:
        raw = raw.split(",", 1)[1]
    try:
        return base64.b64decode(raw, validate=True)
    except Exception as e:  # pylint: disable=broad-exception-caught
        raise HTTPException(status_code=400, detail=f"Invalid base64: {e}") from e


@router.get("/health")
async def face_health():
    """Lightweight readiness probe (does not load models)."""
    svc = get_face_service()
    return {
        "enabled": os.getenv("FACE_SERVICE_ENABLED", "true").lower() in ("1", "true", "yes"),
        "ready": svc.is_ready(),
        "provider": os.getenv("FACE_INFERENCE_PROVIDER", "cpu"),
        "error": svc.last_error(),
    }


@router.post("/analyze", response_model=FaceAnalyzeResponse)
async def face_analyze(req: FaceAnalyzeRequest):
    """Detect faces and optionally extract embeddings."""
    if os.getenv("FACE_SERVICE_ENABLED", "true").lower() in ("0", "false", "no"):
        raise HTTPException(status_code=503, detail="Face service disabled")

    svc = get_face_service()
    if not svc.is_ready():
        ok = svc.initialize()
        if not ok:
            raise HTTPException(
                status_code=503,
                detail=svc.last_error() or "Face engine initialization failed",
            )

    image_bytes = _decode_b64(req.image_base64)
    faces = svc.analyze(
        image_bytes,
        with_embedding=req.with_embedding,
        min_face_score=req.min_face_score,
        max_faces=req.max_faces,
    )
    service_timings = svc.get_last_timings_ms() or {}
    provider = os.getenv("FACE_INFERENCE_PROVIDER", "cpu")
    return FaceAnalyzeResponse(
        faces=[FaceItem(**f) for f in faces],
        provider=provider,
        timings_ms=service_timings,
    )
