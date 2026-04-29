# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from miloco_server.dao.habit_dao import HabitDAO
from miloco_server.service.behavior_learner import BehaviorLearner

logger = logging.getLogger(__name__)


class ModelTrainer:
    def __init__(self, behavior_learner: BehaviorLearner, habit_dao: HabitDAO):
        self.behavior_learner = behavior_learner
        self.habit_dao = habit_dao
        self._training_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False
        self._learn_interval: int = 3600
        self._events_retention_days: int = 90
        self._patterns_retention_days: int = 180
        self._cleanup_interval: int = 86400
        self._stats = {
            "train_cycles": 0,
            "last_train_time": 0.0,
            "last_train_duration": 0.0,
            "last_patterns_count": 0,
            "events_deleted": 0,
            "patterns_deleted": 0,
            "errors": 0,
        }

    async def start(self, learn_interval: int = 3600, events_retention_days: int = 90,
                    patterns_retention_days: int = 180, cleanup_interval: int = 86400) -> None:
        self._learn_interval = learn_interval
        self._events_retention_days = events_retention_days
        self._patterns_retention_days = patterns_retention_days
        self._cleanup_interval = cleanup_interval
        if self._running:
            return
        self._running = True
        self._training_task = asyncio.create_task(self._training_loop())
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("ModelTrainer started (interval=%ds, events_retention=%dd, patterns_retention=%dd)",
                    self._learn_interval, self._events_retention_days, self._patterns_retention_days)

    async def stop(self) -> None:
        self._running = False
        if self._training_task:
            self._training_task.cancel()
            try:
                await self._training_task
            except asyncio.CancelledError:
                pass
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        logger.info("ModelTrainer stopped")

    async def train_all(self) -> Dict[str, Any]:
        start_time = time.time()

        try:
            pattern_count = await self.behavior_learner.learn(days=30)

            duration = time.time() - start_time
            self._stats["train_cycles"] += 1
            self._stats["last_train_time"] = time.time()
            self._stats["last_train_duration"] = round(duration, 2)
            self._stats["last_patterns_count"] = pattern_count

            logger.info(
                "Training completed: %d patterns in %.2fs (cycle #%d)",
                pattern_count, duration, self._stats["train_cycles"],
            )

            return {
                "pattern_count": pattern_count,
                "duration": round(duration, 2),
                "cycle": self._stats["train_cycles"],
            }

        except Exception as e:
            self._stats["errors"] += 1
            logger.error("Training failed: %s", e)
            return {"error": str(e)}

    async def evaluate(self, days: int = 7) -> Dict[str, Any]:
        from miloco_server.utils.metrics import accuracy_score, time_mae_minutes

        end = datetime.now()
        start = end - timedelta(days=days)

        events = self.habit_dao.get_events_by_timerange(start, end, limit=1000)
        if not events:
            return {"error": "No events found for evaluation", "samples": 0}

        predictions = []
        actuals = []

        for event in events:
            from miloco_server.schema.habit_schema import PredictionContext
            context = PredictionContext(
                current_time=event.timestamp,
                day_of_week=event.day_of_week,
                hour_of_day=event.hour_of_day,
                minute_of_hour=event.minute_of_hour,
                is_weekend=event.is_weekend,
            )

            results = await self.behavior_learner.predict(context)
            if results:
                best = results[0]
                predictions.append(best.predicted_action)
                actuals.append(f"{event.entity_id}:{event.new_state}")

        if not predictions:
            return {"error": "No predictions generated", "samples": len(events)}

        acc = accuracy_score(predictions, actuals)

        return {
            "samples": len(events),
            "accuracy": round(acc, 4),
            "predictions_count": len(predictions),
        }

    def get_stats(self) -> Dict[str, Any]:
        return {
            **{k: v for k, v in self._stats.items() if k not in ["events_deleted", "patterns_deleted"]},
            "running": self._running,
            "events_retention_days": self._events_retention_days,
            "patterns_retention_days": self._patterns_retention_days,
            "total_events_deleted": self._stats.get("events_deleted", 0),
            "total_patterns_deleted": self._stats.get("patterns_deleted", 0),
        }

    async def _training_loop(self) -> None:
        await asyncio.sleep(60)

        while self._running:
            try:
                await self.train_all()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Training loop error: %s", e)
                self._stats["errors"] += 1

            await asyncio.sleep(self._learn_interval)

    async def _cleanup_loop(self) -> None:
        await asyncio.sleep(300)

        while self._running:
            try:
                await self._cleanup_expired_data()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Cleanup loop error: %s", e)

            await asyncio.sleep(self._cleanup_interval)

    async def _cleanup_expired_data(self) -> None:
        try:
            events_cutoff = datetime.now() - timedelta(days=self._events_retention_days)
            deleted_events = self.habit_dao.delete_expired_events(events_cutoff)
            self._stats["events_deleted"] += deleted_events
            logger.info("Cleanup: deleted %d expired habit events (before %s)", deleted_events, events_cutoff)
        except Exception as e:
            logger.error("Failed to cleanup expired events: %s", e)

        try:
            patterns_cutoff = datetime.now() - timedelta(days=self._patterns_retention_days)
            deleted_patterns = self.habit_dao.delete_expired_patterns(patterns_cutoff)
            self._stats["patterns_deleted"] += deleted_patterns
            logger.info("Cleanup: deleted %d expired patterns (before %s)", deleted_patterns, patterns_cutoff)
        except Exception as e:
            logger.error("Failed to cleanup expired patterns: %s", e)
