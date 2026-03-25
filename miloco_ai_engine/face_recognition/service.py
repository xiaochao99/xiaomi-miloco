# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""InsightFace face analysis singleton for AI Engine."""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import numpy as np

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
        self._model_pack = os.getenv("FACE_MODEL_PACK", "buffalo_l")
        _ds = int(os.getenv("FACE_DET_SIZE", "640"))
        self._det_size = (_ds, _ds)
        self._ctx_id = int(os.getenv("FACE_CTX_ID", "-1"))

    def is_ready(self) -> bool:
        return bool(self._initialized and self._app is not None)

    def last_error(self) -> Optional[str]:
        return self._init_error

    def initialize(self) -> bool:
        with self._lock:
            if self._initialized:
                return True
            apply_face_onnx_providers()
            try:
                from insightface.app import FaceAnalysis  # pylint: disable=import-error
            except Exception as e:  # pylint: disable=broad-exception-caught
                self._init_error = f"insightface import failed: {e}"
                logger.error("[FaceEngine] %s", self._init_error)
                return False

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
                    app.prepare(ctx_id=self._ctx_id, det_size=self._det_size)
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
            img = self._decode_image(image)
            if img is None:
                return []
            h, w = img.shape[:2]
            faces = self._detect_with_fallback_scales(img, max_faces)
            if not faces:
                return []

            out: List[Dict[str, Any]] = []
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

                out.append(
                    {
                        "bbox_px": list(bbox_px_int),
                        "bbox_norm": list(bbox_norm),
                        "det_score": det_score,
                        "embedding": emb_list,
                    }
                )
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

    def _detect_with_fallback_scales(self, img: np.ndarray, max_faces: int):
        import cv2  # pylint: disable=import-error

        h, w = img.shape[:2]
        attempts = [1.0, 0.75, 1.25]
        best_faces = []

        for scale in attempts:
            if scale == 1.0:
                probe = img
            else:
                nh = max(64, int(h * scale))
                nw = max(64, int(w * scale))
                probe = cv2.resize(img, (nw, nh))

            faces = self._app.get(probe)
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
