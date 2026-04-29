# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from miloco_server.schema.habit_schema import (
    BehaviorPattern,
    HabitCategory,
    HabitEvent,
    PredictionContext,
    RulePrediction,
)

logger = logging.getLogger(__name__)


class PatternMiner:
    def __init__(self, min_occurrences: int = 3, time_bucket_minutes: int = 30):
        self.min_occurrences = min_occurrences
        self.time_bucket_minutes = time_bucket_minutes

    def extract_patterns(self, events: List[HabitEvent]) -> List[BehaviorPattern]:
        if not events:
            return []

        patterns: List[BehaviorPattern] = []
        grouped = self._group_by_entity_and_state(events)

        for (entity_id, state), group_events in grouped.items():
            time_buckets = self._bucket_by_time(group_events)

            for bucket_key, bucket_events in time_buckets.items():
                if len(bucket_events) < self.min_occurrences:
                    continue

                day_of_week, hour, minute = bucket_key
                confidence = self._calculate_confidence(bucket_events, hour, minute)
                context_conditions = self._extract_context_conditions(bucket_events)

                pattern = BehaviorPattern(
                    pattern_type=f"{entity_id}:{state}" if state else entity_id,
                    entity_id=entity_id,
                    category=group_events[0].category.value,
                    day_of_week=day_of_week,
                    hour_of_day=hour,
                    minute_of_hour=minute,
                    confidence=confidence,
                    occurrence_count=len(bucket_events),
                    last_occurrence=max(e.timestamp.timestamp() for e in bucket_events),
                    metadata={"context": context_conditions} if context_conditions else None,
                )
                patterns.append(pattern)

        context_patterns = self._extract_context_only_patterns(events)
        patterns.extend(context_patterns)

        weekday_patterns = self._extract_weekday_patterns(events)
        patterns.extend(weekday_patterns)

        patterns.sort(key=lambda p: p.confidence, reverse=True)
        logger.info("Extracted %d patterns from %d events", len(patterns), len(events))
        return patterns

    def predict(
        self, patterns: List[BehaviorPattern], context: PredictionContext
    ) -> RulePrediction:
        if not patterns:
            return RulePrediction(confidence=0.0)

        matching = []
        for p in patterns:
            if self._pattern_matches_context(p, context):
                context_boost = self._calculate_context_boost(p, context)
                adjusted_confidence = min(1.0, p.confidence * context_boost)
                matching.append((p, adjusted_confidence))

        if not matching:
            return RulePrediction(confidence=0.0)

        best_pattern, best_confidence = max(matching, key=lambda x: x[1] * x[0].occurrence_count)
        service = self._infer_service(best_pattern.entity_id, context)

        return RulePrediction(
            action=best_pattern.pattern_type,
            entity_id=best_pattern.entity_id,
            service=service,
            confidence=round(best_confidence, 3),
        )

    def _group_by_entity_and_state(
        self, events: List[HabitEvent]
    ) -> Dict[Tuple[str, Optional[str]], List[HabitEvent]]:
        grouped: Dict[Tuple[str, Optional[str]], List[HabitEvent]] = defaultdict(list)
        for event in events:
            key = (event.entity_id or "unknown", event.new_state)
            grouped[key].append(event)
        return dict(grouped)

    def _bucket_by_time(
        self, events: List[HabitEvent]
    ) -> Dict[Tuple[int, int, int], List[HabitEvent]]:
        buckets: Dict[Tuple[int, int, int], List[HabitEvent]] = defaultdict(list)
        bucket_mins = self.time_bucket_minutes

        for event in events:
            rounded_minute = (event.minute_of_hour // bucket_mins) * bucket_mins
            bucket_key = (event.day_of_week, event.hour_of_day, rounded_minute)
            buckets[bucket_key].append(event)

        return dict(buckets)

    def _calculate_confidence(
        self, events: List[HabitEvent], expected_hour: int, expected_minute: int
    ) -> float:
        if len(events) < 2:
            return 0.3

        times = [e.hour_of_day + e.minute_of_hour / 60.0 for e in events]
        expected_time = expected_hour + expected_minute / 60.0

        deviations = [abs(t - expected_time) for t in times]
        avg_deviation = np.mean(deviations)
        std_deviation = np.std(deviations) if len(deviations) > 1 else 0

        freq_score = min(1.0, len(events) / 10.0)
        consistency_score = max(0.0, 1.0 - avg_deviation / 2.0)
        std_score = max(0.0, 1.0 - std_deviation / 1.0)

        confidence = 0.3 * freq_score + 0.4 * consistency_score + 0.3 * std_score
        return round(min(1.0, max(0.1, confidence)), 3)

    def _extract_context_conditions(self, events: List[HabitEvent]) -> Dict[str, Any]:
        temps = [e.temperature for e in events if e.temperature is not None]
        humidities = [e.humidity for e in events if e.humidity is not None]
        outdoor_temps = [e.outdoor_temperature for e in events if e.outdoor_temperature is not None]
        light_levels = [e.light_level for e in events if e.light_level is not None]
        presence_values = [e.is_anyone_present for e in events if e.is_anyone_present is not None]
        home_values = [e.is_home for e in events if e.is_home is not None]
        weather_values = [e.weather for e in events if e.weather]

        conditions: Dict[str, Any] = {}

        if temps and len(temps) >= 2:
            temp_mean = float(np.mean(temps))
            temp_std = float(np.std(temps))
            conditions["temperature_mean"] = round(temp_mean, 1)
            conditions["temperature_std"] = round(temp_std, 2)
            conditions["temperature_min"] = round(float(np.percentile(temps, 10)), 1)
            conditions["temperature_max"] = round(float(np.percentile(temps, 90)), 1)

        if humidities and len(humidities) >= 2:
            hum_mean = float(np.mean(humidities))
            conditions["humidity_mean"] = round(hum_mean, 1)
            conditions["humidity_min"] = round(float(np.percentile(humidities, 10)), 1)
            conditions["humidity_max"] = round(float(np.percentile(humidities, 90)), 1)

        if outdoor_temps and len(outdoor_temps) >= 2:
            conditions["outdoor_temp_mean"] = round(float(np.mean(outdoor_temps)), 1)
            conditions["outdoor_temp_min"] = round(float(np.percentile(outdoor_temps, 10)), 1)
            conditions["outdoor_temp_max"] = round(float(np.percentile(outdoor_temps, 90)), 1)

        if light_levels and len(light_levels) >= 2:
            conditions["light_level_mean"] = round(float(np.mean(light_levels)), 0)
            conditions["light_level_min"] = round(float(np.percentile(light_levels, 10)), 0)
            conditions["light_level_max"] = round(float(np.percentile(light_levels, 90)), 0)

        if presence_values:
            present_ratio = sum(1 for v in presence_values if v) / len(presence_values)
            if present_ratio > 0.8:
                conditions["typical_presence"] = True
            elif present_ratio < 0.2:
                conditions["typical_presence"] = False

        if home_values:
            home_ratio = sum(1 for v in home_values if v) / len(home_values)
            if home_ratio > 0.8:
                conditions["typical_home"] = True
            elif home_ratio < 0.2:
                conditions["typical_home"] = False

        if weather_values:
            weather_counts: Dict[str, int] = defaultdict(int)
            for w in weather_values:
                weather_counts[w] += 1
            dominant_weather = max(weather_counts, key=weather_counts.get)
            if weather_counts[dominant_weather] / len(weather_values) > 0.6:
                conditions["typical_weather"] = dominant_weather

        return conditions

    def _extract_context_only_patterns(self, events: List[HabitEvent]) -> List[BehaviorPattern]:
        patterns: List[BehaviorPattern] = []

        temp_trigger_events = [
            e for e in events
            if e.temperature is not None
            and e.entity_id
            and e.device_domain in ("climate", "switch")
        ]
        if temp_trigger_events:
            temp_buckets: Dict[str, List[HabitEvent]] = defaultdict(list)
            for e in temp_trigger_events:
                if e.temperature < 20:
                    bucket = "cold"
                elif e.temperature < 26:
                    bucket = "comfortable"
                else:
                    bucket = "hot"
                for state_val in ("on", "off", "open", "close"):
                    if e.new_state == state_val:
                        key = f"{e.entity_id}:{state_val}:{bucket}"
                        temp_buckets[key].append(e)
                        break

            for key, bucket_events in temp_buckets.items():
                if len(bucket_events) < self.min_occurrences:
                    continue
                parts = key.rsplit(":", 2)
                entity_id, state_val, temp_range = parts[0], parts[1], parts[2]
                temps = [e.temperature for e in bucket_events]
                pattern = BehaviorPattern(
                    pattern_type=f"temp_trigger:{entity_id}:{state_val}",
                    entity_id=entity_id,
                    category=bucket_events[0].category.value,
                    day_of_week=None,
                    hour_of_day=None,
                    minute_of_hour=None,
                    confidence=self._calculate_confidence(
                        bucket_events,
                        bucket_events[0].hour_of_day,
                        bucket_events[0].minute_of_hour,
                    ),
                    occurrence_count=len(bucket_events),
                    last_occurrence=max(e.timestamp.timestamp() for e in bucket_events),
                    metadata={
                        "context": {
                            "trigger_type": "temperature",
                            "temperature_range_label": temp_range,
                            "temperature_mean": round(float(np.mean(temps)), 1),
                            "temperature_min": round(float(np.percentile(temps, 10)), 1),
                            "temperature_max": round(float(np.percentile(temps, 90)), 1),
                        }
                    },
                )
                patterns.append(pattern)

        presence_events = [
            e for e in events
            if e.is_anyone_present is not None
            and e.entity_id
            and e.new_state in ("on", "off")
        ]
        if presence_events:
            presence_buckets: Dict[str, List[HabitEvent]] = defaultdict(list)
            for e in presence_events:
                key = f"{e.entity_id}:{e.new_state}:{'present' if e.is_anyone_present else 'absent'}"
                presence_buckets[key].append(e)

            for key, bucket_events in presence_buckets.items():
                if len(bucket_events) < self.min_occurrences:
                    continue
                parts = key.rsplit(":", 2)
                entity_id, state_val, presence = parts[0], parts[1], parts[2]
                present_count = sum(1 for e in bucket_events if e.is_anyone_present)
                pattern = BehaviorPattern(
                    pattern_type=f"presence_trigger:{entity_id}:{state_val}",
                    entity_id=entity_id,
                    category=bucket_events[0].category.value,
                    day_of_week=None,
                    hour_of_day=None,
                    minute_of_hour=None,
                    confidence=self._calculate_confidence(
                        bucket_events,
                        bucket_events[0].hour_of_day,
                        bucket_events[0].minute_of_hour,
                    ),
                    occurrence_count=len(bucket_events),
                    last_occurrence=max(e.timestamp.timestamp() for e in bucket_events),
                    metadata={
                        "context": {
                            "trigger_type": "presence",
                            "typical_presence": presence == "present",
                            "presence_ratio": round(present_count / len(bucket_events), 2),
                        }
                    },
                )
                patterns.append(pattern)

        return patterns

    def _extract_weekday_patterns(self, events: List[HabitEvent]) -> List[BehaviorPattern]:
        weekday_events = [e for e in events if not e.is_weekend]
        weekend_events = [e for e in events if e.is_weekend]

        patterns = []

        for group_label, group_events in [("weekday", weekday_events), ("weekend", weekend_events)]:
            if len(group_events) < self.min_occurrences:
                continue

            entity_groups: Dict[str, List[HabitEvent]] = defaultdict(list)
            for e in group_events:
                key = e.entity_id or "unknown"
                entity_groups[key].append(e)

            for entity_id, ent_events in entity_groups.items():
                if len(ent_events) < self.min_occurrences:
                    continue

                times = [e.hour_of_day + e.minute_of_hour / 60.0 for e in ent_events]
                avg_time = np.mean(times)
                hour = int(avg_time)
                minute = int((avg_time - hour) * 60)

                confidence = self._calculate_confidence(ent_events, hour, minute)
                context_conditions = self._extract_context_conditions(ent_events)

                pattern = BehaviorPattern(
                    pattern_type=f"{group_label}:{entity_id}",
                    entity_id=entity_id,
                    category=ent_events[0].category.value,
                    day_of_week=None,
                    hour_of_day=hour,
                    minute_of_hour=minute,
                    confidence=confidence * 0.9,
                    occurrence_count=len(ent_events),
                    last_occurrence=max(e.timestamp.timestamp() for e in ent_events),
                    metadata={"period": group_label, "context": context_conditions} if context_conditions else {"period": group_label},
                )
                patterns.append(pattern)

        return patterns

    def _pattern_matches_context(
        self, pattern: BehaviorPattern, context: PredictionContext
    ) -> bool:
        if pattern.day_of_week is not None and pattern.day_of_week != context.day_of_week:
            if not (pattern.metadata and pattern.metadata.get("period")):
                return False

        if pattern.entity_id and context.entity_id and pattern.entity_id != context.entity_id:
            return False

        if pattern.hour_of_day is not None:
            hour_diff = abs(pattern.hour_of_day - context.hour_of_day)
            if hour_diff > 2 and hour_diff < 22:
                return False

        ctx_conditions = (pattern.metadata or {}).get("context", {})
        if not ctx_conditions:
            return True

        trigger_type = ctx_conditions.get("trigger_type")

        if trigger_type == "temperature":
            if context.temperature is None:
                return True
            temp_min = ctx_conditions.get("temperature_min")
            temp_max = ctx_conditions.get("temperature_max")
            if temp_min is not None and temp_max is not None:
                if not (temp_min - 3 <= context.temperature <= temp_max + 3):
                    return False
            return True

        if trigger_type == "presence":
            return True

        if ctx_conditions.get("typical_presence") is not None:
            if ctx_conditions["typical_presence"] and not context.is_anyone_present:
                return False

        if ctx_conditions.get("typical_home") is not None:
            if ctx_conditions["typical_home"] and not context.is_home:
                return False

        if ctx_conditions.get("temperature_mean") is not None and context.temperature is not None:
            temp_diff = abs(ctx_conditions["temperature_mean"] - context.temperature)
            if temp_diff > 8:
                return False

        if ctx_conditions.get("typical_weather") and context.weather:
            if ctx_conditions["typical_weather"] != context.weather:
                return False

        return True

    def _calculate_context_boost(
        self, pattern: BehaviorPattern, context: PredictionContext
    ) -> float:
        ctx_conditions = (pattern.metadata or {}).get("context", {})
        if not ctx_conditions:
            return 1.0

        boost = 1.0

        if ctx_conditions.get("temperature_mean") is not None and context.temperature is not None:
            temp_diff = abs(ctx_conditions["temperature_mean"] - context.temperature)
            if temp_diff < 2:
                boost *= 1.15
            elif temp_diff < 5:
                boost *= 1.05
            elif temp_diff > 8:
                boost *= 0.7

        if ctx_conditions.get("humidity_mean") is not None and context.humidity is not None:
            hum_diff = abs(ctx_conditions["humidity_mean"] - context.humidity)
            if hum_diff < 10:
                boost *= 1.05
            elif hum_diff > 25:
                boost *= 0.85

        if ctx_conditions.get("light_level_mean") is not None and context.light_level is not None:
            light_diff = abs(ctx_conditions["light_level_mean"] - context.light_level)
            if light_diff < 100:
                boost *= 1.1
            elif light_diff > 300:
                boost *= 0.8

        if ctx_conditions.get("outdoor_temp_mean") is not None and context.outdoor_temperature is not None:
            outdoor_diff = abs(ctx_conditions["outdoor_temp_mean"] - context.outdoor_temperature)
            if outdoor_diff < 3:
                boost *= 1.1
            elif outdoor_diff > 10:
                boost *= 0.8

        trigger_type = ctx_conditions.get("trigger_type")
        if trigger_type == "presence":
            expected_present = ctx_conditions.get("typical_presence", True)
            if expected_present == context.is_anyone_present:
                boost *= 1.2
            else:
                boost *= 0.5
        elif ctx_conditions.get("typical_presence") is not None:
            if ctx_conditions["typical_presence"] == context.is_anyone_present:
                boost *= 1.1
            else:
                boost *= 0.7

        if ctx_conditions.get("typical_home") is not None:
            if ctx_conditions["typical_home"] == context.is_home:
                boost *= 1.1
            else:
                boost *= 0.3

        if ctx_conditions.get("typical_weather") and context.weather:
            if ctx_conditions["typical_weather"] == context.weather:
                boost *= 1.1
            else:
                boost *= 0.85

        return max(0.3, min(1.5, boost))

    def _infer_service(self, entity_id: Optional[str], context: PredictionContext) -> str:
        if not entity_id:
            return "turn_on"

        domain = entity_id.split(".")[0]

        if domain in ("light", "switch"):
            current = context.current_state
            if current == "on":
                return "turn_off"
            return "turn_on"

        if domain == "cover":
            current = context.current_state
            if current == "open" or current == "100":
                return "close_cover"
            return "open_cover"

        if domain == "climate":
            return "turn_on"

        return "turn_on"
