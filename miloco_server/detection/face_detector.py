# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
"""
CPU-friendly face detector.

This module integrates InsightFace (CPU) to detect faces and output bounding boxes
as DetectionResult with class_name="face".
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple, Union

import numpy as np

from miloco_server.detection.detector import DetectionResult

logger = logging.getLogger(__name__)


@dataclass
class FaceDetectionConfig:
    # InsightFace model pack (smaller = lighter on CPU).
    # According to InsightFace model zoo:
    # buffalo_l has stronger detection/recognition robustness than lightweight packs.
    model_pack: str = "buffalo_l"
    det_size: Tuple[int, int] = (640, 640)
    ctx_id: int = -1  # -1 = CPU in insightface
    min_face_score: float = 0.1
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

    When FACE_USE_REMOTE is auto/1 and AI Engine exposes /face/health, inference runs
    in miloco_ai_engine (CPU or OpenVINO iGPU). Otherwise uses local InsightFace.
    """

    def __init__(self, config: Optional[FaceDetectionConfig] = None):
        self.config = config or FaceDetectionConfig()
        self._app = None
        self._initialized = False
        self._remote = False
        self._remote_base: Optional[str] = None

    def _face_engine_base_url(self) -> str:
        explicit = os.getenv("FACE_ENGINE_URL")
        if explicit:
            return explicit.rstrip("/")
        from miloco_server.config import LOCAL_MODEL_CONFIG  # pylint: disable=import-outside-toplevel

        host = str(LOCAL_MODEL_CONFIG["host"])
        if host in ("0.0.0.0", "::", "[::]"):
            host = "127.0.0.1"
        port = LOCAL_MODEL_CONFIG["port"]
        return f"http://{host}:{port}/face"

    async def _probe_face_engine(self, base: str) -> bool:
        import httpx  # pylint: disable=import-outside-toplevel

        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{base}/health")
                return resp.status_code == 200
        except Exception:  # pylint: disable=broad-exception-caught
            return False

    def _image_to_jpeg_bytes(self, image: Union[np.ndarray, bytes]) -> bytes:
        if isinstance(image, bytes):
            return image
        import cv2  # pylint: disable=import-outside-toplevel

        ok, buf = cv2.imencode(".jpg", image)
        if not ok:
            return b""
        return buf.tobytes()

    def _analyze_remote(
        self,
        image: Union[np.ndarray, bytes],
        with_embedding: bool,
    ) -> List[FaceInfo]:
        import base64
        import httpx  # pylint: disable=import-outside-toplevel

        raw = self._image_to_jpeg_bytes(image)
        if not raw:
            logger.warning("[FaceDetector] remote: empty image bytes")
            return []
        b64 = base64.b64encode(raw).decode("ascii")
        payload = {
            "image_base64": b64,
            "with_embedding": with_embedding,
            "min_face_score": self.config.min_face_score,
            "max_faces": self.config.max_faces,
        }
        url = f"{self._remote_base}/analyze"
        try:
            with httpx.Client(timeout=120.0) as client:
                resp = client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("[FaceDetector] remote analyze failed: %s", e)
            return []

        faces = data.get("faces") or []
        infos: List[FaceInfo] = []
        for f in faces:
            bn = f.get("bbox_norm") or []
            bp = f.get("bbox_px") or []
            if len(bn) != 4 or len(bp) != 4:
                continue
            emb = None
            if with_embedding and f.get("embedding") is not None:
                emb = np.asarray(f["embedding"], dtype=np.float32)
                norm = float(np.linalg.norm(emb)) if emb.size else 0.0
                if norm > 0:
                    emb = emb / norm
            infos.append(
                FaceInfo(
                    bbox_norm=(float(bn[0]), float(bn[1]), float(bn[2]), float(bn[3])),
                    bbox_px=(int(bp[0]), int(bp[1]), int(bp[2]), int(bp[3])),
                    det_score=float(f.get("det_score", 0.0)),
                    embedding=emb,
                )
            )
        logger.info("[FaceDetector] remote analyze faces=%d", len(infos))
        return infos

    def _build_root_candidates(self) -> List[Optional[str]]:
        """
        Build candidate roots for insightface models, local-first.

        InsightFace usually looks for:
          <root>/models/<model_pack>/
        """
        candidates: List[Optional[str]] = []
        env_root = os.getenv("INSIGHTFACE_MODEL_ROOT")
        if env_root:
            candidates.append(env_root)

        # docker-compose mounts ./models to /models
        candidates.extend([
            "/models/insightface",  # recommended dedicated directory
            "/models",              # fallback if user puts models directly under /models
        ])

        # Deduplicate while preserving order
        uniq: List[Optional[str]] = []
        seen = set()
        for c in candidates:
            if c in seen:
                continue
            seen.add(c)
            uniq.append(c)

        # Last fallback: insightface default root (~/.insightface)
        uniq.append(None)
        return uniq

    def _root_has_model_pack(self, root: str) -> bool:
        """
        Check whether a root appears to contain current model pack.
        """
        base = Path(root)
        model_pack = self.config.model_pack
        # Most common layout
        p1 = base / "models" / model_pack
        # Alternate user-provided layout
        p2 = base / model_pack
        return p1.exists() or p2.exists()

    async def initialize(self) -> bool:
        """Initialize InsightFace face analysis pipeline."""
        logger.info(
            "[FaceDetector] initialize start: model=%s det_size=%s ctx_id=%s min_face_score=%.3f",
            self.config.model_pack,
            self.config.det_size,
            self.config.ctx_id,
            self.config.min_face_score,
        )

        use = os.getenv("FACE_USE_REMOTE", "auto").strip().lower()
        base = self._face_engine_base_url()
        if use == "0":
            self._remote = False
        elif use == "1":
            if not await self._probe_face_engine(base):
                logger.error(
                    "[FaceDetector] FACE_USE_REMOTE=1 but AI Engine face API unreachable: %s",
                    base,
                )
                self._initialized = False
                return False
            self._remote = True
            self._remote_base = base
            self._initialized = True
            self._app = None
            logger.info("[FaceDetector] using remote face engine: %s", base)
            return True
        else:
            if await self._probe_face_engine(base):
                self._remote = True
                self._remote_base = base
                self._initialized = True
                self._app = None
                logger.info("[FaceDetector] using remote face engine (auto): %s", base)
                return True
            self._remote = False

        try:
            from insightface.app import FaceAnalysis  # pylint: disable=import-error
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning(
                "InsightFace not available, face detection disabled: %s", e
            )
            self._initialized = False
            return False

        try:
            # Local-first initialization strategy:
            # 1) try explicit local roots (env + /models paths)
            # 2) fallback to insightface default root (may download)
            roots = self._build_root_candidates()
            last_error = None
            for root in roots:
                try:
                    if root is None:
                        logger.info(
                            "[FaceDetector] trying default insightface root for model=%s",
                            self.config.model_pack,
                        )
                        app = FaceAnalysis(name=self.config.model_pack)
                    else:
                        exists = self._root_has_model_pack(root)
                        logger.info(
                            "[FaceDetector] trying local root=%s model=%s exists=%s",
                            root,
                            self.config.model_pack,
                            exists,
                        )
                        app = FaceAnalysis(name=self.config.model_pack, root=root)

                    # prepare() runs model load (and may download if root has no model files)
                    app.prepare(ctx_id=self.config.ctx_id, det_size=self.config.det_size)
                    self._app = app
                    self._initialized = True
                    logger.info(
                        "FaceDetector initialized (model=%s, det_size=%s, ctx_id=%s, root=%s)",
                        self.config.model_pack,
                        self.config.det_size,
                        self.config.ctx_id,
                        root if root is not None else "default",
                    )
                    return True
                except Exception as e:  # pylint: disable=broad-exception-caught
                    last_error = e
                    logger.warning(
                        "[FaceDetector] init failed on root=%s: %s",
                        root if root is not None else "default",
                        e,
                    )

            logger.error(
                "[FaceDetector] all roots failed for model=%s, last_error=%s",
                self.config.model_pack,
                last_error,
            )
            self._app = None
            self._initialized = False
            return False
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("[FaceDetector] Failed to initialize FaceDetector: %s", e)
            self._app = None
            self._initialized = False
            return False

    def is_initialized(self) -> bool:
        if self._remote:
            return bool(self._initialized)
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
            logger.warning("[FaceDetector] analyze called before initialization")
            return []

        if image is None:
            logger.warning("[FaceDetector] analyze got empty image input")
            return []

        if self._remote:
            return self._analyze_remote(image, with_embedding)

        try:
            if isinstance(image, bytes):
                logger.info("[FaceDetector] analyze bytes input: size=%d with_embedding=%s", len(image), with_embedding)
            else:
                logger.info("[FaceDetector] analyze ndarray input: shape=%s with_embedding=%s", getattr(image, "shape", None), with_embedding)
            img = self._decode_image(image)

            if img is None:
                logger.warning("[FaceDetector] image decode failed: got None")
                return []

            h, w = img.shape[:2]
            logger.info("[FaceDetector] decoded image shape: h=%d w=%d", h, w)
            faces = self._detect_with_fallback_scales(img)
            if not faces:
                logger.warning("[FaceDetector] no faces from detector across fallback scales")
                return []

            logger.info("[FaceDetector] raw detected faces=%d", len(faces))

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
                    emb_candidate = getattr(face, "normed_embedding", None)
                    if emb_candidate is None:
                        emb_candidate = getattr(face, "embedding_normed", None)
                    if emb_candidate is None:
                        emb_candidate = getattr(face, "embedding", None)
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

            logger.info(
                "[FaceDetector] final accepted faces=%d (threshold=%.3f)",
                len(infos),
                self.config.min_face_score,
            )
            return infos
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.exception("[FaceDetector] Face analyze failed: %s", e)
            return []

    def _decode_image(self, image: Union[np.ndarray, bytes]):
        """Decode bytes to OpenCV BGR image, with PIL fallback."""
        if not isinstance(image, bytes):
            return image

        import cv2  # pylint: disable=import-error

        img = cv2.imdecode(np.frombuffer(image, np.uint8), cv2.IMREAD_COLOR)
        if img is not None:
            logger.info("[FaceDetector] image decoded by cv2")
            return img

        # Some formats/headers fail in cv2 on specific builds; use PIL as fallback.
        try:
            from io import BytesIO
            from PIL import Image

            pil = Image.open(BytesIO(image)).convert("RGB")
            rgb = np.asarray(pil, dtype=np.uint8)
            logger.info("[FaceDetector] image decoded by PIL fallback")
            return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception("[FaceDetector] image decode failed in cv2 and PIL fallback")
            return None

    def _detect_with_fallback_scales(self, img: np.ndarray):
        """
        Try face detection on original + resized variants.

        This improves robustness for very large/small inputs.
        """
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
            logger.info(
                "[FaceDetector] detect attempt scale=%.2f probe_shape=%s faces=%d",
                scale,
                getattr(probe, "shape", None),
                len(faces) if faces else 0,
            )
            if faces and len(faces) > len(best_faces):
                best_faces = faces
                if len(best_faces) >= self.config.max_faces:
                    break

        return best_faces

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
        self._remote = False
        self._remote_base = None
        self._initialized = False
        logger.info("FaceDetector destroyed")

