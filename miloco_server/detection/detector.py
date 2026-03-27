# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
YOLO-based object detector for real-time detection of persons, cats, and dogs.
Uses lightweight YOLOv8-nano model for efficient local inference.
"""

import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union, Any

import numpy as np

logger = logging.getLogger(__name__)

# Target classes we want to detect
TARGET_CLASSES = {
    'person': 0,
    'cat': 15,
    'dog': 16,
}

# COCO class names
COCO_NAMES = {
    0: 'person', 1: 'bicycle', 2: 'car', 3: 'motorcycle', 4: 'airplane',
    5: 'bus', 6: 'train', 7: 'truck', 8: 'boat', 9: 'traffic light',
    10: 'fire hydrant', 11: 'stop sign', 12: 'parking meter', 13: 'bench',
    14: 'bird', 15: 'cat', 16: 'dog', 17: 'horse', 18: 'sheep', 19: 'cow',
    20: 'elephant', 21: 'bear', 22: 'zebra', 23: 'giraffe',
}


@dataclass
class DetectionConfig:
    """Configuration for object detection."""
    model_path: Optional[str] = None
    confidence_threshold: float = 0.5
    iou_threshold: float = 0.45
    input_size: Tuple[int, int] = (640, 640)
    max_detections: int = 50
    # Supported values:
    # - auto: pick best available provider automatically
    # - cpu / cuda / mps(coreml) / directml(dml) / openvino
    # For Intel/Windows iGPU acceleration, prefer directml or openvino.
    device: str = 'auto'
    half_precision: bool = True  # Use FP16 for faster inference


@dataclass
class DetectionResult:
    """Single detection result."""
    class_id: int
    class_name: str
    confidence: float
    bbox: Tuple[float, float, float, float]  # x1, y1, x2, y2 (normalized 0-1)
    bbox_px: Optional[Tuple[int, int, int, int]] = None  # pixel coordinates
    extra: Optional[Dict[str, Any]] = None


@dataclass
class FrameDetectionResult:
    """Detection results for a single frame."""
    timestamp: float
    frame_id: int
    detections: List[DetectionResult] = field(default_factory=list)
    inference_time_ms: float = 0.0
    original_shape: Tuple[int, int] = (0, 0)  # height, width


class ObjectDetector:
    """
    Lightweight YOLO object detector optimized for real-time inference.
    Supports detection of persons, cats, and dogs.
    """

    # Model download URLs (YOLOv8 nano - smallest and fastest)
    MODEL_URLS = {
        'yolov8n.onnx': 'https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.onnx',
    }

    def __init__(self, config: Optional[DetectionConfig] = None):
        self.config = config or DetectionConfig()
        self._model = None
        self._session = None
        self._input_name = None
        self._output_name = None
        self._device = None
        self._initialized = False
        self._frame_count = 0

    async def initialize(self) -> bool:
        """Initialize the detector and load the model."""
        try:
            # Try to import ONNX Runtime
            try:
                import onnxruntime as ort
            except ImportError:
                logger.warning("onnxruntime not available, trying onnxruntime-gpu...")
                try:
                    import onnxruntime_gpu as ort  # type: ignore
                except ImportError:
                    logger.error("Neither onnxruntime nor onnxruntime-gpu is installed")
                    return False

            # Get or download model
            model_path = await self._ensure_model()
            if not model_path:
                return False

            # Create inference session
            providers = self._get_providers(ort)
            logger.info(f"Using detection backend: {self._device}, providers={providers}")
            sess_options = ort.SessionOptions()
            sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            sess_options.intra_op_num_threads = 4  # Limit threads for lower CPU usage

            self._session = ort.InferenceSession(
                model_path,
                sess_options=sess_options,
                providers=providers
            )

            self._input_name = self._session.get_inputs()[0].name
            self._output_name = self._session.get_outputs()[0].name

            # Get model input shape (handle dynamic dimensions)
            input_shape = self._session.get_inputs()[0].shape
            # input_shape format: [batch, channels, height, width]
            # Dynamic dimensions may be strings like 'height', 'width'
            try:
                height = int(input_shape[2]) if isinstance(input_shape[2], (int, float)) else 640
                width = int(input_shape[3]) if isinstance(input_shape[3], (int, float)) else 640
                self.config.input_size = (height, width)
            except (IndexError, ValueError, TypeError):
                # Fallback to default size if shape parsing fails
                self.config.input_size = (640, 640)
                logger.warning(f"Could not parse input shape {input_shape}, using default {self.config.input_size}")

            self._initialized = True
            logger.info(f"Object detector initialized successfully. Input size: {self.config.input_size}")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize detector: {e}")
            return False

    def _get_providers(self, ort) -> List[str]:
        """Get execution providers based on configured/available backend."""
        available_providers = ort.get_available_providers()
        logger.info(f"Available ONNX Runtime providers: {available_providers}")
        requested = (self.config.device or "auto").lower().strip()

        provider_aliases = {
            "cuda": ["CUDAExecutionProvider"],
            "mps": ["CoreMLExecutionProvider"],
            "coreml": ["CoreMLExecutionProvider"],
            "directml": ["DmlExecutionProvider"],
            "dml": ["DmlExecutionProvider"],
            "igpu": ["DmlExecutionProvider", "OpenVINOExecutionProvider"],
            "intel_gpu": ["OpenVINOExecutionProvider", "DmlExecutionProvider"],
            "openvino": ["OpenVINOExecutionProvider"],
            "cpu": ["CPUExecutionProvider"],
        }

        # Auto priority: dedicated GPU -> iGPU acceleration -> Apple -> CPU fallback
        auto_priority = [
            "CUDAExecutionProvider",
            "DmlExecutionProvider",
            "OpenVINOExecutionProvider",
            "CoreMLExecutionProvider",
            "CPUExecutionProvider",
        ]

        if requested == "auto":
            chain = [p for p in auto_priority if p in available_providers]
        else:
            preferred = provider_aliases.get(requested, [])
            chain = [p for p in preferred if p in available_providers]
            if not chain:
                logger.warning(
                    f"Requested detection backend '{requested}' is unavailable; falling back to CPU."
                )

        if "CPUExecutionProvider" in available_providers and "CPUExecutionProvider" not in chain:
            chain.append("CPUExecutionProvider")
        if not chain:
            chain = ["CPUExecutionProvider"]

        first = chain[0]
        if first == "CUDAExecutionProvider":
            self._device = "cuda"
        elif first == "CoreMLExecutionProvider":
            self._device = "mps"
        elif first == "DmlExecutionProvider":
            self._device = "directml"
        elif first == "OpenVINOExecutionProvider":
            self._device = "openvino"
        else:
            self._device = "cpu"

        return chain

    async def _ensure_model(self) -> Optional[str]:
        """Ensure model file exists, load from built-in resources."""
        # If custom model path is provided and exists, use it
        if self.config.model_path and os.path.exists(self.config.model_path):
            logger.info(f"Using custom model path: {self.config.model_path}")
            return self.config.model_path

        # Try to load built-in model
        try:
            from miloco_server.detection.model_loader import get_builtin_model_path
            
            builtin_path = get_builtin_model_path()
            if builtin_path:
                logger.info(f"Using built-in model: {builtin_path}")
                return builtin_path
            else:
                logger.error(
                    "Built-in model not found. Please set YOLO_MODEL_PATH or place an ONNX file "
                    "under /models or miloco_server/detection/models/ (e.g. yolo26n.onnx)."
                )
                
        except Exception as e:
            logger.error(f"Failed to load built-in model: {e}")
        
        # Fallback: try legacy download for backward compatibility
        logger.warning("Attempting legacy download as fallback...")
        return await self._download_model_legacy()

    async def _download_model_legacy(self) -> Optional[str]:
        """
        Legacy method to download model from internet.
        Kept for backward compatibility only.
        """
        logger.warning("Using legacy model download - consider using built-in model instead")
        
        model_dir = Path(__file__).parent / "models"
        model_dir.mkdir(exist_ok=True)
        
        model_name = "yolov8n.onnx"
        model_path = model_dir / model_name
        
        if model_path.exists():
            return str(model_path)
        
        # Download model
        logger.info(f"Downloading YOLO model to {model_path}...")
        try:
            import aiohttp
            url = self.MODEL_URLS.get(model_name)
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=300)) as response:
                    response.raise_for_status()
                    total_size = int(response.headers.get('content-length', 0))
                    
                    with open(model_path, 'wb') as f:
                        downloaded = 0
                        async for chunk in response.content.iter_chunked(8192):
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0:
                                progress = (downloaded / total_size) * 100
                                if downloaded % (1024 * 1024) < 8192:
                                    logger.info(f"Download progress: {progress:.1f}%")
            
            logger.info(f"Model downloaded successfully to {model_path}")
            return str(model_path)
            
        except Exception as e:
            logger.error(f"Failed to download model: {e}")
            return None
    
    async def _setup_opencv_fallback(self, model_dir: Path) -> Optional[str]:
        """Setup OpenCV DNN as fallback if ONNX model download fails."""
        try:
            import cv2
            logger.info("Using OpenCV DNN as fallback detector")
            self._use_opencv = True
            return None
        except ImportError:
            logger.error("OpenCV not available for fallback")
            return None

    def detect(self, image: Union[np.ndarray, bytes]) -> FrameDetectionResult:
        """
        Run detection on an image.

        Args:
            image: numpy array (BGR format) or JPEG bytes

        Returns:
            FrameDetectionResult with detected objects
        """
        start_time = time.time()
        self._frame_count += 1

        try:
            input_bytes_len = len(image) if isinstance(image, bytes) else 0

            # Convert bytes to numpy array if needed
            if isinstance(image, bytes):
                import cv2
                image = cv2.imdecode(np.frombuffer(image, np.uint8), cv2.IMREAD_COLOR)

            if image is None:
                logger.error(f"Failed to decode image (cv2.imdecode returned None), input size: {input_bytes_len} bytes")
                return FrameDetectionResult(
                    timestamp=time.time(),
                    frame_id=self._frame_count,
                    detections=[],
                    inference_time_ms=0.0,
                    original_shape=(0, 0)
                )

            original_shape = image.shape[:2]  # height, width
            logger.debug(f"Image decoded successfully: shape={original_shape}")

            # Preprocess
            input_tensor = self._preprocess(image)
            logger.debug(f"Preprocessed: input_tensor shape={input_tensor.shape}")

            # Inference
            if hasattr(self, '_use_opencv') and self._use_opencv:
                logger.debug("Using OpenCV detection")
                detections = self._detect_opencv(image)
            else:
                logger.debug("Using ONNX detection")
                detections = self._detect_onnx(input_tensor, original_shape)

            inference_time = (time.time() - start_time) * 1000

            return FrameDetectionResult(
                timestamp=time.time(),
                frame_id=self._frame_count,
                detections=detections,
                inference_time_ms=inference_time,
                original_shape=original_shape
            )

        except Exception as e:
            logger.error(f"Detection failed: {e}")
            return FrameDetectionResult(
                timestamp=time.time(),
                frame_id=self._frame_count,
                detections=[],
                inference_time_ms=0.0,
                original_shape=(0, 0)
            )

    def _preprocess(self, image: np.ndarray) -> np.ndarray:
        """Preprocess image for inference."""
        import cv2

        # Resize to model input size
        resized = cv2.resize(image, self.config.input_size)

        # Convert BGR to RGB
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)

        # Normalize to 0-1
        normalized = rgb.astype(np.float32) / 255.0

        # HWC to CHW
        transposed = np.transpose(normalized, (2, 0, 1))

        # Add batch dimension
        batched = np.expand_dims(transposed, axis=0)

        return batched

    def _detect_onnx(self, input_tensor: np.ndarray, original_shape: Tuple[int, int]) -> List[DetectionResult]:
        """Run ONNX inference and process results."""
        if self._session is None:
            logger.error("ONNX session is None, detector not initialized properly")
            return []

        try:
            # Run inference
            outputs = self._session.run([self._output_name], {self._input_name: input_tensor})
            predictions = outputs[0]
            logger.debug(f"ONNX inference successful, raw output shape: {getattr(predictions, 'shape', None)}")

            # Handle common output layouts:
            # - YOLOv8: [1, 84, N] / [84, N]
            # - End2End/NMS export: [1, N, 6] / [N, 6] (x1,y1,x2,y2,score,class_id)
            # - Some variants: [1, N, 7] / [N, 7] (x1,y1,x2,y2,obj,score,class_id)
            if isinstance(predictions, np.ndarray) and predictions.ndim >= 3:
                predictions = predictions[0]  # Remove batch dimension when present
            logger.debug(f"Parsed model output shape: {getattr(predictions, 'shape', None)}")

            return self._parse_predictions(predictions, original_shape)
        except Exception as e:
            logger.error(f"ONNX inference failed: {e}")
            return []

    def _parse_predictions(self, predictions: np.ndarray, original_shape: Tuple[int, int]) -> List[DetectionResult]:
        """Parse multiple YOLO-style prediction formats into detection results."""
        detections = []

        if not isinstance(predictions, np.ndarray) or predictions.size == 0:
            return detections

        # Common YOLOv8 output: [84, N] -> transpose to [N, 84]
        if predictions.ndim == 2 and predictions.shape[0] >= 80 and predictions.shape[1] > predictions.shape[0]:
            predictions = predictions.T

        # Get target class IDs
        target_ids = set(TARGET_CLASSES.values())

        boxes = []
        scores = []
        class_ids = []

        # Log prediction shape
        logger.debug(f"Predictions shape: {predictions.shape}, threshold: {self.config.confidence_threshold}")

        # Sample first prediction for diagnostics
        if predictions.shape[0] > 0:
            pred = predictions[0]
            logger.debug(f"First prediction feature length: {len(pred)}")

        features = predictions.shape[1] if predictions.ndim == 2 else 0

        # Format A: [N, 6] => [x1, y1, x2, y2, score, class_id]
        if features == 6:
            self._collect_from_xyxy_score_cls(predictions, boxes, scores, class_ids, target_ids)
        # Format B: [N, 7] => [x1, y1, x2, y2, obj, score, class_id] (common E2E variant)
        elif features == 7:
            self._collect_from_xyxy_obj_score_cls(predictions, boxes, scores, class_ids, target_ids)
        # Format C: [N, >= 84] => [xc, yc, w, h, class0, class1, ...] (YOLOv8 style)
        elif features >= 8:
            self._collect_from_xywh_class_scores(predictions, boxes, scores, class_ids, target_ids)
        else:
            logger.warning(f"Unsupported prediction format: shape={predictions.shape}")
            return detections

        if not boxes:
            logger.debug(f"No boxes passed confidence threshold {self.config.confidence_threshold}")
            return detections

        logger.info(f"Found {len(boxes)} candidate boxes before NMS")

        # Apply Non-Maximum Suppression (NMS)
        try:
            import cv2
            nms_boxes = self._to_nms_xywh(boxes)
            indices = cv2.dnn.NMSBoxes(
                nms_boxes, scores,
                score_threshold=self.config.confidence_threshold,
                nms_threshold=self.config.iou_threshold
            )

            if len(indices) == 0:
                return detections

            # Handle different OpenCV versions
            if isinstance(indices, tuple):
                indices = indices[0]
            indices = indices.flatten() if hasattr(indices, 'flatten') else indices

            for idx in indices:
                idx = int(idx)
                if idx >= len(boxes):
                    continue

                box = boxes[idx]
                class_id = class_ids[idx]
                confidence = scores[idx]

                # Convert normalized coordinates to pixels
                h, w = original_shape
                x1_px = int(box[0] * w)
                y1_px = int(box[1] * h)
                x2_px = int(box[2] * w)
                y2_px = int(box[3] * h)

                # Get class name
                class_name = COCO_NAMES.get(class_id, 'unknown')

                detection = DetectionResult(
                    class_id=class_id,
                    class_name=class_name,
                    confidence=confidence,
                    bbox=tuple(box),
                    bbox_px=(x1_px, y1_px, x2_px, y2_px)
                )
                detections.append(detection)

        except Exception as e:
            logger.warning(f"NMS failed: {e}")
            # Fallback: return top-k detections without NMS
            for i, (box, score, cid) in enumerate(zip(boxes, scores, class_ids)):
                if i >= self.config.max_detections:
                    break

                h, w = original_shape
                detection = DetectionResult(
                    class_id=cid,
                    class_name=COCO_NAMES.get(cid, 'unknown'),
                    confidence=score,
                    bbox=tuple(box),
                    bbox_px=(int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h))
                )
                detections.append(detection)

        # Log final detections
        if detections:
            logger.info(f"Detection results: {len(detections)} objects - " +
                       ", ".join([f"{d.class_name}({d.confidence:.2f})" for d in detections]))
        return detections

    def _collect_from_xyxy_score_cls(
        self,
        predictions: np.ndarray,
        boxes: List[List[float]],
        scores: List[float],
        class_ids: List[int],
        target_ids: set,
    ) -> None:
        """Collect detections from [x1,y1,x2,y2,score,class_id]."""
        for pred in predictions:
            x1, y1, x2, y2, confidence, class_id = pred[:6]
            class_id = int(class_id)
            confidence = float(confidence)

            if class_id not in target_ids or confidence < self.config.confidence_threshold:
                continue

            boxes.append(self._normalize_xyxy(x1, y1, x2, y2))
            scores.append(confidence)
            class_ids.append(class_id)

    def _collect_from_xyxy_obj_score_cls(
        self,
        predictions: np.ndarray,
        boxes: List[List[float]],
        scores: List[float],
        class_ids: List[int],
        target_ids: set,
    ) -> None:
        """Collect detections from [x1,y1,x2,y2,obj,score,class_id]."""
        for pred in predictions:
            x1, y1, x2, y2, obj, score, class_id = pred[:7]
            class_id = int(class_id)
            confidence = float(obj) * float(score)

            if class_id not in target_ids or confidence < self.config.confidence_threshold:
                continue

            boxes.append(self._normalize_xyxy(x1, y1, x2, y2))
            scores.append(confidence)
            class_ids.append(class_id)

    def _collect_from_xywh_class_scores(
        self,
        predictions: np.ndarray,
        boxes: List[List[float]],
        scores: List[float],
        class_ids: List[int],
        target_ids: set,
    ) -> None:
        """Collect detections from YOLOv8-like [xc,yc,w,h,class_scores...]."""
        for pred in predictions:
            x_center, y_center, width, height = pred[:4]
            class_scores = pred[4:]
            class_id = int(np.argmax(class_scores))
            confidence = float(class_scores[class_id])

            if class_id not in target_ids:
                continue
            if confidence < self.config.confidence_threshold:
                if confidence > 0.3:
                    logger.info(
                        f"Filtered detection: class={class_id}, conf={confidence:.3f} < {self.config.confidence_threshold}"
                    )
                continue

            input_h, input_w = self.config.input_size
            x1 = (x_center - width / 2) / float(input_w)
            y1 = (y_center - height / 2) / float(input_h)
            x2 = (x_center + width / 2) / float(input_w)
            y2 = (y_center + height / 2) / float(input_h)
            boxes.append([x1, y1, x2, y2])
            scores.append(confidence)
            class_ids.append(class_id)

    def _normalize_xyxy(
        self, x1: float, y1: float, x2: float, y2: float
    ) -> List[float]:
        """Normalize xyxy boxes to 0-1 range if they are absolute pixels."""
        # Heuristic: if any coordinate > 1.5, treat as pixel space.
        if max(abs(x1), abs(y1), abs(x2), abs(y2)) > 1.5:
            input_h, input_w = self.config.input_size
            if input_w <= 0 or input_h <= 0:
                return [float(x1), float(y1), float(x2), float(y2)]
            return [
                float(x1) / float(input_w),
                float(y1) / float(input_h),
                float(x2) / float(input_w),
                float(y2) / float(input_h),
            ]

        return [float(x1), float(y1), float(x2), float(y2)]

    def _to_nms_xywh(self, boxes: List[List[float]]) -> List[List[float]]:
        """Convert normalized xyxy boxes to xywh format for cv2.dnn.NMSBoxes."""
        nms_boxes: List[List[float]] = []
        for box in boxes:
            x1, y1, x2, y2 = box
            w = max(0.0, float(x2) - float(x1))
            h = max(0.0, float(y2) - float(y1))
            nms_boxes.append([float(x1), float(y1), w, h])
        return nms_boxes

    def _detect_opencv(self, image: np.ndarray) -> List[DetectionResult]:
        """Fallback detection using OpenCV DNN."""
        import cv2

        # This is a simplified fallback - would need actual model weights
        # For now, return empty list
        logger.debug("OpenCV fallback detection not fully implemented")
        return []

    def is_initialized(self) -> bool:
        """Check if detector is initialized."""
        return self._initialized

    async def destroy(self):
        """Cleanup resources."""
        self._session = None
        self._initialized = False
        logger.info("Object detector destroyed")
