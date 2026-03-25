# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
ONNX Runtime provider selection for InsightFace.

Must run before InsightFace creates any InferenceSession.

Environment:
  FACE_INFERENCE_PROVIDER:
    - cpu: default (InsightFace uses CPUExecutionProvider via ctx_id=-1)
    - openvino: prefer OpenVINOExecutionProvider (Intel CPU/iGPU/NPU), needs onnxruntime-openvino
    - openvino_gpu: same as openvino with GPU_FP16 hint for iGPU

Requires: pip install onnxruntime-openvino (replaces onnxruntime on Intel builds)
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_PATCHED = False


def apply_face_onnx_providers() -> None:
    """Monkey-patch onnxruntime.InferenceSession for OpenVINO-backed inference."""
    global _PATCHED  # pylint: disable=global-statement
    if _PATCHED:
        return

    mode = os.getenv("FACE_INFERENCE_PROVIDER", "cpu").lower().strip()
    if mode in ("cpu", "", "default"):
        logger.info("[FaceEngine] FACE_INFERENCE_PROVIDER=%s (no ONNX patch)", mode or "cpu")
        _PATCHED = True
        return

    if mode not in ("openvino", "openvino_gpu"):
        logger.warning("[FaceEngine] Unknown FACE_INFERENCE_PROVIDER=%s, using CPU", mode)
        _PATCHED = True
        return

    try:
        import onnxruntime as ort
    except ImportError as e:
        logger.error("[FaceEngine] onnxruntime not available: %s", e)
        _PATCHED = True
        return

    _orig = ort.InferenceSession

    def _patched_inference_session(*args: Any, **kwargs: Any):
        kwargs["providers"] = ["OpenVINOExecutionProvider", "CPUExecutionProvider"]
        if mode == "openvino_gpu":
            kwargs["provider_options"] = [
                {"device_type": "GPU_FP16"},
                {},
            ]
        else:
            kwargs["provider_options"] = [{}, {}]
        return _orig(*args, **kwargs)

    ort.InferenceSession = _patched_inference_session  # type: ignore[assignment]
    logger.info("[FaceEngine] ONNX InferenceSession patched for FACE_INFERENCE_PROVIDER=%s", mode)
    _PATCHED = True
