# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

import asyncio
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from miloco_server.proxy.ha_proxy import HAProxy
from miloco_server.schema.habit_schema import (
    DecisionAction,
    DecisionContext,
    PredictionContext,
    PredictionResult,
)
from miloco_server.service.behavior_learner import BehaviorLearner
from miloco_server.service.risk_assessor import RiskAssessor, RiskLevel

logger = logging.getLogger(__name__)


class DecisionEngine:
    _instance: Optional["DecisionEngine"] = None

    CONTROLLABLE_DOMAINS = {
        "light", "switch", "climate", "cover", "fan",
        "lock", "media_player", "vacuum", "humidifier",
        "dehumidifier", "air_purifier", "curtain", "scene",
        "input_boolean", "input_number",
    }

    def __init__(
        self,
        behavior_learner: BehaviorLearner,
        risk_assessor: RiskAssessor,
        ha_proxy: HAProxy,
        cycle_interval: int = 60,
        confidence_threshold: float = 0.65,
        risk_level_limit: str = "HIGH",
        bridge_manager=None,
        wakeup_scheduler=None,
        context_provider=None,
    ):
        self.behavior_learner = behavior_learner
        self.risk_assessor = risk_assessor
        self.ha_proxy = ha_proxy
        self.bridge_manager = bridge_manager
        self.wakeup_scheduler = wakeup_scheduler
        self._context_provider = context_provider

        self._cycle_interval = cycle_interval
        self._confidence_threshold = confidence_threshold
        self._risk_level_limit = self.risk_assessor.get_risk_limit_from_config(risk_level_limit)

        self._running = False
        self._cycle_task: Optional[asyncio.Task] = None
        self._executed_actions: Dict[str, float] = {}
        self._stats = {
            "cycles": 0,
            "predictions_made": 0,
            "actions_executed": 0,
            "actions_blocked": 0,
            "actions_context_blocked": 0,
            "inquiries_sent": 0,
            "errors": 0,
        }

        DecisionEngine._instance = self

    @classmethod
    def get_instance(cls) -> Optional["DecisionEngine"]:
        return cls._instance

    async def start(self) -> None:
        if self._running:
            logger.warning("DecisionEngine already running")
            return
        self._running = True
        self._cycle_task = asyncio.create_task(self._run_loop())
        logger.info(
            "DecisionEngine started (interval=%ds, threshold=%.2f, risk_limit=%s)",
            self._cycle_interval,
            self._confidence_threshold,
            self._risk_level_limit.name,
        )

    async def stop(self) -> None:
        self._running = False
        if self._cycle_task:
            self._cycle_task.cancel()
            try:
                await self._cycle_task
            except asyncio.CancelledError:
                pass
        logger.info("DecisionEngine stopped")

    async def run_cycle(self) -> List[Dict[str, Any]]:
        self._stats["cycles"] += 1
        results: List[Dict[str, Any]] = []

        try:
            context = await self._build_context()
            predictions = await self.behavior_learner.predict()

            high_conf = [
                p for p in predictions
                if p.confidence >= self._confidence_threshold
            ]

            high_conf = [
                p for p in high_conf
                if (p.entity_id or "").split(".")[0] in self.CONTROLLABLE_DOMAINS
            ]

            self._stats["predictions_made"] += len(high_conf)

            if not high_conf:
                return results

            logger.info("DecisionEngine: %d high-confidence predictions", len(high_conf))

            for prediction in high_conf:
                action = self._prediction_to_action(prediction)
                if self._is_duplicate(action):
                    continue

                ctx_skip, ctx_reason = self._context_pre_check(action, context)
                if ctx_skip:
                    logger.info("Context skip: %s - %s", action.entity_id, ctx_reason)
                    self._stats["actions_context_blocked"] += 1
                    results.append({
                        "action": action.to_dict(),
                        "result": "blocked_context",
                        "reason": ctx_reason,
                    })
                    continue

                decision_context = DecisionContext(
                    current_time=datetime.now(),
                    device_states=context.environment or {},
                    environment=context.environment or {},
                    day_of_week=context.day_of_week,
                    is_weekend=context.is_weekend,
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
                )

                risk = await self.risk_assessor.assess(action, decision_context)

                if risk.level > self._risk_level_limit:
                    logger.info("Action %s exceeds risk limit (%s > %s), skipping",
                                action.entity_id, risk.level.name, self._risk_level_limit.name)
                    self._stats["actions_blocked"] += 1
                    results.append({"action": action.to_dict(), "result": "blocked_risk_limit", "risk": risk.to_dict()})
                    continue

                if risk.level == RiskLevel.CRITICAL:
                    logger.warning("Critical risk action blocked: %s", action.entity_id)
                    self._stats["actions_blocked"] += 1
                    results.append({"action": action.to_dict(), "result": "blocked_critical", "risk": risk.to_dict()})
                    continue

                if risk.requires_inquiry:
                    success = await self._execute_with_inquiry(action, risk)
                    result_label = "inquiry_sent" if success else "inquiry_failed"
                    self._stats["inquiries_sent"] += 1
                elif risk.requires_broadcast:
                    success = await self._execute_silent(action, broadcast=True)
                    result_label = "executed_broadcast" if success else "executed_failed"
                else:
                    success = await self._execute_silent(action, broadcast=False)
                    result_label = "executed_silent" if success else "executed_failed"

                if success:
                    self._mark_executed(action)
                    self._stats["actions_executed"] += 1

                results.append({"action": action.to_dict(), "result": result_label, "risk": risk.to_dict()})

        except Exception as e:
            self._stats["errors"] += 1
            logger.error("DecisionEngine cycle error: %s", e)

        return results

    def get_stats(self) -> Dict[str, Any]:
        return {**self._stats, "running": self._running}

    async def _run_loop(self) -> None:
        while self._running:
            try:
                await self.run_cycle()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("DecisionEngine loop error: %s", e)
            await asyncio.sleep(self._cycle_interval)

    async def _build_context(self) -> PredictionContext:
        now = datetime.now()

        ctx = PredictionContext(
            current_time=now,
            day_of_week=now.weekday(),
            hour_of_day=now.hour,
            minute_of_hour=now.minute,
            is_weekend=now.weekday() >= 5,
            environment={},
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
                ctx.environment = env_ctx.to_dict()
            except Exception as e:
                logger.debug("ContextProvider snapshot failed: %s", e)

        return ctx

    def _context_pre_check(self, action: DecisionAction, context: PredictionContext) -> tuple:
        if not context.is_home and action.domain in ("light", "switch"):
            if action.service == "turn_on":
                return True, "no_one_home_light"

        if context.weather in ("rainy", "thunderstorm", "heavy_rain"):
            if action.domain == "cover" and action.service in ("open_cover", "open"):
                return True, "raining_no_open_window"

        if context.weather in ("snowy", "heavy_snow", "blizzard"):
            if action.domain == "cover" and action.service in ("open_cover", "open"):
                return True, "snowing_no_open_window"

        if action.domain == "climate":
            if context.temperature is not None:
                if action.service == "turn_on":
                    if 22 <= context.temperature <= 26:
                        return True, "temp_comfortable_no_need_ac"

        if not context.is_anyone_present:
            if action.domain in ("media_player",):
                return True, "no_one_present_media"

        if context.air_quality is not None and context.air_quality > 150:
            if action.domain == "cover" and action.service in ("open_cover", "open"):
                return True, "poor_air_quality_no_open"

        if context.is_home and action.domain == "lock":
            if action.service in ("lock", "turn_off"):
                if context.is_anyone_present:
                    return True, "people_home_no_lock"

        return False, ""

    def _prediction_to_action(self, prediction: PredictionResult) -> DecisionAction:
        entity_id = prediction.entity_id or ""
        domain = entity_id.split(".")[0] if entity_id else ""
        service = prediction.service or "turn_on"

        return DecisionAction(
            entity_id=entity_id,
            domain=domain,
            service=service,
            new_state=prediction.predicted_state,
            prediction_confidence=prediction.confidence,
            reasoning=prediction.reasoning,
        )

    def _is_duplicate(self, action: DecisionAction) -> bool:
        key = f"{action.entity_id}:{action.service}:{datetime.now().hour}"
        last_exec = self._executed_actions.get(key)
        if last_exec and (time.time() - last_exec) < 3600:
            return True
        return False

    def _mark_executed(self, action: DecisionAction) -> None:
        key = f"{action.entity_id}:{action.service}:{datetime.now().hour}"
        self._executed_actions[key] = time.time()

        cutoff = time.time() - 7200
        expired = [k for k, v in self._executed_actions.items() if v < cutoff]
        for k in expired:
            del self._executed_actions[k]

    async def _execute_silent(self, action: DecisionAction, broadcast: bool = False) -> bool:
        try:
            await self.ha_proxy.call_service(
                domain=action.domain,
                service=action.service,
                entity_id=action.entity_id,
            )
            logger.info("Silent execution: %s %s %s", action.entity_id, action.service, action.new_state or "")

            if broadcast and self.wakeup_scheduler:
                text = self._generate_broadcast_text(action)
                await self.wakeup_scheduler.broadcast_message(text)

            return True
        except Exception as e:
            logger.error("Silent execution failed for %s: %s", action.entity_id, e)
            self._stats["errors"] += 1
            return False

    async def _execute_with_inquiry(self, action: DecisionAction, risk) -> bool:
        if not self.wakeup_scheduler:
            logger.warning("Cannot send inquiry: wakeup_scheduler not available")
            return await self._execute_silent(action, broadcast=False)

        try:
            text = self._generate_inquiry_text(action)
            await self.wakeup_scheduler.broadcast_message(text)
            logger.info("Inquiry sent for %s: %s", action.entity_id, text)
            return True
        except Exception as e:
            logger.error("Inquiry failed for %s: %s", action.entity_id, e)
            return False

    @staticmethod
    def _generate_broadcast_text(action: DecisionAction) -> str:
        domain = action.domain
        entity_name = action.entity_id.split(".")[-1].replace("_", " ")

        if domain == "light":
            if action.service == "turn_on":
                return f"已为您打开{entity_name}"
            return f"已为您关闭{entity_name}"
        if domain == "cover":
            if "open" in action.service:
                return f"已为您打开{entity_name}"
            return f"已为您关闭{entity_name}"
        if domain == "climate":
            return f"已为您开启{entity_name}"

        return f"已为您操作{entity_name}"

    @staticmethod
    def _generate_inquiry_text(action: DecisionAction) -> str:
        entity_name = action.entity_id.split(".")[-1].replace("_", " ")
        domain = action.domain

        if domain == "lock":
            return f"检测到您习惯在这个时间锁门，是否需要帮您操作{entity_name}？"
        if domain == "camera":
            return f"是否需要帮您调整{entity_name}？"

        return f"是否需要帮您操作{entity_name}？"
