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

    # InsightFace's FaceAnalysis.prepare() in our environment does NOT accept
    # `providers`/`provider_options` (see debug logs: prepare supports ctx_id/det_size/det_thresh only).
    # To force OpenVINO/CPU providers, we patch ONNX Runtime's InferenceSession.__init__
    # (keep class identity; avoid replacing ort.InferenceSession itself).
    try:
        import onnxruntime as ort  # pylint: disable=import-error
    except ImportError as e:
        logger.error("[FaceEngine] onnxruntime not available: %s", e)
        _PATCHED = True
        return

    available = []
    try:
        available = ort.get_available_providers()
    except Exception:  # pylint: disable=broad-exception-caught
        available = []

    # Only apply if OpenVINO EP exists; otherwise keep CPU behavior.
    if "OpenVINOExecutionProvider" not in available:
        logger.warning(
            "[FaceEngine] OpenVINOExecutionProvider not available (available=%s), keep default providers.",
            available,
        )
        _PATCHED = True
        return

    orig_init = ort.InferenceSession.__init__

    def _patched_init(self: Any, *args: Any, **kwargs: Any):
        providers = kwargs.get("providers")
        provider_options = kwargs.get("provider_options")

        # If InsightFace explicitly requests CUDA, filter it out.
        if providers is not None:
            providers = [p for p in providers if p != "CUDAExecutionProvider"]
            if not providers:
                providers = ["OpenVINOExecutionProvider", "CPUExecutionProvider"]
            kwargs["providers"] = providers

        # If not specified, set providers to OpenVINO then CPU fallback.
        if providers is None:
            kwargs["providers"] = ["OpenVINOExecutionProvider", "CPUExecutionProvider"]

        # Provider options only for OpenVINO GPU path.
        if mode == "openvino_gpu":
            if provider_options is None:
                kwargs["provider_options"] = [{"device_type": "GPU_FP16"}, {}]
        else:
            if provider_options is None and "provider_options" in kwargs:
                # keep whatever caller set
                pass
            if provider_options is None:
                kwargs["provider_options"] = [{}, {}]

        return orig_init(self, *args, **kwargs)

    ort.InferenceSession.__init__ = _patched_init  # type: ignore[assignment]
    logger.info(
        "[FaceEngine] Patched InferenceSession.__init__ for mode=%s (available=%s)",
        mode,
        available,
    )
    _PATCHED = True
