# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
ONNX Runtime provider selection for InsightFace.

Must run before InsightFace creates any InferenceSession.

Environment:
  FACE_INFERENCE_PROVIDER:
    - cpu: default (InsightFace uses CPUExecutionProvider via ctx_id=-1)
    - openvino: prefer OpenVINOExecutionProvider (Intel CPU/iGPU/NPU), needs onnxruntime-openvino
    - openvino_gpu: same as openvino with GPU + FP16 hint for iGPU

Requires: pip install onnxruntime-openvino (replaces onnxruntime on Intel builds)
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_PATCHED = False
_PATCHED_MODE: str = ""
_ORT_DEBUG_LOGGED = False
_ORT_SESSION_PROVIDERS_LOGGED = False
_LAST_SESSION_PROVIDERS: list[str] = []
_LAST_PROVIDER_OPTIONS: list[Any] = []
_LAST_OPENVINO_DEVICES: list[str] = []
_LAST_CHOSEN_DEVICE_TYPE: str = ""
_ORIG_INFERENCESESSION_INIT = None


def apply_face_onnx_providers() -> None:
    """Monkey-patch onnxruntime.InferenceSession for OpenVINO-backed inference."""
    mode = os.getenv("FACE_INFERENCE_PROVIDER", "cpu").lower().strip()
    global _PATCHED, _PATCHED_MODE, _ORIG_INFERENCESESSION_INIT  # pylint: disable=global-statement
    # Fixed to FP32 by code for better stability on some OpenVINO GPU setups.
    openvino_precision = "FP32"
    if mode in ("cpu", "", "default"):
        logger.info("[FaceEngine] FACE_INFERENCE_PROVIDER=%s (no ONNX patch)", mode or "cpu")
        try:
            import onnxruntime as ort  # pylint: disable=import-error
        except ImportError as e:
            logger.error("[FaceEngine] onnxruntime not available: %s", e)
            return

        # Restore original init if we previously patched.
        if _ORIG_INFERENCESESSION_INIT is not None:
            ort.InferenceSession.__init__ = _ORIG_INFERENCESESSION_INIT  # type: ignore[assignment]
        _PATCHED = False
        _PATCHED_MODE = mode or "cpu"
        return

    if mode not in ("openvino", "openvino_gpu"):
        logger.warning("[FaceEngine] Unknown FACE_INFERENCE_PROVIDER=%s, using CPU", mode)
        _PATCHED = False
        _PATCHED_MODE = "cpu"
        return

    # InsightFace's FaceAnalysis.prepare() in our environment does NOT accept
    # `providers`/`provider_options` (see debug logs: prepare supports ctx_id/det_size/det_thresh only).
    # To force OpenVINO/CPU providers, we patch ONNX Runtime's InferenceSession.__init__
    # (keep class identity; avoid replacing ort.InferenceSession itself).
    try:
        import onnxruntime as ort  # pylint: disable=import-error
    except ImportError as e:
        logger.error("[FaceEngine] onnxruntime not available: %s", e)
        _PATCHED = False
        _PATCHED_MODE = mode
        return

    # Verification switch: when enabled, force OpenVINO-only by removing CPU fallback.
    # Read again inside _patched_init so it can take effect even if the patch
    # function was created earlier.
    no_cpu_fallback_default = os.getenv(
        "FACE_OPENVINO_NO_CPU_FALLBACK", "1"
    ).strip().lower() in ("1", "true", "yes")

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
        _PATCHED = False
        _PATCHED_MODE = mode
        return
    if _PATCHED and _PATCHED_MODE == mode:
        # Already patched for the current mode.
        return

    # Detect whether OpenVINO runtime actually has GPU device enabled.
    openvino_devices: list[str] = []
    try:
        # Newer OpenVINO python API
        from openvino import Core  # type: ignore  # pylint: disable=import-error

        core = Core()
        openvino_devices = list(core.available_devices)
        logger.info(
            "[FaceEngine][debug][OV] available_devices=%s",
            openvino_devices,
        )
    except Exception as e:  # pylint: disable=broad-exception-caught
        try:
            # Older API fallback
            import openvino.runtime as ov  # type: ignore  # pylint: disable=import-error

            core = ov.Core()
            openvino_devices = list(core.available_devices)
            logger.info(
                "[FaceEngine][debug][OV] available_devices=%s",
                openvino_devices,
            )
        except Exception as e2:  # pylint: disable=broad-exception-caught
            logger.warning("[FaceEngine][debug][OV] cannot query available_devices: %s", e2)

    def _choose_device_type() -> str:
        """
        Choose OpenVINO device_type for provider_options.

        Important: many OpenVINO CPU builds only support FP32/ACCURACY and will
        reject CPU_FP16 (see logs: "CPU only supports FP32, ACCURACY").
        """
        if mode == "openvino_gpu":
            # Prefer GPU only when OpenVINO runtime reports GPU devices.
            # If we cannot query (no openvino Python package), we still attempt GPU
            # so you can validate iGPU acceleration. OpenVINO EP will fall back
            # or error out if GPU device is truly unavailable.
            if not openvino_devices:
                logger.warning(
                    "[FaceEngine][debug][OV] openvino Python module not available (or no devices query); "
                    "will still attempt device_type=GPU for validation."
                )
                return "GPU"
            if any(d == "GPU" or str(d).startswith("GPU") for d in openvino_devices):
                return "GPU"
            return "CPU"
        # openvino (non-gpu) -> safe CPU precision
        return "CPU"

    chosen_device_type = _choose_device_type()
    logger.info("[FaceEngine][debug][OV] chosen OpenVINO device_type=%s (mode=%s)", chosen_device_type, mode)
    global _LAST_OPENVINO_DEVICES, _LAST_CHOSEN_DEVICE_TYPE  # pylint: disable=global-statement
    _LAST_OPENVINO_DEVICES = list(openvino_devices)
    _LAST_CHOSEN_DEVICE_TYPE = chosen_device_type

    if _ORIG_INFERENCESESSION_INIT is None:
        _ORIG_INFERENCESESSION_INIT = ort.InferenceSession.__init__
    orig_init = _ORIG_INFERENCESESSION_INIT

    def _patched_init(self: Any, *args: Any, **kwargs: Any):
        global _ORT_DEBUG_LOGGED, _ORT_SESSION_PROVIDERS_LOGGED, _LAST_SESSION_PROVIDERS, _LAST_PROVIDER_OPTIONS  # pylint: disable=global-statement
        providers = kwargs.get("providers")

        # Normalize providers to list
        if providers is None:
            # Prefer OpenVINO -> CPU
            providers = ["OpenVINOExecutionProvider", "CPUExecutionProvider"]
        elif isinstance(providers, (str, bytes)):
            providers = [providers]
        else:
            providers = list(providers)

        # Filter CUDA requests (we only have OpenVINO/CPU in this image).
        providers = [p for p in providers if p != "CUDAExecutionProvider"]

        # Optional: force OpenVINO-only by removing CPU fallback.
        # Re-read env at call-time to avoid needing a re-patch after toggling.
        no_cpu_fallback = os.getenv(
            "FACE_OPENVINO_NO_CPU_FALLBACK",
            "1" if no_cpu_fallback_default else "0",
        ).strip().lower() in ("1", "true", "yes")
        if mode == "openvino_gpu" and no_cpu_fallback:
            providers = [p for p in providers if p != "CPUExecutionProvider"]

        # Ensure OpenVINO is present in openvino_gpu mode.
        if mode == "openvino_gpu" and "OpenVINOExecutionProvider" in available:
            if "OpenVINOExecutionProvider" not in providers:
                providers = ["OpenVINOExecutionProvider"] + providers

        # If OpenVINO isn't available, fall back to CPU only.
        if "OpenVINOExecutionProvider" not in available:
            providers = ["CPUExecutionProvider"]

        kwargs["providers"] = providers

        # Optionally disable CPU EP fallback to understand whether latency comes
        # from OpenVINO GPU execution or from CPU fallback for unsupported ops.
        if mode == "openvino_gpu" and no_cpu_fallback:
            try:
                # sess_options key exists in InferenceSession signature.
                sess_options = kwargs.get("sess_options")
                if sess_options is None:
                    sess_options = ort.SessionOptions()
                # When enabled, ORT will not fallback nodes to CPU EP.
                sess_options.add_config_entry("session.disable_cpu_ep_fallback", "1")
                kwargs["sess_options"] = sess_options
            except Exception:  # pylint: disable=broad-exception-caught
                pass

        # Force provider_options to be a list aligned with providers length.
        # This avoids ORT error: providers/provider_options length mismatch.
        if mode == "openvino_gpu":
            kwargs["provider_options"] = [
                (
                    {"device_type": "GPU", "precision": openvino_precision}
                    if p == "OpenVINOExecutionProvider" and chosen_device_type == "GPU"
                    else {"device_type": "CPU", "precision": "FP32"}
                    if p == "OpenVINOExecutionProvider"
                    else {}
                )
                for p in providers
            ]
        else:
            kwargs["provider_options"] = [
                {"device_type": "CPU", "precision": "FP32"} if p == "OpenVINOExecutionProvider" else {}
                for p in providers
            ]

        # Cache provider_options for observability.
        try:
            _LAST_PROVIDER_OPTIONS = list(kwargs.get("provider_options") or [])
        except Exception:  # pylint: disable=broad-exception-caught
            _LAST_PROVIDER_OPTIONS = []

        # One-time debug: show what ORT is actually requested to use.
        try:
            if not _ORT_DEBUG_LOGGED:
                logger.info(
                    "[FaceEngine][debug][ORT] providers=%s provider_options=%s",
                    kwargs.get("providers"),
                    kwargs.get("provider_options"),
                )
                _ORT_DEBUG_LOGGED = True
        except Exception:  # pylint: disable=broad-exception-caught
            pass

        res = orig_init(self, *args, **kwargs)
        # One-time debug: show actual providers after session creation.
        try:
            # Capture providers for observability (used by /face/analyze timings response).
            _LAST_SESSION_PROVIDERS = list(self.get_providers())
            if not _ORT_SESSION_PROVIDERS_LOGGED:
                logger.info(
                    "[FaceEngine][debug][ORT] InferenceSession actual providers=%s",
                    self.get_providers(),
                )
                _ORT_SESSION_PROVIDERS_LOGGED = True
        except Exception:  # pylint: disable=broad-exception-caught
            pass
        return res

    ort.InferenceSession.__init__ = _patched_init  # type: ignore[assignment]
    logger.info(
        "[FaceEngine] Patched InferenceSession.__init__ for mode=%s (available=%s)",
        mode,
        available,
    )
    _PATCHED = True
    _PATCHED_MODE = mode


def get_last_session_providers() -> list[str]:
    """Return providers list captured from the last created ORT session."""
    return list(_LAST_SESSION_PROVIDERS)


def get_last_provider_options() -> list[Any]:
    """Return provider_options passed to the last created ORT session."""
    return list(_LAST_PROVIDER_OPTIONS)


def get_last_openvino_devices() -> list[str]:
    """Return OpenVINO Core.available_devices from the last provider patch."""
    return list(_LAST_OPENVINO_DEVICES)


def get_last_chosen_device_type() -> str:
    """Return the chosen OpenVINO device_type (GPU/CPU) for provider_options."""
    return _LAST_CHOSEN_DEVICE_TYPE
