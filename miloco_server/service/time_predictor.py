# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

import numpy as np

from miloco_server.schema.habit_schema import (
    BehaviorPattern,
    HabitEvent,
    PredictionContext,
    TimePrediction,
)

logger = logging.getLogger(__name__)


@dataclass
class TimeModel:
    pattern_type: str = ""
    weekday_ewma_hour: float = 0.0
    weekday_ewma_std: float = 0.5
    weekend_ewma_hour: float = 0.0
    weekend_ewma_std: float = 0.5
    weekday_samples: int = 0
    weekend_samples: int = 0
    last_trained: Optional[float] = None

    def get_ewma_hour(self, is_weekend: bool) -> float:
        return self.weekend_ewma_hour if is_weekend else self.weekday_ewma_hour

    def get_ewma_std(self, is_weekend: bool) -> float:
        return self.weekend_ewma_std if is_weekend else self.weekday_ewma_std

    def get_samples(self, is_weekend: bool) -> int:
        return self.weekend_samples if is_weekend else self.weekday_samples

    def to_dict(self) -> Dict:
        return {
            "pattern_type": self.pattern_type,
            "weekday_ewma_hour": self.weekday_ewma_hour,
            "weekday_ewma_std": self.weekday_ewma_std,
            "weekend_ewma_hour": self.weekend_ewma_hour,
            "weekend_ewma_std": self.weekend_ewma_std,
            "weekday_samples": self.weekday_samples,
            "weekend_samples": self.weekend_samples,
            "last_trained": self.last_trained,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "TimeModel":
        return cls(**data)


class TimePredictor:
    def __init__(self, alpha: float = 0.3, min_samples: int = 5):
        self._alpha = alpha
        self._min_samples = min_samples
        self._models: Dict[str, TimeModel] = {}

    async def train(self, pattern: BehaviorPattern, events: List[HabitEvent]) -> None:
        pattern_key = pattern.pattern_type
        model = self._models.get(pattern_key) or TimeModel(pattern_type=pattern_key)

        weekday_events = [e for e in events if not e.is_weekend]
        weekend_events = [e for e in events if e.is_weekend]

        if weekday_events:
            hours = np.array([e.hour_of_day + e.minute_of_hour / 60.0 for e in weekday_events])
            model = self._update_ewma(model, hours, is_weekend=False)

        if weekend_events:
            hours = np.array([e.hour_of_day + e.minute_of_hour / 60.0 for e in weekend_events])
            model = self._update_ewma(model, hours, is_weekend=True)

        model.last_trained = datetime.now().timestamp()
        self._models[pattern_key] = model

        logger.debug(
            "Trained time model for %s: weekday=%.2f±%.2f (%d), weekend=%.2f±%.2f (%d)",
            pattern_key,
            model.weekday_ewma_hour, model.weekday_ewma_std, model.weekday_samples,
            model.weekend_ewma_hour, model.weekend_ewma_std, model.weekend_samples,
        )

    async def predict(self, context: PredictionContext) -> TimePrediction:
        pattern_key = context.pattern_type
        if not pattern_key:
            return TimePrediction(confidence=0.0)

        model = self._models.get(pattern_key)
        if not model:
            return TimePrediction(confidence=0.0)

        is_weekend = context.is_weekend
        samples = model.get_samples(is_weekend)

        if samples < self._min_samples:
            if model.get_samples(not is_weekend) >= self._min_samples:
                is_weekend = not is_weekend
            else:
                total = model.weekday_samples + model.weekend_samples
                if total < self._min_samples:
                    return TimePrediction(confidence=max(0.1, total / (self._min_samples * 2)))

        ewma_hour = model.get_ewma_hour(is_weekend)
        ewma_std = model.get_ewma_std(is_weekend)

        predicted_minute = int((ewma_hour % 1) * 60)
        predicted_hour = int(ewma_hour)
        if predicted_hour >= 24:
            predicted_hour = 23
            predicted_minute = 59

        now = context.current_time
        predicted_time = now.replace(
            hour=predicted_hour,
            minute=predicted_minute,
            second=0,
            microsecond=0,
        )

        current_hour_float = context.hour_of_day + context.minute_of_hour / 60.0
        time_diff = abs(current_hour_float - ewma_hour)
        if time_diff > 12:
            time_diff = 24 - time_diff

        confidence = self._time_proximity_confidence(time_diff, ewma_std)
        confidence *= min(1.0, samples / 20.0)

        return TimePrediction(
            time=predicted_time,
            confidence=round(max(0.0, min(1.0, confidence)), 3),
        )

    def get_model(self, pattern_type: str) -> Optional[TimeModel]:
        return self._models.get(pattern_type)

    def get_all_models(self) -> Dict[str, TimeModel]:
        return dict(self._models)

    def set_model(self, pattern_type: str, model: TimeModel) -> None:
        self._models[pattern_type] = model

    def _update_ewma(self, model: TimeModel, hours: np.ndarray, is_weekend: bool) -> TimeModel:
        alpha = self._alpha
        sorted_hours = np.sort(hours)

        circular_hours = self._to_circular(sorted_hours)
        mean_sin = np.mean(np.sin(2 * np.pi * circular_hours / 24.0))
        mean_cos = np.mean(np.cos(2 * np.pi * circular_hours / 24.0))
        circular_mean = (np.arctan2(mean_sin, mean_cos) * 24.0 / (2 * np.pi)) % 24.0

        deviations = np.array([
            min(abs(h - circular_mean), 24 - abs(h - circular_mean))
            for h in sorted_hours
        ])
        circular_std = float(np.std(deviations))

        prev_hour = model.get_ewma_hour(is_weekend)
        prev_std = model.get_ewma_std(is_weekend)
        prev_samples = model.get_samples(is_weekend)

        if prev_samples == 0:
            new_hour = circular_mean
            new_std = circular_std
        else:
            hour_diff = circular_mean - prev_hour
            if hour_diff > 12:
                hour_diff -= 24
            elif hour_diff < -12:
                hour_diff += 24
            new_hour = (prev_hour + alpha * hour_diff) % 24.0
            new_std = prev_std + alpha * (circular_std - prev_std)

        new_samples = prev_samples + len(hours)

        if is_weekend:
            model.weekend_ewma_hour = new_hour
            model.weekend_ewma_std = max(0.1, new_std)
            model.weekend_samples = new_samples
        else:
            model.weekday_ewma_hour = new_hour
            model.weekday_ewma_std = max(0.1, new_std)
            model.weekday_samples = new_samples

        return model

    @staticmethod
    def _to_circular(hours: np.ndarray) -> np.ndarray:
        return hours % 24.0

    @staticmethod
    def _time_proximity_confidence(time_diff: float, std: float) -> float:
        if std <= 0:
            std = 0.5
        z_score = time_diff / std
        confidence = math.exp(-0.5 * z_score * z_score)
        return confidence
