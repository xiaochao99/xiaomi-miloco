# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Real-time object detection module for Miloco.
Provides efficient local detection of persons, cats, and dogs from video streams.
"""

from miloco_server.detection.detector import ObjectDetector, DetectionResult, DetectionConfig
from miloco_server.detection.stream_processor import StreamProcessor, StreamConfig
from miloco_server.detection.detection_service import DetectionService

__all__ = [
    'ObjectDetector',
    'DetectionResult', 
    'DetectionConfig',
    'StreamProcessor',
    'StreamConfig',
    'DetectionService',
]
