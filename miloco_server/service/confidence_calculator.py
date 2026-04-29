# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

import logging
from typing import Optional

from miloco_server.schema.habit_schema import BehaviorPattern, PredictionContext

logger = logging.getLogger(__name__)


class ConfidenceCalculator:
    TIME_MATCH_WEIGHT = 0.4
    RULE_MATCH_WEIGHT = 0.3
    CONTEXT_WEIGHT = 0.2
    RECENCY_WEIGHT = 0.1

    def __init__(self):
        pass

    def calculate_confidence(
        self,
        pattern: BehaviorPattern,
        context: PredictionContext,
    ) -> float:
        time_score = self._calculate_time_match(pattern, context)
        rule_score = self._calculate_rule_match(pattern, context)
        context_score = self._calculate_context_match(pattern, context)
        recency_score = self._calculate_recency(pattern)

        final = (
            self.TIME_MATCH_WEIGHT * time_score
            + self.RULE_MATCH_WEIGHT * rule_score
            + self.CONTEXT_WEIGHT * context_score
            + self.RECENCY_WEIGHT * recency_score
        )
        return round(max(0.0, min(1.0, final)), 3)

    def _calculate_time_match(
        self, pattern: BehaviorPattern, context: PredictionContext
    ) -> float:
        score = 0.5

        if pattern.day_of_week is not None:
            if pattern.day_of_week == context.day_of_week:
                score += 0.3
            else:
                score -= 0.2

        if pattern.hour_of_day is not None:
            hour_diff = abs(pattern.hour_of_day - context.hour_of_day)
            if hour_diff <= 1:
                score += 0.3
            elif hour_diff <= 2:
                score += 0.2
            elif hour_diff <= 3:
                score += 0.1

        return max(0.0, min(1.0, score))

    def _calculate_rule_match(
        self, pattern: BehaviorPattern, context: PredictionContext
    ) -> float:
        score = 0.5

        if context.pattern_type and pattern.pattern_type:
            if context.pattern_type in pattern.pattern_type:
                score += 0.3

        if context.entity_id and pattern.entity_id:
            if context.entity_id == pattern.entity_id:
                score += 0.3
            else:
                score -= 0.2

        if pattern.occurrence_count:
            freq_bonus = min(0.3, pattern.occurrence_count / 20.0)
            score += freq_bonus

        return max(0.0, min(1.0, score))

    def _calculate_context_match(
        self, pattern: BehaviorPattern, context: PredictionContext
    ) -> float:
        score = 0.5

        ctx_conditions = (pattern.metadata or {}).get("context", {})
        if not ctx_conditions:
            return 0.6

        if ctx_conditions.get("temperature_mean") is not None and context.temperature is not None:
            temp_diff = abs(ctx_conditions["temperature_mean"] - context.temperature)
            if temp_diff < 2:
                score += 0.3
            elif temp_diff < 5:
                score += 0.15
            elif temp_diff > 10:
                score -= 0.3

        if ctx_conditions.get("humidity_mean") is not None and context.humidity is not None:
            hum_diff = abs(ctx_conditions["humidity_mean"] - context.humidity)
            if hum_diff < 10:
                score += 0.2
            elif hum_diff > 25:
                score -= 0.15

        if ctx_conditions.get("light_level_mean") is not None and context.light_level is not None:
            light_diff = abs(ctx_conditions["light_level_mean"] - context.light_level)
            if light_diff < 100:
                score += 0.2
            elif light_diff > 300:
                score -= 0.1

        if ctx_conditions.get("outdoor_temp_mean") is not None and context.outdoor_temperature is not None:
            outdoor_diff = abs(ctx_conditions["outdoor_temp_mean"] - context.outdoor_temperature)
            if outdoor_diff < 3:
                score += 0.2
            elif outdoor_diff > 10:
                score -= 0.15

        if ctx_conditions.get("typical_presence") is not None:
            if ctx_conditions["typical_presence"] == context.is_anyone_present:
                score += 0.2
            else:
                score -= 0.3

        if ctx_conditions.get("typical_home") is not None:
            if ctx_conditions["typical_home"] == context.is_home:
                score += 0.15
            else:
                score -= 0.4

        if ctx_conditions.get("typical_weather") and context.weather:
            if ctx_conditions["typical_weather"] == context.weather:
                score += 0.15
            else:
                score -= 0.1

        if ctx_conditions.get("trigger_type") == "temperature":
            score += 0.1
            if context.temperature is not None:
                temp_min = ctx_conditions.get("temperature_min")
                temp_max = ctx_conditions.get("temperature_max")
                if temp_min is not None and temp_max is not None:
                    if temp_min <= context.temperature <= temp_max:
                        score += 0.25

        if ctx_conditions.get("trigger_type") == "presence":
            score += 0.1
            expected = ctx_conditions.get("typical_presence", True)
            if expected == context.is_anyone_present:
                score += 0.3

        return max(0.0, min(1.0, score))

    def _calculate_recency(self, pattern: BehaviorPattern) -> float:
        if not pattern.last_occurrence:
            return 0.3

        import time
        hours_since = (time.time() - pattern.last_occurrence) / 3600

        if hours_since < 24:
            return 1.0
        if hours_since < 168:
            return 0.8
        if hours_since < 720:
            return 0.5
        return 0.3
