# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from miloco_server.dao.habit_dao import HabitDAO
from miloco_server.schema.habit_schema import (
    BehaviorPattern,
    HabitCategory,
    PredictionContext,
    PredictionResult,
    TimePrediction,
)
from miloco_server.service.confidence_calculator import ConfidenceCalculator
from miloco_server.service.pattern_miner import PatternMiner
from miloco_server.service.time_predictor import TimePredictor

logger = logging.getLogger(__name__)


class BehaviorLearner:
    _instance: Optional["BehaviorLearner"] = None

    def __init__(
        self,
        habit_dao: HabitDAO,
        pattern_miner: Optional[PatternMiner] = None,
        time_predictor: Optional[TimePredictor] = None,
        confidence_calculator: Optional[ConfidenceCalculator] = None,
        min_occurrences: int = 3,
        time_bucket_minutes: int = 30,
    ):
        self._habit_dao = habit_dao
        self._pattern_miner = pattern_miner or PatternMiner(
            min_occurrences=min_occurrences,
            time_bucket_minutes=time_bucket_minutes,
        )
        self._time_predictor = time_predictor or TimePredictor()
        self._confidence_calculator = confidence_calculator or ConfidenceCalculator()
        self._context_provider = None
        self._stats = {
            "total_patterns": 0,
            "learn_cycles": 0,
            "total_predictions": 0,
        }
        BehaviorLearner._instance = self

    @classmethod
    def get_instance(cls) -> Optional["BehaviorLearner"]:
        return cls._instance

    def set_context_provider(self, provider) -> None:
        self._context_provider = provider

    async def learn(self, days: int = 30) -> List[BehaviorPattern]:
        logger.info("Starting habit learning, days=%d", days)
        self._stats["learn_cycles"] += 1

        events = self._habit_dao.get_recent_events(hours=days * 24, limit=5000)
        if not events:
            logger.info("No events found for learning")
            return []

        new_patterns = self._pattern_miner.extract_patterns(events)
        self._habit_dao.save_patterns(new_patterns)
        self._stats["total_patterns"] = len(new_patterns)

        self._update_slot_patterns(new_patterns)

        logger.info("Learned %d new patterns", len(new_patterns))
        return new_patterns

    async def predict(self) -> List[PredictionResult]:
        logger.info("Starting prediction")
        self._stats["total_predictions"] += 1

        all_patterns = self._habit_dao.get_patterns(min_confidence=0.1)
        if not all_patterns:
            logger.info("No patterns found for prediction")
            return []

        context = self._build_prediction_context()
        predictions: List[PredictionResult] = []
        seen_actions: set = set()

        CONTROLLABLE_DOMAINS = {
            "light", "switch", "climate", "cover", "fan",
            "lock", "media_player", "vacuum", "humidifier",
            "dehumidifier", "air_purifier", "curtain", "scene",
            "input_boolean", "input_number",
        }

        for pattern in all_patterns:
            if not pattern.entity_id:
                continue

            domain = pattern.entity_id.split(".")[0] if "." in pattern.entity_id else ""
            if domain not in CONTROLLABLE_DOMAINS:
                continue

            pattern.context = context

            tp_ctx = PredictionContext(
                current_time=context.current_time,
                day_of_week=context.day_of_week,
                hour_of_day=context.hour_of_day,
                minute_of_hour=context.minute_of_hour,
                is_weekend=context.is_weekend,
                pattern_type=pattern.pattern_type or "",
                temperature=context.temperature,
                humidity=context.humidity,
                light_level=context.light_level,
                is_home=context.is_home,
                is_anyone_present=context.is_anyone_present,
                outdoor_temperature=context.outdoor_temperature,
                weather=context.weather,
                wind_speed=context.wind_speed,
                air_quality=context.air_quality,
                time_period=context.time_period,
                water_leak_detected=context.water_leak_detected,
                traffic_restricted=context.traffic_restricted,
            )

            time_prediction = await self._time_predictor.predict(tp_ctx)

            confidence = self._confidence_calculator.calculate_confidence(
                pattern, context
            )

            if time_prediction.confidence:
                combined = (confidence + time_prediction.confidence) / 2
            else:
                combined = confidence

            if combined < 0.1:
                continue

            expected_time = 0.0
            if time_prediction.time:
                expected_time = time_prediction.time.hour + time_prediction.time.minute / 60.0
                time_diff = expected_time - (context.hour_of_day + context.minute_of_hour / 60.0)
                if time_diff < -0.5:
                    continue

            confidence = round(max(0.1, min(1.0, combined)), 3)

            category = HabitCategory(pattern.category) if pattern.category else HabitCategory.UNKNOWN

            action_key = f"{pattern.entity_id}:{pattern.pattern_type}:{context.hour_of_day}"
            if action_key in seen_actions:
                continue
            seen_actions.add(action_key)

            last_occurrence_dt = None
            if pattern.last_occurrence:
                last_occurrence_dt = datetime.fromtimestamp(pattern.last_occurrence)

            action_desc = pattern.pattern_type
            if ":" in action_desc:
                parts = action_desc.split(":")
                if len(parts) == 2:
                    action_desc = parts[1]

            predictions.append(
                PredictionResult(
                    entity_id=pattern.entity_id,
                    predicted_action=action_desc,
                    predicted_time=time_prediction.time,
                    expected_time=round(expected_time, 2),
                    confidence=confidence,
                    pattern_type=category.value,
                    time_confidence=time_prediction.confidence,
                    last_occurrence=last_occurrence_dt,
                    occurrence_count=pattern.occurrence_count,
                )
            )

        predictions.sort(key=lambda p: p.confidence, reverse=True)
        logger.info("Generated %d predictions", len(predictions))
        return predictions

    def _update_slot_patterns(self, patterns: List[BehaviorPattern]) -> None:
        now = datetime.now()
        current_hour = now.hour
        for p in patterns:
            if p.hour_of_day is not None:
                time_diff = abs(p.hour_of_day - current_hour)
                if time_diff > 12:
                    time_diff = 24 - time_diff
                if time_diff <= 2:
                    self._habit_dao.save_patterns([p])

    def _build_prediction_context(self) -> PredictionContext:
        now = datetime.now()
        ctx = PredictionContext(
            current_time=now,
            day_of_week=now.weekday(),
            hour_of_day=now.hour,
            minute_of_hour=now.minute,
            is_weekend=now.weekday() >= 5,
        )
        if self._context_provider:
            try:
                env_ctx = self._context_provider.get_context()
                ctx.temperature = env_ctx.temperature
                ctx.humidity = env_ctx.humidity
                ctx.light_level = env_ctx.light_level
                ctx.is_home = env_ctx.is_home
                ctx.is_anyone_present = env_ctx.is_anyone_present
                ctx.outdoor_temperature = env_ctx.outdoor_temperature
                ctx.weather = env_ctx.weather
                ctx.wind_speed = env_ctx.wind_speed
                ctx.air_quality = env_ctx.air_quality
                ctx.time_period = env_ctx.time_period
                ctx.water_leak_detected = env_ctx.water_leak_detected
                ctx.traffic_restricted = env_ctx.traffic_restricted
                ctx.environment = env_ctx.to_dict()
            except Exception as e:
                logger.debug("Failed to get environment context: %s", e)
        return ctx

    def get_stats(self) -> Dict[str, any]:
        return {**self._stats}
