# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

import asyncio
import logging
import time
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set

from miloco_server.dao.habit_dao import HabitDAO
from miloco_server.schema.habit_schema import (
    HabitCategory,
    HabitEvent,
    HabitEventType,
)

logger = logging.getLogger(__name__)


class HabitCollector:
    _instance: Optional["HabitCollector"] = None

    def __init__(self, habit_dao: HabitDAO, flush_interval: float = 5.0, context_provider=None):
        self._habit_dao = habit_dao
        self._context_provider = context_provider
        self._enabled = True
        self._buffer: List[HabitEvent] = []
        self._buffer_lock = asyncio.Lock()
        self._flush_interval = flush_interval
        self._flush_task: Optional[asyncio.Task] = None
        self._stats = {
            "total_collected": 0,
            "total_flushed": 0,
            "noise_filtered": 0,
            "errors": 0,
        }

        self._domain_category_map: Dict[str, HabitCategory] = {
            "light": HabitCategory.LIGHT_CONTROL,
            "switch": HabitCategory.SWITCH_CONTROL,
            "cover": HabitCategory.CURTAIN_CONTROL,
            "climate": HabitCategory.CLIMATE_CONTROL,
            "media_player": HabitCategory.MEDIA_CONTROL,
            "fan": HabitCategory.CLIMATE_CONTROL,
            "humidifier": HabitCategory.CLIMATE_CONTROL,
        }

        self._entity_category_map: Dict[str, HabitCategory] = {
            "binary_sensor.motion": HabitCategory.SECURITY_CHECK,
            "binary_sensor.door": HabitCategory.SECURITY_CHECK,
            "binary_sensor.window": HabitCategory.SECURITY_CHECK,
            "binary_sensor.presence": HabitCategory.SECURITY_CHECK,
            "alarm_control_panel": HabitCategory.SECURITY_CHECK,
            "lock": HabitCategory.SECURITY_CHECK,
            "camera": HabitCategory.SECURITY_CHECK,
        }

        self._noise_states = {"unavailable", "unknown", "none", ""}
        self._noise_entities: Set[str] = {
            "sensor.heartbeat",
            "sensor.storage_used",
            "sensor.last_boot",
            "sensor.sun_next_dawn",
            "sensor.sun_next_dusk",
        }

        self._previous_states: Dict[str, str] = {}

        HabitCollector._instance = self

    @classmethod
    def get_instance(cls) -> Optional["HabitCollector"]:
        return cls._instance

    async def start(self) -> None:
        self._flush_task = asyncio.create_task(self._flush_loop())
        logger.info("HabitCollector started")

    async def stop(self) -> None:
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        await self._flush_buffer()
        logger.info("HabitCollector stopped")

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        logger.info("HabitCollector %s", "enabled" if enabled else "disabled")

    async def on_state_changed(
        self, entity_id: str, old_state: Optional[dict], new_state: dict
    ) -> None:
        if not self._enabled:
            return

        try:
            new_val = new_state.get("state") if isinstance(new_state, dict) else str(new_state)
            old_val = (old_state.get("state") if isinstance(old_state, dict) else str(old_state)) if old_state else None

            if self._is_noise(entity_id, old_val, new_val):
                self._stats["noise_filtered"] += 1
                return

            category = self._categorize_entity(entity_id)
            if category is None:
                category = HabitCategory.DEVICE_USAGE
                logger.debug("Uncategorized entity %s, collected as DEVICE_USAGE", entity_id)

            now = datetime.now()
            attributes = new_state.get("attributes", {}) if isinstance(new_state, dict) else {}

            ctx = self._capture_context()

            event = HabitEvent(
                event_id=str(uuid.uuid4()),
                timestamp=now,
                event_type=HabitEventType.DEVICE_STATE_CHANGE,
                category=category,
                entity_id=entity_id,
                device_domain=entity_id.split(".")[0],
                old_state=old_val,
                new_state=new_val,
                attributes=attributes if isinstance(attributes, dict) else {},
                day_of_week=now.weekday(),
                hour_of_day=now.hour,
                minute_of_hour=now.minute,
                is_weekend=now.weekday() >= 5,
                temperature=ctx.get("temperature"),
                humidity=ctx.get("humidity"),
                light_level=ctx.get("light_level"),
                is_home=ctx.get("is_home"),
                is_anyone_present=ctx.get("is_anyone_present"),
                outdoor_temperature=ctx.get("outdoor_temperature"),
                weather=ctx.get("weather"),
                water_leak_detected=ctx.get("water_leak_detected"),
                traffic_restricted=ctx.get("traffic_restricted"),
                source="ha_websocket",
                metadata=ctx,
            )

            self._previous_states[entity_id] = new_val

            async with self._buffer_lock:
                self._buffer.append(event)
                self._stats["total_collected"] += 1

            logger.debug("Collected event: %s %s -> %s [%s] temp=%.1f humidity=%.1f present=%s",
                         entity_id, old_val, new_val, category.value,
                         ctx.get("temperature", 0) if ctx.get("temperature") else 0,
                         ctx.get("humidity", 0) if ctx.get("humidity") else 0,
                         ctx.get("is_anyone_present"))

        except Exception as e:
            self._stats["errors"] += 1
            logger.error("HabitCollector.on_state_changed error: %s", e)

    def _capture_context(self) -> Dict[str, Any]:
        if self._context_provider:
            try:
                env_ctx = self._context_provider.get_context()
                return env_ctx.to_dict()
            except Exception as e:
                logger.debug("ContextProvider snapshot failed: %s", e)
        return {}

    async def on_user_command(self, command: str, context: Optional[Dict[str, Any]] = None) -> None:
        if not self._enabled:
            return

        try:
            now = datetime.now()
            event = HabitEvent(
                event_id=str(uuid.uuid4()),
                timestamp=now,
                event_type=HabitEventType.USER_COMMAND,
                category=HabitCategory.DEVICE_USAGE,
                attributes={"command": command, **(context or {})},
                day_of_week=now.weekday(),
                hour_of_day=now.hour,
                minute_of_hour=now.minute,
                is_weekend=now.weekday() >= 5,
                source="user_interaction",
            )

            async with self._buffer_lock:
                self._buffer.append(event)
                self._stats["total_collected"] += 1

        except Exception as e:
            self._stats["errors"] += 1
            logger.error("HabitCollector.on_user_command error: %s", e)

    async def on_automation_trigger(
        self, rule_id: str, rule_name: str, actions: Optional[List[Dict]] = None
    ) -> None:
        if not self._enabled:
            return

        try:
            now = datetime.now()
            event = HabitEvent(
                event_id=str(uuid.uuid4()),
                timestamp=now,
                event_type=HabitEventType.AUTOMATION_TRIGGER,
                category=HabitCategory.DEVICE_USAGE,
                attributes={
                    "rule_id": rule_id,
                    "rule_name": rule_name,
                    "actions": actions or [],
                },
                day_of_week=now.weekday(),
                hour_of_day=now.hour,
                minute_of_hour=now.minute,
                is_weekend=now.weekday() >= 5,
                source="automation",
            )

            async with self._buffer_lock:
                self._buffer.append(event)
                self._stats["total_collected"] += 1

        except Exception as e:
            self._stats["errors"] += 1
            logger.error("HabitCollector.on_automation_trigger error: %s", e)

    def _is_noise(self, entity_id: str, old_state: Optional[str], new_state: Optional[str]) -> bool:
        if entity_id in self._noise_entities:
            return True

        if new_state in self._noise_states:
            return True

        if old_state == new_state:
            return True

        return False

    def _categorize_entity(self, entity_id: str) -> Optional[HabitCategory]:
        if entity_id in self._entity_category_map:
            return self._entity_category_map[entity_id]

        for prefix, category in self._entity_category_map.items():
            if entity_id.startswith(prefix + "."):
                return category

        domain = entity_id.split(".")[0]
        return self._domain_category_map.get(domain)

    def get_watchable_entities(self) -> List[str]:
        return list(self._entity_category_map.keys()) + list(self._domain_category_map.keys())

    async def _flush_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self._flush_interval)
                await self._flush_buffer()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("HabitCollector flush loop error: %s", e)

    async def _flush_buffer(self) -> None:
        async with self._buffer_lock:
            if not self._buffer:
                return
            events_to_flush = list(self._buffer)
            self._buffer.clear()

        try:
            count = self._habit_dao.insert_events_batch(events_to_flush)
            self._stats["total_flushed"] += count
            if count > 0:
                logger.debug("Flushed %d habit events", count)
        except Exception as e:
            self._stats["errors"] += 1
            logger.error("HabitCollector flush error: %s", e)

    def get_stats(self) -> Dict[str, Any]:
        return {
            **self._stats,
            "buffer_size": len(self._buffer),
            "enabled": self._enabled,
        }
