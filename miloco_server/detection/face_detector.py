# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
"""
CPU-friendly face detector.

This module integrates InsightFace (CPU) to detect faces and output bounding boxes
as DetectionResult with class_name="face".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple, Union

import numpy as np

from miloco_server.detection.detector import DetectionResult

logger = logging.getLogger(__name__)


@dataclass
class FaceDetectionConfig:
    # InsightFace model pack (smaller = lighter on CPU).
    # According to InsightFace model zoo:
    # - buffalo_sc is the smallest python-package model pack (~16MB).
    model_pack: str = "buffalo_sc"
    det_size: Tuple[int, int] = (640, 640)
    ctx_id: int = -1  # -1 = CPU in insightface
    min_face_score: float = 0.3
    max_faces: int = 10


@dataclass
class FaceInfo:
    bbox_norm: Tuple[float, float, float, float]
    bbox_px: Tuple[int, int, int, int]
    det_score: float
    embedding: Optional[np.ndarray] = None


class FaceDetector:
    """
    Face detector that outputs DetectionResult list for class_name="face".
    """

    def __init__(self, config: Optional[FaceDetectionConfig] = None):
        self.config = config or FaceDetectionConfig()
        self._app = None
        self._initialized = False

    async def initialize(self) -> bool:
        """Initialize InsightFace face analysis pipeline."""
        try:
            from insightface.app import FaceAnalysis  # pylint: disable=import-error
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning(
                "InsightFace not available, face detection disabled: %s", e
            )
            self._initialized = False
            return False

        try:
            self._app = FaceAnalysis(name=self.config.model_pack)
            # prepare() runs model download/initialization if needed
            self._app.prepare(ctx_id=self.config.ctx_id, det_size=self.config.det_size)
            self._initialized = True
            logger.info(
                "FaceDetector initialized (model=%s, det_size=%s, ctx_id=%s)",
                self.config.model_pack,
                self.config.det_size,
                self.config.ctx_id,
            )
            return True
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Failed to initialize FaceDetector: %s", e)
            self._app = None
            self._initialized = False
            return False

    def is_initialized(self) -> bool:
        return bool(self._initialized and self._app is not None)

    def analyze(
        self,
        image: Union[np.ndarray, bytes],
        with_embedding: bool = False,
    ) -> List[FaceInfo]:
        """
        Analyze faces in an image.

        Args:
            with_embedding: whether to compute/return embedding vectors.
        """
        if not self.is_initialized():
            return []

        if image is None:
            return []

        try:
            if isinstance(image, bytes):
                import cv2  # pylint: disable=import-error

                img = cv2.imdecode(
                    np.frombuffer(image, np.uint8), cv2.IMREAD_COLOR
                )
            else:
                img = image

            if img is None:
                return []

            h, w = img.shape[:2]
            faces = self._app.get(img)
            if not faces:
                return []

            infos: List[FaceInfo] = []
            for face in faces[: self.config.max_faces]:
                det_score = float(getattr(face, "det_score", 0.0) or 0.0)
                if det_score < self.config.min_face_score:
                    continue

                bbox_px = getattr(face, "bbox", None)
                if bbox_px is None:
                    continue

                x1, y1, x2, y2 = [float(v) for v in bbox_px]
                # clip
                x1 = max(0.0, min(float(w), x1))
                x2 = max(0.0, min(float(w), x2))
                y1 = max(0.0, min(float(h), y1))
                y2 = max(0.0, min(float(h), y2))

                if x2 <= x1 or y2 <= y1:
                    continue

                bbox_norm = (x1 / w, y1 / h, x2 / w, y2 / h)
                bbox_px_int = (int(x1), int(y1), int(x2), int(y2))

                emb = None
                if with_embedding:
                    emb_candidate = (
                        getattr(face, "normed_embedding", None)
                        or getattr(face, "embedding_normed", None)
                        or getattr(face, "embedding", None)
                    )
                    if emb_candidate is not None:
                        emb = np.asarray(emb_candidate, dtype=np.float32)
                        # Normalize for cosine similarity.
                        norm = float(np.linalg.norm(emb)) if emb.size else 0.0
                        if norm > 0:
                            emb = emb / norm

                infos.append(
                    FaceInfo(
                        bbox_norm=bbox_norm,
                        bbox_px=bbox_px_int,
                        det_score=det_score,
                        embedding=emb,
                    )
                )

            return infos
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning("Face analyze failed: %s", e)
            return []

    def detect(self, image: Union[np.ndarray, bytes]) -> List[DetectionResult]:
        """
        Detect faces and return DetectionResult list.

        Note: StreamProcessor passes JPEG bytes; we decode once per call here.
        """
        infos = self.analyze(image, with_embedding=False)
        detections: List[DetectionResult] = []
        for info in infos:
            detections.append(
                DetectionResult(
                    class_id=0,
                    class_name="face",
                    confidence=info.det_score,
                    bbox=info.bbox_norm,
                    bbox_px=info.bbox_px,
                )
            )
        return detections

    async def destroy(self):
        """Release resources."""
        self._app = None
        self._initialized = False
        logger.info("FaceDetector destroyed")

