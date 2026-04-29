# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

import logging
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, Dict, List, Optional, Tuple

from miloco_server.schema.habit_schema import DecisionAction, DecisionContext

logger = logging.getLogger(__name__)


class RiskLevel(IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class RiskAssessment:
    level: RiskLevel
    factors: List[Tuple[str, str]] = field(default_factory=list)
    requires_inquiry: bool = False
    requires_broadcast: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level.name,
            "level_value": self.level.value,
            "factors": [{"name": n, "detail": d} for n, d in self.factors],
            "requires_inquiry": self.requires_inquiry,
            "requires_broadcast": self.requires_broadcast,
        }


class RiskAssessor:
    DOMAIN_RISK_MAP: Dict[str, RiskLevel] = {
        "light": RiskLevel.LOW,
        "switch": RiskLevel.LOW,
        "fan": RiskLevel.LOW,
        "humidifier": RiskLevel.LOW,
        "cover": RiskLevel.MEDIUM,
        "climate": RiskLevel.MEDIUM,
        "media_player": RiskLevel.MEDIUM,
        "water_heater": RiskLevel.MEDIUM,
        "lock": RiskLevel.HIGH,
        "camera": RiskLevel.HIGH,
        "alarm_control_panel": RiskLevel.CRITICAL,
    }

    SECURITY_ENTITY_PREFIXES = (
        "alarm_control_panel",
        "lock",
        "binary_sensor.door",
        "binary_sensor.window",
        "binary_sensor.motion",
        "binary_sensor.presence",
    )

    NIGHT_START = 22
    NIGHT_END = 7

    async def assess(
        self,
        action: DecisionAction,
        context: DecisionContext,
    ) -> RiskAssessment:
        factors: List[Tuple[str, str]] = []
        max_level = RiskLevel.LOW

        device_level = self._assess_device_risk(action.entity_id)
        factors.append(("device_type", f"{action.entity_id} -> {device_level.name}"))
        max_level = max(max_level, device_level)

        if max_level < RiskLevel.CRITICAL:
            security_level = self._assess_security_risk(action.entity_id)
            if security_level > RiskLevel.LOW:
                factors.append(("security", f"Security device -> {security_level.name}"))
                max_level = max(max_level, security_level)

        if max_level < RiskLevel.HIGH:
            time_level = self._assess_time_risk(context)
            if time_level > RiskLevel.LOW:
                factors.append(("time_sensitivity", f"Night mode -> {time_level.name}"))
                max_level = max(max_level, time_level)

        if max_level < RiskLevel.HIGH:
            conf_level = self._assess_confidence_risk(action.prediction_confidence)
            if conf_level > RiskLevel.LOW:
                factors.append(("low_confidence", f"confidence={action.prediction_confidence:.2f} -> {conf_level.name}"))
                max_level = max(max_level, conf_level)

        requires_inquiry = max_level >= RiskLevel.HIGH
        requires_broadcast = max_level >= RiskLevel.MEDIUM

        assessment = RiskAssessment(
            level=max_level,
            factors=factors,
            requires_inquiry=requires_inquiry,
            requires_broadcast=requires_broadcast,
        )

        logger.debug("Risk assessment for %s: %s", action.entity_id, assessment.to_dict())
        return assessment

    def _assess_device_risk(self, entity_id: str) -> RiskLevel:
        domain = entity_id.split(".")[0] if entity_id else ""
        return self.DOMAIN_RISK_MAP.get(domain, RiskLevel.MEDIUM)

    def _assess_security_risk(self, entity_id: str) -> RiskLevel:
        if not entity_id:
            return RiskLevel.LOW
        for prefix in self.SECURITY_ENTITY_PREFIXES:
            if entity_id.startswith(prefix):
                return RiskLevel.CRITICAL
        return RiskLevel.LOW

    def _assess_time_risk(self, context: DecisionContext) -> RiskLevel:
        hour = context.current_time.hour
        if hour >= self.NIGHT_START or hour < self.NIGHT_END:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    def _assess_confidence_risk(self, confidence: float) -> RiskLevel:
        if confidence < 0.4:
            return RiskLevel.HIGH
        if confidence < 0.6:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    def get_risk_limit_from_config(self, limit_str: str) -> RiskLevel:
        mapping = {
            "LOW": RiskLevel.LOW,
            "MEDIUM": RiskLevel.MEDIUM,
            "HIGH": RiskLevel.HIGH,
            "CRITICAL": RiskLevel.CRITICAL,
        }
        return mapping.get(limit_str.upper(), RiskLevel.HIGH)
