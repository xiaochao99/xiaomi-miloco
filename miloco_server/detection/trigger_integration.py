# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Integration between detection service and trigger rule system.
Handles detection events and triggers rules based on configured conditions.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Set, Callable

from miloco_server.detection.detection_service import get_detection_service
from miloco_server.detection.stream_processor import StreamDetectionEvent
from miloco_server.schema.trigger_schema import DetectionCondition, TriggerRule
from miloco_server.utils.detection_condition_checker import detection_condition_checker

logger = logging.getLogger(__name__)


class DetectionTriggerIntegration:
    """
    Integrates detection events with the trigger rule system.
    Evaluates rules with detection conditions and triggers them when conditions are met.
    """

    def __init__(self):
        self._rules: Dict[str, TriggerRule] = {}
        self._callback: Optional[Callable[[str, str, str], None]] = None
        self._enabled = False
        self._lock = asyncio.Lock()

    async def initialize(self, trigger_callback: Callable[[str, str, str], None]):
        """
        Initialize the integration.

        Args:
            trigger_callback: Callback function(rule_id, camera_id, reason) called when rule should trigger
        """
        self._callback = trigger_callback

        # Register for detection events
        service = await get_detection_service()
        service.register_event_callback(self._on_detection_event)

        self._enabled = True
        logger.info("Detection trigger integration initialized")

    async def destroy(self):
        """Cleanup and unregister."""
        self._enabled = False

        try:
            service = await get_detection_service()
            service.unregister_event_callback(self._on_detection_event)
        except Exception as e:
            logger.warning(f"Error unregistering from detection service: {e}")

        self._rules.clear()
        self._callback = None

        logger.info("Detection trigger integration destroyed")

    def add_rule(self, rule: TriggerRule):
        """Add a rule to be evaluated."""
        if not rule.detection_condition or not rule.detection_condition.enabled:
            return

        if not rule.cameras:
            logger.warning(f"Rule {rule.name} has detection condition but no cameras")
            return

        self._rules[rule.id] = rule
        logger.debug(f"Added detection rule: {rule.name} ({rule.id})")

    def remove_rule(self, rule_id: str):
        """Remove a rule."""
        if rule_id in self._rules:
            del self._rules[rule_id]
            detection_condition_checker.reset_state(rule_id)
            logger.debug(f"Removed detection rule: {rule_id}")

    def update_rule(self, rule: TriggerRule):
        """Update a rule."""
        self.remove_rule(rule.id)
        self.add_rule(rule)

    def _on_detection_event(self, event: StreamDetectionEvent):
        """Handle detection event from service."""
        if not self._enabled or not self._callback:
            return

        # Find rules that care about this camera
        matching_rules = [
            rule for rule in self._rules.values()
            if event.camera_id in rule.cameras and rule.enabled
        ]

        if not matching_rules:
            return

        # Evaluate each rule
        for rule in matching_rules:
            try:
                self._evaluate_rule(rule, event)
            except Exception as e:
                logger.error(f"Error evaluating detection rule {rule.name}: {e}")

    def _evaluate_rule(self, rule: TriggerRule, event: StreamDetectionEvent):
        """Evaluate a single rule against detection event."""
        condition = rule.detection_condition
        if not condition or not condition.enabled:
            return

        should_trigger, reason = detection_condition_checker.evaluate(
            rule_id=rule.id,
            camera_id=event.camera_id,
            condition=condition,
            detections=event.detections,
            timestamp=event.timestamp
        )

        if should_trigger:
            logger.info(
                f"Detection rule triggered: {rule.name} ({rule.id}) "
                f"from camera {event.camera_id}: {reason}"
            )

            # Call the trigger callback
            if self._callback:
                try:
                    if asyncio.iscoroutinefunction(self._callback):
                        asyncio.create_task(self._callback(rule.id, event.camera_id, reason))
                    else:
                        self._callback(rule.id, event.camera_id, reason)
                except Exception as e:
                    logger.error(f"Error in trigger callback: {e}")
        else:
            logger.debug(f"Detection rule not triggered: {rule.name} - {reason}")

    def get_monitored_rules(self) -> List[str]:
        """Get list of rule IDs being monitored."""
        return list(self._rules.keys())

    def get_rule_state(self, rule_id: str, camera_id: str) -> Optional[Dict]:
        """Get evaluation state for debugging."""
        return detection_condition_checker.get_state_info(rule_id, camera_id)


# Singleton instance
detection_trigger_integration = DetectionTriggerIntegration()


async def get_detection_trigger_integration() -> DetectionTriggerIntegration:
    """Get the detection trigger integration singleton."""
    return detection_trigger_integration
