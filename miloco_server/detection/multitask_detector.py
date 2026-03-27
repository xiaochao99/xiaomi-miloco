# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
"""
Multi-task detector: object detection + optional face detection.

Used by StreamProcessor to output unified DetectionResult list.
"""

from __future__ import annotations

import time
from typing import List, Optional, Union

import numpy as np

from miloco_server.detection.detector import (
    DetectionResult,
    FrameDetectionResult,
    ObjectDetector,
)
from miloco_server.detection.face_detector import FaceDetector
from miloco_server.face_recognition.face_library_service import FaceLibraryService


class MultiTaskDetector:
    def __init__(
        self,
        object_detector: ObjectDetector,
        face_detector: Optional[FaceDetector] = None,
        enable_face_recognition: bool = False,
        face_accept_threshold: float = 0.35,
    ):
        self._object_detector = object_detector
        self._face_detector = face_detector
        self._enable_face_recognition = enable_face_recognition
        self._face_accept_threshold = float(face_accept_threshold)
        self._face_library = FaceLibraryService()

    @property
    def config(self):
        return self._object_detector.config

    def is_initialized(self) -> bool:
        return self._object_detector.is_initialized()

    async def destroy(self):
        # underlying detectors managed by DetectionService
        return

    def detect(self, image: Union[np.ndarray, bytes]) -> FrameDetectionResult:
        if isinstance(image, bytes):
            import cv2  # pylint: disable=import-error

            img = cv2.imdecode(np.frombuffer(image, np.uint8), cv2.IMREAD_COLOR)
        else:
            img = image

        if img is None:
            return FrameDetectionResult(
                timestamp=time.time(),
                frame_id=0,
                detections=[],
                inference_time_ms=0.0,
                original_shape=(0, 0),
            )

        start = time.time()

        # Object detection (person/cat/dog)
        obj_result = self._object_detector.detect(img)
        detections: List[DetectionResult] = list(obj_result.detections)

        # Face detection + identification (class_name="face")
        # Optimization: only run face analysis when a person is detected first.
        has_person = any(det.class_name == "person" for det in detections)
        if self._enable_face_recognition and self._face_detector and has_person:
            face_start = time.time()
            face_infos = self._face_detector.analyze(img, with_embedding=True)
            for info in face_infos:
                identity = None
                if info.embedding is not None and info.embedding.size:
                    matches = self._face_library.search(
                        query_embedding=info.embedding,
                        top_k=1,
                        accept_threshold=self._face_accept_threshold,
                    )
                    if matches:
                        m = matches[0]
                        identity = {"id": m.id, "name": m.name, "score": round(m.score, 4)}

                detections.append(
                    DetectionResult(
                        class_id=0,
                        class_name="face",
                        confidence=float(info.det_score),
                        bbox=info.bbox_norm,
                        bbox_px=info.bbox_px,
                        extra={"identity": identity} if identity else {"identity": None},
                    )
                )
            face_time_ms = (time.time() - face_start) * 1000.0
        else:
            face_time_ms = 0.0

        total_time_ms = (time.time() - start) * 1000.0

        # Prefer the measured total time (includes both tasks).
        obj_result.inference_time_ms = total_time_ms
        obj_result.detections = detections
        return obj_result

