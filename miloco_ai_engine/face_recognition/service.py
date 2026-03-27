# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""InsightFace face analysis singleton for AI Engine."""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import numpy as np
import inspect

from miloco_ai_engine.face_recognition.runtime import apply_face_onnx_providers

logger = logging.getLogger(__name__)


def _build_root_candidates() -> List[Optional[str]]:
    candidates: List[Optional[str]] = []
    env_root = os.getenv("INSIGHTFACE_MODEL_ROOT")
    if env_root:
        candidates.append(env_root)
    candidates.extend(["/models/insightface", "/models"])
    uniq: List[Optional[str]] = []
    seen = set()
    for c in candidates:
        if c in seen:
            continue
        seen.add(c)
        uniq.append(c)
    uniq.append(None)
    return uniq


def _root_has_model_pack(root: str, model_pack: str) -> bool:
    base = Path(root)
    p1 = base / "models" / model_pack
    p2 = base / model_pack
    return p1.exists() or p2.exists()


class FaceRecognitionService:
    """Thread-safe lazy FaceAnalysis wrapper."""

    def __init__(self):
        self._lock = threading.Lock()
        self._app = None
        self._initialized = False
        self._init_error: Optional[str] = None
        self._last_timings_ms: Optional[Dict[str, float]] = None
        self._model_pack = os.getenv("FACE_MODEL_PACK", "buffalo_l")
        _ds = int(os.getenv("FACE_DET_SIZE", "640"))
        self._det_size = (_ds, _ds)
        self._ctx_id = int(os.getenv("FACE_CTX_ID", "-1"))
        self._face_provider_mode = os.getenv("FACE_INFERENCE_PROVIDER", "cpu").lower().strip()
        # Cache whether insightface.app.FaceAnalysis.get supports filtering params.
        self._get_supports_det_thresh: bool = False
        self._get_supports_max_num: bool = False
        self._get_supports_max_faces: bool = False
        self._get_param_names: List[str] = []

    def is_ready(self) -> bool:
        cur_mode = os.getenv("FACE_INFERENCE_PROVIDER", "cpu").lower().strip()
        return bool(
            self._initialized
            and self._app is not None
            and self._face_provider_mode == cur_mode,
        )

    def last_error(self) -> Optional[str]:
        return self._init_error

    def get_last_timings_ms(self) -> Optional[Dict[str, float]]:
        """Return timings collected from the last /face/analyze call."""
        return self._last_timings_ms

    def get_last_get_param_names(self) -> List[str]:
        """Return FaceAnalysis.get() parameter names (best-effort)."""
        return list(self._get_param_names)

    def initialize(self) -> bool:
        with self._lock:
            cur_mode = os.getenv("FACE_INFERENCE_PROVIDER", "cpu").lower().strip()
            # If provider mode changed at runtime, force re-create FaceAnalysis so that
            # ORT sessions use the correct EP configuration.
            if self._initialized and self._app is not None and self._face_provider_mode == cur_mode:
                return True
            if self._initialized:
                self._app = None
                self._initialized = False
                self._init_error = None
            self._face_provider_mode = cur_mode

            apply_face_onnx_providers()
            try:
                from insightface.app import FaceAnalysis  # pylint: disable=import-error
            except Exception as e:  # pylint: disable=broad-exception-caught
                self._init_error = f"insightface import failed: {e}"
                logger.error("[FaceEngine] %s", self._init_error)
                return False

            # Debug: log what ORT providers we can actually use.
            try:
                import onnxruntime as ort  # pylint: disable=import-error

                logger.info(
                    "[FaceEngine][debug] requested FACE_INFERENCE_PROVIDER=%s FACE_CTX_ID=%s; onnxruntime available providers=%s",
                    os.getenv("FACE_INFERENCE_PROVIDER", "cpu"),
                    self._ctx_id,
                    ort.get_available_providers(),
                )
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.warning("[FaceEngine][debug] cannot get onnxruntime providers: %s", e)

            roots = _build_root_candidates()
            last_err = None
            for root in roots:
                try:
                    if root is None:
                        app = FaceAnalysis(name=self._model_pack)
                    else:
                        exists = _root_has_model_pack(root, self._model_pack)
                        logger.info(
                            "[FaceEngine] try root=%s model=%s exists=%s",
                            root,
                            self._model_pack,
                            exists,
                        )
                        app = FaceAnalysis(name=self._model_pack, root=root)
                    # Optionally configure ONNX Runtime execution providers.
                    # InsightFace's prepare() signature may differ across versions,
                    # so we only pass arguments it supports.
                    providers = None
                    provider_options = None
                    mode = os.getenv("FACE_INFERENCE_PROVIDER", "cpu").lower().strip()
                    if mode in ("openvino", "openvino_gpu"):
                        providers = ["OpenVINOExecutionProvider", "CPUExecutionProvider"]
                        if mode == "openvino_gpu":
                            provider_options = [{"device_type": "GPU", "precision": "FP32"}, {}]
                        else:
                            provider_options = [{}, {}]

                    prep_sig = inspect.signature(app.prepare)
                    prep_kwargs: Dict[str, Any] = {
                        "ctx_id": self._ctx_id,
                        "det_size": self._det_size,
                    }
                    if providers is not None and "providers" in prep_sig.parameters:
                        prep_kwargs["providers"] = providers
                    if provider_options is not None and "provider_options" in prep_sig.parameters:
                        prep_kwargs["provider_options"] = provider_options

                    logger.info(
                        "[FaceEngine][debug] prepare supports=%s; will_pass=%s",
                        list(prep_sig.parameters.keys()),
                        {
                            "providers": prep_kwargs.get("providers"),
                            "provider_options": prep_kwargs.get("provider_options"),
                            "ctx_id": prep_kwargs.get("ctx_id"),
                            "det_size": prep_kwargs.get("det_size"),
                        },
                    )

                    app.prepare(**prep_kwargs)
                    # Determine which optional args FaceAnalysis.get supports so we can
                    # reduce unnecessary work (e.g. limit candidates early).
                    try:
                        get_sig = inspect.signature(app.get)
                        self._get_supports_det_thresh = "det_thresh" in get_sig.parameters
                        self._get_supports_max_num = "max_num" in get_sig.parameters
                        self._get_supports_max_faces = "max_faces" in get_sig.parameters
                        self._get_param_names = list(get_sig.parameters.keys())
                    except Exception:  # pylint: disable=broad-exception-caught
                        self._get_supports_det_thresh = False
                        self._get_supports_max_num = False
                        self._get_supports_max_faces = False
                        self._get_param_names = []

                    self._app = app
                    self._initialized = True
                    self._init_error = None
                    logger.info(
                        "[FaceEngine] FaceAnalysis ready model=%s ctx_id=%s root=%s",
                        self._model_pack,
                        self._ctx_id,
                        root if root is not None else "default",
                    )
                    return True
                except Exception as e:  # pylint: disable=broad-exception-caught
                    last_err = e
                    logger.warning("[FaceEngine] init failed on root=%s: %s", root, e)

            self._init_error = str(last_err) if last_err else "unknown"
            logger.error("[FaceEngine] all init roots failed: %s", self._init_error)
            return False

    def analyze(
        self,
        image: Union[np.ndarray, bytes],
        *,
        with_embedding: bool = False,
        min_face_score: float = 0.1,
        max_faces: int = 10,
    ) -> List[Dict[str, Any]]:
        if not self.is_ready():
            return []
        if image is None:
            return []
        try:
            t_total0 = time.perf_counter()
            img = self._decode_image(image)
            t_decode_ms = (time.perf_counter() - t_total0) * 1000.0
            if img is None:
                self._last_timings_ms = {
                    "decode_ms": t_decode_ms,
                    "detect_ms": 0.0,
                    "embedding_ms": 0.0,
                    "postprocess_ms": 0.0,
                    "total_ms": (time.perf_counter() - t_total0) * 1000.0,
                }
                return []
            h, w = img.shape[:2]
            t_detect0 = time.perf_counter()
            faces = self._detect_with_fallback_scales(
                img, max_faces, min_face_score, with_embedding=with_embedding
            )
            t_detect_ms = (time.perf_counter() - t_detect0) * 1000.0
            if not faces:
                self._last_timings_ms = {
                    "decode_ms": t_decode_ms,
                    "detect_ms": t_detect_ms,
                    "embedding_ms": 0.0,
                    "postprocess_ms": 0.0,
                    "total_ms": (time.perf_counter() - t_total0) * 1000.0,
                }
                return []

            out: List[Dict[str, Any]] = []
            t_post0 = time.perf_counter()
            t_emb0 = 0.0
            embedding_ms = 0.0
            for face in faces[:max_faces]:
                det_score = float(getattr(face, "det_score", 0.0) or 0.0)
                if det_score < min_face_score:
                    continue
                bbox_px = getattr(face, "bbox", None)
                if bbox_px is None:
                    continue
                x1, y1, x2, y2 = [float(v) for v in bbox_px]
                x1 = max(0.0, min(float(w), x1))
                x2 = max(0.0, min(float(w), x2))
                y1 = max(0.0, min(float(h), y1))
                y2 = max(0.0, min(float(h), y2))
                if x2 <= x1 or y2 <= y1:
                    continue
                bbox_norm = (x1 / w, y1 / h, x2 / w, y2 / h)
                bbox_px_int = (int(x1), int(y1), int(x2), int(y2))

                emb_list = None
                if with_embedding:
                    t_emb0 = time.perf_counter()
                    emb_candidate = getattr(face, "normed_embedding", None)
                    if emb_candidate is None:
                        emb_candidate = getattr(face, "embedding_normed", None)
                    if emb_candidate is None:
                        emb_candidate = getattr(face, "embedding", None)
                    if emb_candidate is not None:
                        emb = np.asarray(emb_candidate, dtype=np.float32)
                        norm = float(np.linalg.norm(emb)) if emb.size else 0.0
                        if norm > 0:
                            emb = emb / norm
                        emb_list = emb.tolist()
                    embedding_ms += (time.perf_counter() - t_emb0) * 1000.0

                out.append(
                    {
                        "bbox_px": list(bbox_px_int),
                        "bbox_norm": list(bbox_norm),
                        "det_score": det_score,
                        "embedding": emb_list,
                    }
                )
            t_post_ms = (time.perf_counter() - t_post0) * 1000.0
            t_total_ms = (time.perf_counter() - t_total0) * 1000.0
            self._last_timings_ms = {
                "decode_ms": float(t_decode_ms),
                "detect_ms": float(t_detect_ms),
                "embedding_ms": float(embedding_ms),
                "postprocess_ms": float(t_post_ms),
                "total_ms": float(t_total_ms),
            }
            return out
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("[FaceEngine] analyze failed: %s", e)
            return []

    def _decode_image(self, image: Union[np.ndarray, bytes]):
        if not isinstance(image, bytes):
            return image
        import cv2  # pylint: disable=import-error

        img = cv2.imdecode(np.frombuffer(image, np.uint8), cv2.IMREAD_COLOR)
        if img is not None:
            return img
        try:
            from io import BytesIO
            from PIL import Image

            pil = Image.open(BytesIO(image)).convert("RGB")
            rgb = np.asarray(pil, dtype=np.uint8)
            return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception("[FaceEngine] decode failed")
            return None

    def _detect_with_fallback_scales(
        self,
        img: np.ndarray,
        max_faces: int,
        min_face_score: float,
        *,
        with_embedding: bool,
    ):
        import cv2  # pylint: disable=import-error

        h, w = img.shape[:2]
        attempts = [1.0, 0.75, 1.25]
        best_faces = []

        def _has_usable_face(faces: Any) -> bool:
            # InsightFace returns Face objects; we only use lightweight checks here
            # and leave bbox coordinate validity to later post-processing.
            for f in faces or []:
                det_score = float(getattr(f, "det_score", 0.0) or 0.0)
                bbox_px = getattr(f, "bbox", None)
                if det_score < min_face_score or bbox_px is None:
                    continue
                try:
                    x1, y1, x2, y2 = [float(v) for v in bbox_px]
                    if x2 > x1 and y2 > y1:
                        return True
                except Exception:  # pylint: disable=broad-exception-caught
                    continue
            return False

        for scale in attempts:
            if scale == 1.0:
                probe = img
            else:
                nh = max(64, int(h * scale))
                nw = max(64, int(w * scale))
                probe = cv2.resize(img, (nw, nh))

            get_kwargs: Dict[str, Any] = {}
            if self._get_supports_det_thresh:
                get_kwargs["det_thresh"] = float(min_face_score)
            if self._get_supports_max_num:
                get_kwargs["max_num"] = int(max_faces)
            elif self._get_supports_max_faces:
                get_kwargs["max_faces"] = int(max_faces)

            # Best-effort: if insightface.app.FaceAnalysis.get() exposes a switch to
            # avoid embedding computation, we pass it when supported.
            # (In many versions, embeddings are computed regardless of what we read later.)
            if not with_embedding:
                for candidate_key in (
                    "return_embedding",
                    "return_embeddings",
                    "with_embedding",
                    "return_emb",
                    "output_embedding",
                    "output_embeddings",
                ):
                    if candidate_key in self._get_param_names:
                        get_kwargs[candidate_key] = False
                        break

            if get_kwargs:
                faces = self._app.get(probe, **get_kwargs)
            else:
                faces = self._app.get(probe)
            if faces and scale == 1.0 and _has_usable_face(faces):
                # Most frames will be detected at scale=1.0; avoid 3x inference cost.
                return faces
            if faces and len(faces) > len(best_faces):
                best_faces = faces
                if len(best_faces) >= max_faces:
                    break
        return best_faces


_service: Optional[FaceRecognitionService] = None
_service_lock = threading.Lock()


def get_face_service() -> FaceRecognitionService:
    global _service  # pylint: disable=global-statement
    with _service_lock:
        if _service is None:
            _service = FaceRecognitionService()
        return _service
