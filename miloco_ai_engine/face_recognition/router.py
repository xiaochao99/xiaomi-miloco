# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""FastAPI routes for face recognition."""

from __future__ import annotations

import base64
import logging
import os
import time

from fastapi import APIRouter, HTTPException

from miloco_ai_engine.face_recognition.schemas import FaceAnalyzeRequest, FaceAnalyzeResponse, FaceItem
from miloco_ai_engine.face_recognition.service import get_face_service
from miloco_ai_engine.face_recognition.runtime import (
    get_last_chosen_device_type,
    get_last_provider_options,
    get_last_openvino_devices,
    get_last_session_providers,
)

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

    t_request0 = time.perf_counter()
    t_decode_b64_0 = time.perf_counter()
    image_bytes = _decode_b64(req.image_base64)
    decode_b64_ms = (time.perf_counter() - t_decode_b64_0) * 1000.0
    faces = svc.analyze(
        image_bytes,
        with_embedding=req.with_embedding,
        min_face_score=req.min_face_score,
        max_faces=req.max_faces,
    )
    service_timings = svc.get_last_timings_ms() or {}
    provider = os.getenv("FACE_INFERENCE_PROVIDER", "cpu")
    ort_session_providers = get_last_session_providers()
    ort_provider_options = get_last_provider_options()
    openvino_devices = get_last_openvino_devices()
    chosen_device_type = get_last_chosen_device_type()
    request_ms = (time.perf_counter() - t_request0) * 1000.0

    warn_msg = None
    if provider == "openvino_gpu" and chosen_device_type != "GPU":
        warn_msg = (
            "OpenVINO GPU device is not available in this container "
            f"(available_devices={openvino_devices}); falling back to CPU."
        )
    return FaceAnalyzeResponse(
        faces=[FaceItem(**f) for f in faces],
        provider=provider,
        timings_ms={
            **service_timings,
            "decode_b64_ms": float(decode_b64_ms),
            "request_total_ms": float(request_ms),
            "ort_session_providers": ort_session_providers,
            "ort_provider_options": ort_provider_options,
            "openvino_devices": openvino_devices,
            "chosen_openvino_device_type": chosen_device_type,
        },
        message=warn_msg,
    )
