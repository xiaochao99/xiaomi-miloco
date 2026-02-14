# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Detection condition checker for evaluating object detection-based trigger rules.
Integrates with the detection service to evaluate trigger conditions.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
from collections import defaultdict

from miloco_server.detection.stream_processor import DetectionResult
from miloco_server.schema.trigger_schema import (
    DetectionCondition,
    DetectionLogicType,
    DetectionTargetType,
)

logger = logging.getLogger(__name__)


@dataclass
class DetectionTriggerState:
    """Tracks detection state for trigger evaluation."""
    target_presence: Dict[str, float] = field(default_factory=dict)  # target -> first_seen_time
    last_trigger_time: float = 0.0
    consecutive_detections: int = 0
    last_detection_time: float = 0.0


class DetectionConditionChecker:
    """
    Evaluates detection conditions for trigger rules.
    Manages trigger state and cooldown periods.
    """

    def __init__(self):
        # Track state per rule per camera
        self._trigger_states: Dict[str, Dict[str, DetectionTriggerState]] = defaultdict(
            lambda: defaultdict(DetectionTriggerState)
        )
        self._target_presence_history: Dict[str, Dict[str, List[Tuple[float, bool]]]] = defaultdict(
            lambda: defaultdict(list)
        )

    def evaluate(
        self,
        rule_id: str,
        camera_id: str,
        condition: DetectionCondition,
        detections: List[DetectionResult],
        timestamp: Optional[float] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Evaluate if detection condition is met.

        Args:
            rule_id: Rule identifier
            camera_id: Camera identifier
            condition: Detection condition configuration
            detections: Current frame detections
            timestamp: Current timestamp

        Returns:
            Tuple of (should_trigger, reason)
        """
        if not condition.enabled:
            return False, "Detection condition not enabled"

        if not condition.targets:
            return False, "No detection targets configured"

        current_time = timestamp or time.time()
        state = self._trigger_states[rule_id][camera_id]

        # Filter detections by confidence threshold
        valid_detections = [
            d for d in detections
            if d.confidence >= condition.confidence_threshold
        ]

        # Count detected targets
        detected_targets = self._count_detected_targets(
            valid_detections,
            condition.targets
        )

        # Check cooldown
        cooldown_remaining = self._get_cooldown_remaining(state, condition, current_time)
        if cooldown_remaining > 0:
            return False, f"In cooldown period ({cooldown_remaining:.1f}s remaining)"

        # Update presence tracking
        self._update_target_presence(
            rule_id, camera_id, detected_targets, condition.targets, current_time
        )

        # Evaluate detection logic
        logic_met = self._evaluate_logic(condition, detected_targets, valid_detections)

        if not logic_met:
            # Reset consecutive counter if condition not met
            state.consecutive_detections = 0
            return False, "Detection logic not satisfied"

        # Update consecutive detection counter
        state.consecutive_detections += 1
        state.last_detection_time = current_time

        # Check sensitivity (consecutive frames required)
        required_consecutive = self._get_required_consecutive(condition.sensitivity)
        if state.consecutive_detections < required_consecutive:
            return False, (
                f"Building confidence ({state.consecutive_detections}/{required_consecutive} "
                f"consecutive detections)"
            )

        # Check minimum duration if configured
        if condition.min_duration_seconds:
            duration_met = self._check_min_duration(
                rule_id, camera_id, detected_targets, condition, current_time
            )
            if not duration_met:
                return False, "Minimum duration not met"

        # All conditions met - should trigger
        state.last_trigger_time = current_time
        state.consecutive_detections = 0  # Reset after trigger

        trigger_reason = self._build_trigger_reason(detected_targets, valid_detections)
        return True, trigger_reason

    def _count_detected_targets(
        self,
        detections: List[DetectionResult],
        target_types: List[DetectionTargetType]
    ) -> Dict[str, int]:
        """Count occurrences of each target type in detections."""
        counts = defaultdict(int)

        for det in detections:
            # Map COCO class names to our target types
            target_type = self._map_class_to_target(det.class_name)
            if target_type and target_type in [t.value for t in target_types]:
                counts[target_type] += 1

        return dict(counts)

    def _map_class_to_target(self, class_name: str) -> Optional[str]:
        """Map COCO class name to detection target type."""
        mapping = {
            "person": "person",
            "cat": "cat",
            "dog": "dog",
        }
        return mapping.get(class_name.lower())

    def _evaluate_logic(
        self,
        condition: DetectionCondition,
        detected_targets: Dict[str, int],
        detections: List[DetectionResult]
    ) -> bool:
        """Evaluate detection logic against detected targets."""
        logic = condition.logic
        expected_targets = [t.value for t in condition.targets]

        if logic == DetectionLogicType.ANY:
            # Any of the specified targets must be detected
            return any(
                target in detected_targets and detected_targets[target] > 0
                for target in expected_targets
            )

        elif logic == DetectionLogicType.ALL:
            # All specified targets must be detected
            return all(
                target in detected_targets and detected_targets[target] > 0
                for target in expected_targets
            )

        elif logic == DetectionLogicType.COUNT:
            # Total count across all targets must meet minimum
            if condition.min_count is None:
                logger.warning("COUNT logic requires min_count to be set")
                return False

            total_count = sum(detected_targets.values())
            return total_count >= condition.min_count

        return False

    def _update_target_presence(
        self,
        rule_id: str,
        camera_id: str,
        detected_targets: Dict[str, int],
        expected_targets: List[DetectionTargetType],
        timestamp: float
    ):
        """Update target presence tracking for duration checks."""
        state = self._trigger_states[rule_id][camera_id]

        for target_type in expected_targets:
            target_key = target_type.value
            is_present = target_key in detected_targets and detected_targets[target_key] > 0

            if is_present:
                if target_key not in state.target_presence:
                    state.target_presence[target_key] = timestamp
            else:
                # Target not detected, remove from presence
                state.target_presence.pop(target_key, None)

    def _check_min_duration(
        self,
        rule_id: str,
        camera_id: str,
        detected_targets: Dict[str, int],
        condition: DetectionCondition,
        current_time: float
    ) -> bool:
        """Check if targets have been present for minimum duration."""
        if not condition.min_duration_seconds:
            return True

        state = self._trigger_states[rule_id][camera_id]

        # Check if all currently detected targets have been present long enough
        for target_key, first_seen in state.target_presence.items():
            if target_key in detected_targets and detected_targets[target_key] > 0:
                duration = current_time - first_seen
                if duration < condition.min_duration_seconds:
                    return False

        return True

    def _get_cooldown_remaining(
        self,
        state: DetectionTriggerState,
        condition: DetectionCondition,
        current_time: float
    ) -> float:
        """Get remaining cooldown time in seconds."""
        if state.last_trigger_time == 0:
            return 0

        elapsed = current_time - state.last_trigger_time
        remaining = condition.cooldown_seconds - elapsed
        return max(0, remaining)

    def _get_required_consecutive(self, sensitivity: int) -> int:
        """
        Get required consecutive detections based on sensitivity.
        Higher sensitivity = fewer consecutive frames needed.
        """
        # Map sensitivity 1-10 to consecutive frames 5-1
        # Sensitivity 1 (low) = 5 consecutive frames
        # Sensitivity 10 (high) = 1 consecutive frame
        return max(1, 6 - (sensitivity // 2))

    def _build_trigger_reason(
        self,
        detected_targets: Dict[str, int],
        detections: List[DetectionResult]
    ) -> str:
        """Build human-readable trigger reason."""
        parts = []
        for target, count in detected_targets.items():
            if count > 0:
                if count == 1:
                    parts.append(f"检测到1个{self._translate_target(target)}")
                else:
                    parts.append(f"检测到{count}个{self._translate_target(target)}")

        return "，".join(parts) if parts else "检测到目标"

    def _translate_target(self, target: str) -> str:
        """Translate target type to Chinese."""
        translations = {
            "person": "人",
            "cat": "猫",
            "dog": "狗",
        }
        return translations.get(target, target)

    def reset_state(self, rule_id: Optional[str] = None, camera_id: Optional[str] = None):
        """Reset trigger state for a rule or camera."""
        if rule_id and camera_id:
            if rule_id in self._trigger_states and camera_id in self._trigger_states[rule_id]:
                del self._trigger_states[rule_id][camera_id]
        elif rule_id:
            if rule_id in self._trigger_states:
                del self._trigger_states[rule_id]
        else:
            self._trigger_states.clear()

    def get_state_info(self, rule_id: str, camera_id: str) -> Optional[Dict]:
        """Get current state info for debugging."""
        if rule_id not in self._trigger_states:
            return None
        if camera_id not in self._trigger_states[rule_id]:
            return None

        state = self._trigger_states[rule_id][camera_id]
        return {
            "target_presence": state.target_presence,
            "last_trigger_time": state.last_trigger_time,
            "consecutive_detections": state.consecutive_detections,
            "last_detection_time": state.last_detection_time,
        }


# Singleton instance
detection_condition_checker = DetectionConditionChecker()
