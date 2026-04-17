# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Trigger business logic service
Handles trigger-related business logic and data validation
"""

import json
import time
from typing import Callable, List, Dict, Optional, Any, Set
import asyncio
import logging
import uuid

from miloco_server.schema.mcp_schema import CallToolResult
from thespian.actors import ActorExitRequest

from miloco_server import actor_system
from miloco_server.config.normal_config import TRIGGER_RULE_RUNNER_CONFIG
from miloco_server.config.prompt_config import UserLanguage
from miloco_server.dao.trigger_rule_log_dao import TriggerRuleLogDAO
from miloco_server.mcp.tool_executor import ToolExecutor
from miloco_server.proxy.llm_proxy import LLMProxy
from miloco_server.proxy.miot_proxy import MiotProxy
from miloco_server.proxy.ha_proxy import HAProxy
from miloco_server.proxy.ha_listener import HaStateListener
from miloco_server.service.trigger_buffer import TriggerBuffer
from miloco_server.schema.miot_schema import CameraImgPathSeq, CameraImgSeq, CameraInfo
from miloco_server.schema.trigger_log_schema import (
    AiRecommendDynamicExecuteResult, TriggerConditionResult, ActionExecuteResult,
    TriggerRuleLog, NotifyResult, ExecuteResult
)
from miloco_server.schema.trigger_schema import (
    Action, TriggerRule, ExecuteType, ConditionType, XiaoAIBroadcastMode
)
from miloco_server.service.xiaoai_broadcast_service import broadcast_via_bridge
from miloco_server.service.wakeup_scheduler import WakeUpScheduler
from miloco_server.utils.check_img_motion import check_camera_motion
from miloco_server.utils.direct_condition_checker import direct_condition_checker
from miloco_server.utils.local_models import ModelPurpose
from miloco_server.utils.normal_util import extract_json_from_content
from miloco_server.utils.prompt_helper import TriggerRuleConditionPromptBuilder
from miloco_server.utils.trigger_filter import trigger_filter
from miloco_server.detection.trigger_integration import get_detection_trigger_integration
from miloco_server.service import trigger_rule_dynamic_executor_cache
from miloco_server.service.trigger_rule_dynamic_executor import START, TriggerRuleDynamicExecutor
from miloco_server.schema.wakeup_schema import WakeUpMode
from miloco_server.xiaomi_bridge.manager import get_bridge_manager

logger = logging.getLogger(name=__name__)


class TriggerRuleRunner:
    """Trigger service class"""

    def __init__(self, trigger_rules: List[TriggerRule], miot_proxy: MiotProxy,
                 ha_proxy: HAProxy,
                 get_llm_proxy_by_purpose: Callable[[ModelPurpose], LLMProxy],
                 get_language: Callable[[], UserLanguage],
                 tool_executor: ToolExecutor,
                 trigger_rule_log_dao: TriggerRuleLogDAO):

        self.trigger_rules: Dict[str, TriggerRule] = {
            rule.id: rule
            for rule in trigger_rules if rule.id is not None
        }
        self._get_llm_proxy_by_purpose = get_llm_proxy_by_purpose
        self.miot_proxy = miot_proxy
        self.ha_proxy = ha_proxy
        self._get_language = get_language
        self.trigger_rule_log_dao = trigger_rule_log_dao
        self._tool_executor = tool_executor
        self._task = None
        self._is_running: bool = False
        self._interval_seconds = TRIGGER_RULE_RUNNER_CONFIG["interval_seconds"]
        self._vision_use_img_count = TRIGGER_RULE_RUNNER_CONFIG["vision_use_img_count"]

        # Initialize HA Listener
        ha_config = self.ha_proxy.get_ha_config()
        self._ha_listener = HaStateListener(
            ha_config,
            self._on_ha_state_changed,
            on_connected=self._refresh_ha_device_map
        ) if ha_config else None

        # Initialize Trigger Buffer
        self._trigger_buffer = TriggerBuffer(self._execute_buffered_rules)

        # Initialize Detection Trigger Integration
        self._detection_trigger_integration = None

        # Cache for HA Device -> Entities mapping
        self._ha_device_map: Dict[str, List[str]] = {}

        # Cache for last AI conclusion per rule (for deduplication)
        self._last_rule_conclusions: Dict[str, bool] = {}

        # Active hybrid mode rules: rules where HA condition is met, need periodic camera check
        # Dict[rule_id, Dict[str, Any]] with keys: rule, last_ha_check_time, ha_condition_met
        self._active_hybrid_rules: Dict[str, Dict[str, Any]] = {}

        # Rules currently being checked (prevent concurrent LLM calls for same rule)
        self._rules_being_checked: Set[str] = set()

        # Update listener subscription list
        self._update_listener_watched_entities()

        logger.info(
            "TriggerRuleRunner init success, trigger_rules: %s", self.trigger_rules
        )

    def _update_listener_watched_entities(self):
        """Extract all entity IDs from all rules and update the HA listener."""
        if not self._ha_listener:
            return

        all_watched = set()
        for rule in self.trigger_rules.values():
            if rule.ha_devices:
                for dev_id in rule.ha_devices:
                    all_watched.update(self._ha_device_map.get(dev_id, []))

        if all_watched:
            logger.info("Updating watched entities (%d)", len(all_watched))
            self._ha_listener.update_watched_entities(list(all_watched))

    async def _refresh_ha_device_map(self):
        """Fetch HA device grouping and update cache."""
        try:
            if not self.ha_proxy:
                return

            template = """
            {
              {% set ns = namespace(devices=[]) %}
              {% for state in states %}
                {% set dev_id = device_id(state.entity_id) %}
                {% if dev_id %}
                  {% set ns.devices = ns.devices + [dev_id] %}
                {% endif %}
              {% endfor %}
              {% set unique_devices = ns.devices | unique | list %}

              {% for dev_id in unique_devices %}
                "{{ dev_id }}": {{ device_entities(dev_id) | list | to_json }}{% if not loop.last %},{% endif %}
              {% endfor %}
            }
            """
            if self.ha_proxy.ha_client:
                res = await self.ha_proxy.ha_client.render_template_async(template)
                self._ha_device_map = json.loads(res)
                logger.info("Refreshed HA device map, found %d devices", len(self._ha_device_map))

                # Update watched entities with all entities belonging to rules' ha_devices
                if self._ha_listener:
                    all_entities = set()
                    for rule in self.trigger_rules.values():
                        if rule.ha_devices:
                            for dev_id in rule.ha_devices:
                                all_entities.update(self._ha_device_map.get(dev_id, []))

                    watched_list = list(all_entities)
                    logger.info("Updating watched entities (%d): %s", len(watched_list), watched_list)
                    self._ha_listener.update_watched_entities(watched_list)
        except Exception as e:  # pylint: disable=broad-except
            logger.error("Failed to refresh HA device map: %s", e)

    def _get_vision_understaning_llm_proxy(self) -> LLMProxy:
        return self._get_llm_proxy_by_purpose(
            ModelPurpose.VISION_UNDERSTANDING)

    def _get_planning_llm_proxy(self) -> LLMProxy:
        return self._get_llm_proxy_by_purpose(
            ModelPurpose.PLANNING)

    def add_trigger_rule(self, trigger_rule: TriggerRule):
        """Add trigger rule"""
        self.trigger_rules[trigger_rule.id] = trigger_rule
        self._update_listener_watched_entities()

        # Add to detection trigger integration if applicable
        if self._detection_trigger_integration:
            if trigger_rule.detection_condition and trigger_rule.detection_condition.enabled:
                self._detection_trigger_integration.add_rule(trigger_rule)

    def remove_trigger_rule(self, rule_id: str):
        """Remove trigger rule"""
        if rule_id in self.trigger_rules:
            del self.trigger_rules[rule_id]
            self._update_listener_watched_entities()

        # Remove from detection trigger integration
        if self._detection_trigger_integration:
            self._detection_trigger_integration.remove_rule(rule_id)

    async def _periodic_task(self):
        """Scheduled task execution method, runs at configured interval"""
        while self._is_running:
            try:
                # Execute scheduled task logic
                asyncio.create_task(self._execute_scheduled_task())

                # Wait for configured interval
                await asyncio.sleep(self._interval_seconds)
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.error(
                    "Error occurred while executing scheduled task: %s", e)
                await asyncio.sleep(self._interval_seconds)

    def _on_ha_state_changed(self, entity_id: str, old_state: Dict[str, Any], new_state: Dict[str, Any]):
        """Callback for HA state changes."""
        domain = entity_id.split(".")[0]
        val_old = old_state.get("state") if old_state else None
        val_new = new_state.get("state") if new_state else None

        # 1. State Deduplication: Ignore if state value hasn't changed.
        # But allow events/buttons/scenes to always pass through as they are momentary.
        if val_old == val_new and domain not in ["event", "button", "input_button", "scene"]:
            return

        logger.info("HA State Changed for %s: %s -> %s", entity_id, val_old, val_new)

        # Performance/Noise Filter: Ignore very frequent or irrelevant entities
        noise_keywords = {"heartbeat", "storage_used", "recording_duration"}
        if any(k in entity_id for k in noise_keywords):
            logger.debug("Ignoring noise entity: %s", entity_id)
            return

        # Find rules that care about this entity
        dirty_rules = set()

        parent_device_ids = []
        for dev_id, entities in self._ha_device_map.items():
            if entity_id in entities:
                parent_device_ids.append(dev_id)

        for rule_id, rule in self.trigger_rules.items():
            if rule.ha_devices:
                # Skip detection mode rules - they are handled by detection trigger integration
                is_detection_mode = (
                    hasattr(rule, 'condition_type') and
                    rule.condition_type in (ConditionType.DETECTION, ConditionType.FACE_RECOGNITION)
                )
                if is_detection_mode:
                    continue

                # If rule cares about any of the parent devices of this entity
                if any(dev_id in rule.ha_devices for dev_id in parent_device_ids):
                    # Direct mode with selected entity: use edge-trigger logic to avoid stale dedupe state.
                    is_direct_mode = (
                        not rule.cameras and
                        rule.ha_devices and
                        hasattr(rule, 'condition_type') and
                        rule.condition_type == ConditionType.DIRECT
                    )
                    if is_direct_mode and getattr(rule, "trigger_entity_id", None):
                        edge_should_trigger = self._evaluate_direct_entity_edge(
                            rule_id=rule_id,
                            rule=rule,
                            changed_entity_id=entity_id,
                            old_state=old_state,
                            new_state=new_state,
                        )
                        if edge_should_trigger and trigger_filter.pre_filter(rule):
                            dirty_rules.add(rule_id)
                        continue

                    if trigger_filter.pre_filter(rule):
                        dirty_rules.add(rule_id)

        if dirty_rules:
            logger.info("Marking rules as dirty due to %s change: %s", entity_id, dirty_rules)
            asyncio.create_task(self._trigger_buffer.mark_dirty(dirty_rules, entity_id))

        # Check active hybrid mode rules: if HA condition no longer met, remove from active set
        self._check_active_hybrid_rules_ha_condition(parent_device_ids)

    def _evaluate_direct_entity_edge(
        self,
        rule_id: str,
        rule: TriggerRule,
        changed_entity_id: str,
        old_state: Optional[Dict[str, Any]],
        new_state: Optional[Dict[str, Any]],
    ) -> bool:
        """Evaluate false->true edge for direct mode with a specific entity."""
        if rule.trigger_entity_id != changed_entity_id:
            return False

        # Use ha_condition for direct mode, fallback to condition for backward compatibility
        ha_check_condition = rule.ha_condition if rule.ha_condition else rule.condition

        old_matches = False
        if old_state:
            old_matches = direct_condition_checker.evaluate(
                ha_check_condition or "",
                {changed_entity_id: old_state},
                rule.trigger_entity_id,
            )

        new_matches = False
        if new_state:
            new_matches = direct_condition_checker.evaluate(
                ha_check_condition or "",
                {changed_entity_id: new_state},
                rule.trigger_entity_id,
            )

        # Reset dedupe baseline when condition becomes false.
        if not new_matches:
            self._last_rule_conclusions[rule_id] = False

        # Only trigger on rising edge.
        if new_matches and not old_matches:
            self._last_rule_conclusions[rule_id] = False
            logger.info("Direct edge trigger accepted for rule %s: false -> true", rule.name)
            return True
        return False

    def _check_active_hybrid_rules_ha_condition(self, changed_device_ids: List[str]):
        """Check if active hybrid rules' HA condition is still met after device state change."""
        rules_to_deactivate = []

        for rule_id, active_info in list(self._active_hybrid_rules.items()):
            rule = active_info.get('rule')
            if not rule or not rule.ha_devices:
                continue

            # Check if this rule cares about any of the changed devices
            if not any(dev_id in rule.ha_devices for dev_id in changed_device_ids):
                continue

            # Check if HA condition is still met
            if not self._ha_listener:
                continue

            all_states = self._ha_listener.get_all_states()
            rule_device_states = {}

            for dev_id in rule.ha_devices:
                entities = self._ha_device_map.get(dev_id, [])
                for entity in entities:
                    if entity in all_states:
                        rule_device_states[entity] = all_states[entity]

            if not rule_device_states:
                continue

            # Re-check HA condition
            ha_check_condition = rule.ha_condition if rule.ha_condition else rule.condition
            ha_condition_matched = direct_condition_checker.evaluate(
                ha_check_condition, rule_device_states, rule.trigger_entity_id
            )

            if not ha_condition_matched:
                rules_to_deactivate.append(rule_id)
                logger.info(
                    "HA condition no longer met for rule %s, removing from active hybrid rules",
                    rule.name
                )

        for rule_id in rules_to_deactivate:
            del self._active_hybrid_rules[rule_id]

    async def _execute_buffered_rules(self, rule_work_load: Dict[str, Set[str]]):
        """Execute rules triggered by the buffer."""
        logger.info("Executing buffered rules: %s", list(rule_work_load.keys()))
        await self._check_rules_batch(rule_work_load)

    async def _check_rules_batch(self, rule_work_load: Any):
        """Check a specific batch of rules."""
        vision_proxy = self._get_vision_understaning_llm_proxy()
        planning_proxy = self._get_planning_llm_proxy()

        start_time = int(time.time() * 1000)

        # Normalize work load to Dict[rid, sources]
        if isinstance(rule_work_load, list):
            target_rules_with_sources = {rid: set() for rid in rule_work_load}
        else:
            target_rules_with_sources = rule_work_load

        # Filter enabled rules and split by type
        # Direct mode rules don't need LLM, process them separately
        direct_mode_rules = []  # Rules using DIRECT condition type (no LLM needed)
        vision_rules = []       # Rules with cameras (need Vision LLM)
        text_rules = []         # Text-only rules using LLM mode (need Planning/Vision LLM)

        for rid, sources in target_rules_with_sources.items():
            rule = self.trigger_rules.get(rid)
            if rule and trigger_filter.pre_filter(rule):
                # Check if this is a detection mode rule (handled by detection trigger integration)
                is_detection_mode = (
                    hasattr(rule, 'condition_type') and
                    rule.condition_type in (ConditionType.DETECTION, ConditionType.FACE_RECOGNITION)
                )

                # Skip detection mode rules - they are handled by detection trigger integration
                if is_detection_mode:
                    logger.debug("Skipping detection mode rule %s in batch processing", rule.name)
                    continue

                # Check if this is a direct mode rule (no cameras, has HA devices, condition_type=DIRECT)
                is_direct_mode = (
                    not rule.cameras and
                    rule.ha_devices and
                    hasattr(rule, 'condition_type') and
                    rule.condition_type == ConditionType.DIRECT
                )

                if is_direct_mode:
                    direct_mode_rules.append((rid, rule, sources))
                elif rule.cameras:
                    vision_rules.append((rid, rule, sources))
                else:
                    text_rules.append((rid, rule, sources))

        # Execute direct mode rules (zero token cost, no LLM needed)
        if direct_mode_rules:
            logger.info("Executing %d direct mode rules (no LLM required)", len(direct_mode_rules))
            await self._execute_rules_logic(direct_mode_rules, None, start_time)

        # Check if we have any LLM-based rules but no LLM proxy
        if not vision_proxy and not planning_proxy:
            if vision_rules or text_rules:
                logger.warning("No LLM proxy available, skipping %d vision rules and %d text rules",
                             len(vision_rules), len(text_rules))
            return

        # Execute vision rules with Vision Model
        if vision_rules and vision_proxy:
            await self._execute_rules_logic(vision_rules, vision_proxy, start_time)
        elif vision_rules:
            logger.warning("Vision rules skipped because Vision Model is not available")

        # Execute text-only rules with Planning Model (fallback to Vision)
        if text_rules:
            proxy = planning_proxy if planning_proxy else vision_proxy
            if proxy:
                await self._execute_rules_logic(text_rules, proxy, start_time)
            else:
                logger.warning("Text rules skipped because no LLM is available")

    async def _execute_rules_logic(
            self, target_rules: List[tuple[str, TriggerRule, Set[str]]],
            llm_proxy: LLMProxy, start_time: int):
        """Core execution logic shared by periodic and event-driven triggers."""

        # Filter out rules that are already being checked (prevent concurrent calls)
        filtered_rules = []
        skipped_rules = []
        for rule_id, rule, trigger_sources in target_rules:
            if rule_id in self._rules_being_checked:
                skipped_rules.append(rule_id)
                continue
            filtered_rules.append((rule_id, rule, trigger_sources))

        if skipped_rules:
            logger.info("Skipping rules already being checked: %s", skipped_rules)

        if not filtered_rules:
            return

        # Mark rules as being checked
        for rule_id, _, _ in filtered_rules:
            self._rules_being_checked.add(rule_id)

        try:
            await self._execute_rules_logic_internal(filtered_rules, llm_proxy, start_time)
        finally:
            # Always remove rules from being checked set
            for rule_id, _, _ in filtered_rules:
                self._rules_being_checked.discard(rule_id)

    async def _execute_rules_logic_internal(
            self, target_rules: List[tuple[str, TriggerRule, Set[str]]],
            llm_proxy: LLMProxy, start_time: int):
        """Internal execution logic with locking handled by caller."""

        # 1. Get Camera Data
        relevant_cameras = set()
        for _, rule, _ in target_rules:
            relevant_cameras.update(rule.cameras)

        camera_motion_dict = {}
        camera_info_dict = {}

        if relevant_cameras:
            miot_camera_info_dict = await self.miot_proxy.get_cameras()
            camera_info_dict = {
                camera_id: CameraInfo.model_validate(miot_camera_info.model_dump())
                for camera_id, miot_camera_info in miot_camera_info_dict.items()
                if camera_id in relevant_cameras
            }

            for camera_id, camera_info in camera_info_dict.items():
                if camera_id not in camera_motion_dict:
                    camera_motion_dict[camera_id] = {}
                for channel in range(camera_info.channel_count or 1):
                    camera_img_seq = self.miot_proxy.get_recent_camera_img(
                        camera_id, channel, self._vision_use_img_count)
                    is_motion = False
                    if camera_img_seq:
                        is_motion = self._check_camera_motion(camera_img_seq)

                    camera_motion_dict[camera_id][channel] = (is_motion, camera_img_seq)

        # 2. Get Device States (HA)
        device_states = {}
        if self._ha_listener:
            device_states.update(self._ha_listener.get_all_states())

        # 3. Check Conditions
        tasks = []
        rule_info_list = []

        for rule_id, rule, trigger_sources in target_rules:
            # Filter device states relevant to this rule to reduce prompt token usage
            rule_device_states = {}

            # Add entities from selected devices
            if rule.ha_devices:
                for dev_id in rule.ha_devices:
                    entities = self._ha_device_map.get(dev_id, [])
                    for entity in entities:
                        if entity in device_states:
                            # Clone state info and mark if it was the trigger source
                            state_info = device_states[entity].copy()
                            if entity in trigger_sources:
                                state_info["_is_trigger_source"] = True
                            rule_device_states[entity] = state_info

            debug_states = {k: v.get("state") for k, v in rule_device_states.items()}
            logger.info(
                "Checking rule %s with device states: %s, trigger_sources: %s",
                rule.name, debug_states, trigger_sources)

            # If rule has no cameras and no devices, skip
            if not rule.cameras and not rule.ha_devices:
                continue

            # Check if we should use direct mode (no LLM)
            # Direct mode: no cameras, has HA devices, and condition_type is DIRECT
            use_direct_mode = (
                not rule.cameras and
                rule.ha_devices and
                hasattr(rule, 'condition_type') and
                rule.condition_type == ConditionType.DIRECT
            )

            # Check if we should use hybrid mode (HA direct check + camera LLM)
            use_hybrid_mode = (
                rule.cameras and
                rule.ha_devices and
                hasattr(rule, 'condition_type') and
                rule.condition_type == ConditionType.HYBRID
            )

            if use_hybrid_mode:
                # Hybrid mode: first check HA condition with direct mode
                logger.info("Rule %s using HYBRID mode (HA pre-filter + camera LLM)", rule.name)
                async def hybrid_check_wrapper():
                    return await self._check_trigger_condition_hybrid(
                        rule, llm_proxy, camera_motion_dict, camera_info_dict, rule_device_states)
                task = hybrid_check_wrapper()
                tasks.append(task)
            elif use_direct_mode:
                # Direct mode: no LLM needed, use synchronous check
                logger.info("Rule %s using DIRECT mode (zero token cost)", rule.name)
                # Direct check is synchronous, but we need an async function for asyncio.gather
                async def direct_check_wrapper():
                    return await self._check_trigger_condition_direct(rule, rule_device_states)
                task = direct_check_wrapper()
                tasks.append(task)
            else:
                # LLM mode: use original logic
                task = self._check_trigger_condition(
                    rule, llm_proxy, camera_motion_dict, camera_info_dict, rule_device_states)
                tasks.append(task)

            rule_info_list.append((rule_id, rule))

        if not tasks:
            return

        logger.info("Starting asyncio.gather for %d tasks", len(tasks))
        condition_results = await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("asyncio.gather completed, results count: %d", len(condition_results))

        # 4. Process Results
        for (rule_id, rule), condition_result_list in zip(rule_info_list, condition_results):
            logger.info("Processing result for rule %s: type=%s", rule_id, type(condition_result_list).__name__)

            if isinstance(condition_result_list, Exception):
                logger.error("Rule check failed for %s: %s", rule_id, condition_result_list)
                import traceback
                logger.error("Traceback: %s", traceback.format_exc())
                continue

            if not isinstance(condition_result_list, list):
                logger.warning("Rule check result for %s is not a list: %s", rule_id, condition_result_list)
                continue

            # Post filter logic
            # Note: For non-camera rules, we use a virtual "device" tag for filter
            execable = False

            if rule.cameras:
                # Camera based filter
                # camera_info should be present if rule.cameras is set, but check safety
                execable = any([
                    trigger_filter.post_filter(
                        rule_id,
                        f"{condition_result.camera_info.did},"
                        f"{condition_result.channel}" if condition_result.camera_info else "global",
                        condition_result.result)
                    for condition_result in condition_result_list
                ])
            else:
                # Pure device based filter
                # We assume if LLM says yes, it matches.
                # result is True if ANY condition result is True
                is_triggered = any(r.result for r in condition_result_list)

                # Deduplication: Only proceed if the AI conclusion changed
                last_conclusion = self._last_rule_conclusions.get(rule_id)
                self._last_rule_conclusions[rule_id] = is_triggered

                if last_conclusion == is_triggered:
                    logger.info("Rule %s: AI conclusion remains %s, skipping execution", rule.name, is_triggered)
                    execable = False
                else:
                    # Note: We still use post_filter for global state persistence if needed,
                    # but our internal check takes precedence for deduplication.
                    execable = trigger_filter.post_filter(rule_id, "global", is_triggered)

            is_dynamic_action_running = self._check_dynamic_action_is_running(rule_id)

            if execable and not is_dynamic_action_running:
                execute_id = str(uuid.uuid4())
                execute_result = await self._execute_trigger_action(execute_id, rule, camera_motion_dict)
                await self._log_rule_execution(execute_id, start_time, rule,
                                               camera_motion_dict,
                                               condition_result_list,
                                               execute_result)

    async def _execute_scheduled_task(self):
        """Specific execution logic for scheduled tasks"""
        logger.debug("Executing scheduled task - checking trigger rules")

        # Periodic check is for:
        # 1. Vision-based rules in LLM mode (contain cameras, no HA devices or condition_type=LLM)
        # 2. Active hybrid mode rules (HA condition met, need continuous camera check)
        # 3. Other poll-based rules (if any)
        # Pure HA rules are skipped here because they are handled by WebSocket events.
        enabled_rules = []
        active_hybrid_rule_ids = []

        for rule_id, rule in self.trigger_rules.items():
            if not rule.cameras or not trigger_filter.pre_filter(rule):
                continue

            # Skip detection mode rules - they are handled by detection trigger integration
            is_detection_mode = (
                hasattr(rule, 'condition_type') and
                rule.condition_type in (ConditionType.DETECTION, ConditionType.FACE_RECOGNITION)
            )
            if is_detection_mode:
                logger.debug("Skipping detection mode rule %s in scheduled task", rule.name)
                continue

            # Check if this is a hybrid mode rule
            is_hybrid_mode = (
                rule.ha_devices and
                hasattr(rule, 'condition_type') and
                rule.condition_type == ConditionType.HYBRID
            )

            if is_hybrid_mode:
                # Check if this hybrid rule is active (HA condition met)
                if rule_id in self._active_hybrid_rules:
                    active_hybrid_rule_ids.append(rule_id)
                    logger.debug("Including active hybrid mode rule %s in periodic check", rule.name)
                else:
                    logger.debug("Skipping inactive hybrid mode rule %s", rule.name)
                continue

            # LLM mode: include in periodic check
            enabled_rules.append(rule_id)

        # Execute LLM mode rules
        if enabled_rules:
            logger.info("Periodic check: executing %d LLM mode camera rules", len(enabled_rules))
            await self._check_rules_batch(enabled_rules)
        else:
            logger.debug("No LLM mode camera rules to check in periodic task")

        # Execute active hybrid mode rules (HA condition met, checking camera)
        if active_hybrid_rule_ids:
            logger.info("Periodic check: executing %d active hybrid mode rules", len(active_hybrid_rule_ids))
            await self._check_rules_batch(active_hybrid_rule_ids)

    async def _log_rule_execution(
            self,
            execute_id: str,
            start_time: int,
            rule: TriggerRule,
            camera_motion_dict: dict[str, dict[int, tuple[bool, Optional[CameraImgSeq]]]],
            condition_result_list: list[TriggerConditionResult],
            execute_result: Optional[ExecuteResult] = None):
        """Record rule trigger and execution logs, save to database"""
        logger.info(
            "Rule %s triggered, condition results: %s", rule.name, condition_result_list
        )

        for condition_result in condition_result_list:
            # Handle camera images if available
            if condition_result.camera_info:
                is_motion, camera_img_seq = camera_motion_dict.get(
                    condition_result.camera_info.did, {}).get(
                        condition_result.channel, (False, None))
                if is_motion and condition_result.result and camera_img_seq:
                    path_seq: CameraImgPathSeq = await camera_img_seq.store_to_path()
                    condition_result.images = path_seq.img_list

        trigger_rule_log = TriggerRuleLog(
            id=execute_id,
            timestamp=start_time,
            trigger_rule_id=rule.id,
            trigger_rule_name=rule.name,
            trigger_rule_condition=rule.condition,
            condition_results=condition_result_list,
            execute_result=execute_result,
        )

        # Save to database
        log_id = self.trigger_rule_log_dao.create(trigger_rule_log)
        if log_id:
            logger.info(
                "Trigger rule log saved to database: id=%s, rule_id=%s", log_id, rule.id
            )
        else:
            logger.error(
                "Failed to save trigger rule log to database: rule_id=%s", rule.id
            )

    async def start_periodic_task(self):
        """Start async scheduled task"""
        if self._is_running:
            logger.warning("Scheduled task is already running")
            return

        self._is_running = True

        # Start HA Listener
        if self._ha_listener:
            asyncio.create_task(self._ha_listener.start())

        # Refresh device map once on startup
        asyncio.create_task(self._refresh_ha_device_map())

        # Initialize Detection Trigger Integration
        try:
            self._detection_trigger_integration = await get_detection_trigger_integration()
            await self._detection_trigger_integration.initialize(self._on_detection_trigger)

            # Register existing rules with detection conditions
            for rule in self.trigger_rules.values():
                if rule.detection_condition and rule.detection_condition.enabled:
                    self._detection_trigger_integration.add_rule(rule)

            logger.info("Detection trigger integration initialized")
        except Exception as e:
            logger.warning(f"Failed to initialize detection trigger integration: {e}")

        self._task = asyncio.create_task(self._periodic_task())
        logger.info("Scheduled task started, executing every %d seconds", self._interval_seconds)

    async def stop_periodic_task(self):
        """Stop async scheduled task"""
        if not self._is_running:
            logger.warning("Scheduled task is not running")
            return

        self._is_running = False

        # Stop HA Listener
        if self._ha_listener:
            await self._ha_listener.stop()

        # Stop Detection Trigger Integration
        if self._detection_trigger_integration:
            await self._detection_trigger_integration.destroy()
            self._detection_trigger_integration = None

        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info("Scheduled task stopped")

    def is_task_running(self) -> bool:
        """Check if scheduled task is running"""
        return self._is_running

    async def _call_vision_understaning(self, llm_proxy: LLMProxy, messages):
        """
        Call vision understanding LLM

        Returns:
            LLM response result
        """

        return await llm_proxy.async_call_llm(messages)

    async def _check_trigger_condition(
        self, rule: TriggerRule, llm_proxy: LLMProxy,
        camera_motion_dict: dict[str, dict[int,
                                           tuple[bool,
                                                 Optional[CameraImgSeq]]]],
        camera_info_dict: dict[str, CameraInfo],
        device_states: Optional[Dict[str, Any]] = None) -> List[TriggerConditionResult]:

        cameras_video: dict[tuple[str, int], CameraImgSeq] = {}
        condition_result_list: List[TriggerConditionResult] = []

        # If rule has cameras, collect them
        if rule.cameras:
            for camera_id in rule.cameras:
                if camera_id not in camera_info_dict:
                    continue

                camera_info = camera_info_dict[camera_id]
                channel_motion_dict = camera_motion_dict.get(camera_id, {})
                for channel, (_, camera_img_seq) in channel_motion_dict.items():
                    if camera_img_seq:
                        cameras_video[camera_id, channel] = camera_img_seq
                    else:
                        condition_result_list.append(
                            TriggerConditionResult(camera_info=camera_info,
                                                channel=channel,
                                                result=False,
                                                images=None))

        # If rule has NO cameras, we still need to run LLM if device_states are present.
        if not cameras_video and rule.ha_devices:
            # Use a dummy key to run the loop once
            cameras_video[("no_camera", 0)] = None

        # Concurrently execute LLM calls
        tasks = []
        for (camera_id, channel), camera_img_seq in cameras_video.items():
            messages = TriggerRuleConditionPromptBuilder.build_trigger_rule_prompt(
                camera_img_seq, rule.condition, self._get_language(), device_states)
            task = self._call_vision_understaning(llm_proxy, messages.get_messages())
            tasks.append(task)

        # Concurrently execute all tasks
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        for ((camera_id, channel),
             camera_img_seq), response in zip(cameras_video.items(),
                                              responses):
            # Check for exceptions
            if isinstance(response, Exception):
                logger.error(
                    "LLM call failed for rule %s (cam: %s): %s", rule.name, camera_id, response
                )
                continue

            # Ensure response is dict type before accessing
            if not isinstance(response, dict):
                logger.error(
                    "Invalid response type for rule %s: %s", rule.name, type(response)
                )
                continue

            content = response["content"]
            logger.info(
                "Condition result, rule name: %s, condition: %s, cam: %s, content: %s",
                rule.name, rule.condition, camera_id, content
            )

            if not content:
                continue

            try:
                # Use optimized helper method to extract JSON content
                json_content = extract_json_from_content(content)
                content_dict = json.loads(json_content)
            except json.JSONDecodeError as e:
                logger.error(
                    "Failed to parse JSON. Content: %s, Error: %s", content, e)
                continue
            except Exception as e:  # pylint: disable=broad-except
                logger.error("Error processing content: %s, Error: %s", content, e)
                continue

            # Construct result
            # If it was a dummy camera, camera_info is None or dummy
            cam_info = camera_info_dict.get(camera_id) if camera_id != "no_camera" else None

            condition_result = TriggerConditionResult(
                camera_info=cam_info,
                channel=channel,
                result=content_dict.get("result") == "yes"
            )

            condition_result_list.append(condition_result)

        return condition_result_list

    async def _check_trigger_condition_direct(
        self, rule: TriggerRule, rule_device_states: Dict[str, Dict[str, Any]]
    ) -> List[TriggerConditionResult]:
        """
        Check trigger condition using direct state matching (no LLM).

        Args:
            rule: Trigger rule to check
            rule_device_states: Device states relevant to this rule

        Returns:
            List of condition results (usually single element for direct mode)
        """
        logger.info("=" * 60)
        logger.info("DIRECT MODE CHECK START for rule: %s", rule.name)
        logger.info("Condition: %s", rule.condition)
        logger.info("Device states: %s", {k: v.get("state") for k, v in rule_device_states.items()})
        logger.info("=" * 60)

        # Direct mode should not depend on having a "_is_trigger_source" marker.
        # Prefer explicit trigger_entity_id if configured; otherwise evaluate against all entities.
        trigger_entity_id = None

        # 1) Prefer configured trigger entity (direct/hybrid form field)
        if getattr(rule, "trigger_entity_id", None) and rule.trigger_entity_id in rule_device_states:
            trigger_entity_id = rule.trigger_entity_id
        else:
            # 2) Fall back to the entity that triggered this check (if any)
            for entity_id, state_info in rule_device_states.items():
                if state_info.get("_is_trigger_source", False):
                    trigger_entity_id = entity_id
                    break

        # Use ha_condition for direct mode, fallback to condition for backward compatibility
        ha_check_condition = rule.ha_condition if rule.ha_condition else rule.condition
        if not ha_check_condition:
            logger.warning("Direct mode rule %s has empty condition, skipping", rule.name)
            return [TriggerConditionResult(camera_info=None, channel=0, result=False, images=None)]

        # Use direct condition checker (synchronous)
        result = direct_condition_checker.evaluate(
            ha_check_condition,
            rule_device_states,
            trigger_entity_id,
        )

        logger.info(
            "Direct condition check result for rule %s: %s (condition: %s, entity: %s, state: %s)",
            rule.name,
            result,
            ha_check_condition,
            trigger_entity_id,
            rule_device_states.get(trigger_entity_id, {}).get("state", "unknown") if trigger_entity_id else "n/a",
        )

        # Return single result (no camera context for direct mode)
        return [TriggerConditionResult(
            camera_info=None,
            channel=0,
            result=result,
            images=None
        )]

    async def _check_trigger_condition_hybrid(
        self, rule: TriggerRule, llm_proxy: LLMProxy,
        camera_motion_dict: dict[str, dict[int,
                                           tuple[bool,
                                                 Optional[CameraImgSeq]]]],
        camera_info_dict: dict[str, CameraInfo],
        rule_device_states: Dict[str, Dict[str, Any]]
    ) -> List[TriggerConditionResult]:
        """
        Check trigger condition using hybrid mode: first check HA devices with direct mode,
        if HA condition matches, then check cameras with LLM.

        This is useful for reducing LLM calls when HA devices serve as pre-filters.

        Args:
            rule: Trigger rule to check
            llm_proxy: LLM proxy for camera analysis
            camera_motion_dict: Camera motion data
            camera_info_dict: Camera information
            rule_device_states: Device states relevant to this rule

        Returns:
            List of condition results (one per camera)
        """
        logger.info(
            "Checking rule %s using HYBRID mode (HA pre-check -> camera LLM), condition: %s",
            rule.name, rule.condition
        )

        # Step 1: Check HA devices using direct mode (synchronous)
        # Try to find trigger source (from HA event), but it's optional for hybrid mode
        # Hybrid mode checks current state of all devices, not just the trigger source
        trigger_entity_id = None
        for entity_id, state_info in rule_device_states.items():
            if state_info.get("_is_trigger_source", False):
                trigger_entity_id = entity_id
                break

        if not trigger_entity_id:
            logger.info(
                "HYBRID mode: No specific trigger source for rule %s, "
                "checking all device states", rule.name
            )
            # Use first available entity as reference (for state logging)
            if rule_device_states:
                trigger_entity_id = next(iter(rule_device_states.keys()))

        if not rule_device_states:
            logger.warning("No device states available for rule %s in HYBRID mode", rule.name)
            # Return false results for all cameras
            condition_result_list = []
            for camera_id in rule.cameras:
                if camera_id in camera_info_dict:
                    camera_info = camera_info_dict[camera_id]
                    for channel in range(camera_info.channel_count or 1):
                        condition_result_list.append(
                            TriggerConditionResult(
                                camera_info=camera_info,
                                channel=channel,
                                result=False,
                                images=None
                            ))
            return condition_result_list

        # Evaluate HA condition using direct checker
        # Use ha_condition if provided, otherwise fallback to rule.condition for backward compatibility
        ha_check_condition = rule.ha_condition if rule.ha_condition else rule.condition
        logger.info(
            "HYBRID mode: Checking HA condition: %s (ha_condition: %s, fallback: %s)",
            ha_check_condition,
            rule.ha_condition or "(not set)",
            rule.condition
        )

        # For hybrid mode, check ALL entities against the condition
        # This differs from direct mode which only checks the trigger source
        ha_condition_matched = direct_condition_checker.evaluate(
            ha_check_condition,
            rule_device_states,
            rule.trigger_entity_id or trigger_entity_id  # Prefer configured entity, fallback to trigger source
        )

        # Get state for logging (handle case where trigger_entity_id might not be in rule_device_states)
        log_state = "unknown"
        if trigger_entity_id and trigger_entity_id in rule_device_states:
            log_state = rule_device_states[trigger_entity_id].get("state", "unknown")

        logger.info(
            "HYBRID mode HA pre-check for rule %s: %s (condition: %s, state: %s)",
            rule.name, ha_condition_matched, ha_check_condition, log_state
        )

        # Step 2: If HA condition doesn't match, skip LLM calls entirely
        if not ha_condition_matched:
            logger.info(
                "HYBRID mode: HA condition not met for rule %s, skipping camera LLM analysis",
                rule.name
            )
            # Remove from active hybrid rules if present
            if rule.id in self._active_hybrid_rules:
                del self._active_hybrid_rules[rule.id]
                logger.info("Removed rule %s from active hybrid rules (HA condition not met)", rule.name)
            # Return false results for all cameras
            condition_result_list = []
            for camera_id in rule.cameras:
                if camera_id in camera_info_dict:
                    camera_info = camera_info_dict[camera_id]
                    for channel in range(camera_info.channel_count or 1):
                        condition_result_list.append(
                            TriggerConditionResult(
                                camera_info=camera_info,
                                channel=channel,
                                result=False,
                                images=None
                            ))
            return condition_result_list

        # Step 3: HA condition matched, proceed to check cameras with LLM
        logger.info(
            "HYBRID mode: HA condition met for rule %s, proceeding to camera LLM analysis",
            rule.name
        )

        # Add to active hybrid rules for continuous camera checking
        if rule.id not in self._active_hybrid_rules:
            self._active_hybrid_rules[rule.id] = {
                'rule': rule,
                'last_check_time': time.time(),
                'ha_condition_met': True
            }
            logger.info("Added rule %s to active hybrid rules (HA condition met)", rule.name)

        # Collect camera data
        cameras_video: dict[tuple[str, int], CameraImgSeq] = {}
        condition_result_list: List[TriggerConditionResult] = []

        for camera_id in rule.cameras:
            if camera_id not in camera_info_dict:
                continue

            camera_info = camera_info_dict[camera_id]
            channel_motion_dict = camera_motion_dict.get(camera_id, {})
            for channel, (_, camera_img_seq) in channel_motion_dict.items():
                if camera_img_seq:
                    cameras_video[camera_id, channel] = camera_img_seq
                else:
                    condition_result_list.append(
                        TriggerConditionResult(
                            camera_info=camera_info,
                            channel=channel,
                            result=False,
                            images=None
                        ))

        # Step 4: Call LLM for each camera
        # Use rule.condition (main trigger condition) for LLM camera analysis
        camera_analysis_condition = rule.condition
        logger.info(
            "HYBRID mode: Using main condition for LLM camera analysis: %s",
            camera_analysis_condition
        )

        tasks = []
        for (camera_id, channel), camera_img_seq in cameras_video.items():
            # Note: In hybrid mode, we pass device_states to LLM as context
            # even though we already checked them, for better understanding
            messages = TriggerRuleConditionPromptBuilder.build_trigger_rule_prompt(
                camera_img_seq, camera_analysis_condition, self._get_language(), rule_device_states)
            task = self._call_vision_understaning(llm_proxy, messages.get_messages())
            tasks.append(task)

        # Execute LLM calls concurrently
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        # Process LLM results
        for ((camera_id, channel), camera_img_seq), response in zip(
            cameras_video.items(), responses
        ):
            if isinstance(response, Exception):
                logger.error(
                    "LLM call failed for rule %s (cam: %s): %s",
                    rule.name, camera_id, response
                )
                continue

            if not isinstance(response, dict):
                logger.error(
                    "Invalid response type for rule %s: %s",
                    rule.name, type(response)
                )
                continue

            content = response["content"]
            if not content:
                continue

            try:
                json_content = extract_json_from_content(content)
                content_dict = json.loads(json_content)
            except json.JSONDecodeError as e:
                logger.error("Failed to parse JSON. Content: %s, Error: %s", content, e)
                continue
            except Exception as e:
                logger.error("Error processing content: %s, Error: %s", content, e)
                continue

            camera_info = camera_info_dict.get(camera_id)
            if camera_info:
                condition_result = TriggerConditionResult(
                    camera_info=camera_info,
                    channel=channel,
                    result=content_dict.get("result") == "yes"
                )
                condition_result_list.append(condition_result)

        logger.info(
            "HYBRID mode final results for rule %s: %s matched out of %d cameras",
            rule.name,
            sum(1 for r in condition_result_list if r.result),
            len(condition_result_list)
        )

        return condition_result_list

    def _check_camera_motion(self, camera_img_seq: CameraImgSeq) -> bool:
        """Detect motion in images"""
        if len(camera_img_seq.img_list) < 2:
            return False
        return check_camera_motion(camera_img_seq.img_list[0].data,
                                   camera_img_seq.img_list[-1].data)

    async def _execute_trigger_action(
        self, execute_id: str, rule: TriggerRule,
        camera_motion_dict: dict[str, dict[int,
                                           tuple[bool,
                                                 Optional[CameraImgSeq]]]]
    ) -> Optional[ExecuteResult]:
        """Execute trigger action"""
        logger.info("[%s] Executing trigger action: %s", execute_id, rule.name)

        if not rule.execute_info:
            return None

        execute_type = rule.execute_info.ai_recommend_execute_type
        ai_recommend_action_execute_results = None
        ai_recommend_dynamic_execute_result = None
        automation_action_execute_results = None
        notify_result = None
        wakeup_cfg = rule.execute_info.xiaoai_wakeup if rule.execute_info else None
        interactive_wakeup = (
            wakeup_cfg
            and wakeup_cfg.enabled
            and wakeup_cfg.mode != WakeUpMode.MANUAL
        )

        # Handle STATIC action type
        if (not interactive_wakeup) and execute_type == ExecuteType.STATIC and rule.execute_info.ai_recommend_actions:
            ai_recommend_action_execute_results = []
            for action in rule.execute_info.ai_recommend_actions:
                result = await self.execute_action(action)
                ai_recommend_action_execute_results.append(
                    ActionExecuteResult(action=action, result=result))

        # Handle DYNAMIC action type
        if (not interactive_wakeup) and execute_type == ExecuteType.DYNAMIC:
            ai_recommend_dynamic_execute_result = AiRecommendDynamicExecuteResult(
                is_done=False,
                ai_recommend_action_descriptions=rule.execute_info.ai_recommend_action_descriptions,
                chat_history_session=None)
            if rule.execute_info.ai_recommend_action_descriptions:
                # execute dynamic action in background
                asyncio.create_task(self._execute_dynamic_action(execute_id, rule, camera_motion_dict))
            else:
                ai_recommend_dynamic_execute_result.is_done = True
                logger.warning("[%s] Dynamic action descriptions not found, skip dynamic action", execute_id)

        # Handle automation actions
        if (not interactive_wakeup) and rule.execute_info.automation_actions:
            automation_action_execute_results = []
            for action in rule.execute_info.automation_actions:
                result = await self.execute_action(action)
                automation_action_execute_results.append(
                    ActionExecuteResult(action=action, result=result))

        # Send MiOT notification
        if rule.execute_info.notify:
            notify_res = await self.miot_proxy.send_app_notify(rule.execute_info.notify.id)
            logger.info("Send miot notify result: %s, notify: %s", notify_res, rule.execute_info.notify)
            notify_result = NotifyResult(notify=rule.execute_info.notify, result=notify_res)

        # XiaoAI broadcast action
        # In interactive wakeup mode, proactive inquiry TTS is handled by WakeUpScheduler to avoid double-TTS.
        if (not interactive_wakeup) and rule.execute_info.xiaoai_broadcast:
            await self._execute_xiaoai_broadcast(rule)

        # WakeUp (唤醒小爱) interactive voice flow:
        if interactive_wakeup:
            try:
                bridge_manager = get_bridge_manager()
                planning_proxy = self._get_planning_llm_proxy()
                wakeup_scheduler = WakeUpScheduler(
                    bridge_manager=bridge_manager,
                    llm_proxy=planning_proxy,
                    tool_executor=self._tool_executor
                )
                wakeup_scheduler.set_ha_proxy(self.ha_proxy)
                _ = await wakeup_scheduler.execute_wakeup_flow(rule, trigger_event=None)
            except Exception as e:
                logger.error("WakeUpScheduler execution failed for rule %s: %s", rule.name, e)

        return ExecuteResult(
            ai_recommend_execute_type=execute_type,
            ai_recommend_action_execute_results=ai_recommend_action_execute_results,
            ai_recommend_dynamic_execute_result=ai_recommend_dynamic_execute_result,
            automation_action_execute_results=automation_action_execute_results,
            notify_result=notify_result
        )

    async def _execute_xiaoai_broadcast(self, rule: TriggerRule) -> bool:
        """Execute XiaoAI broadcast action configured in rule."""
        try:
            cfg = rule.execute_info.xiaoai_broadcast
            if not cfg:
                return False

            # Get target device IDs (if specified)
            device_ids = cfg.device_ids if hasattr(cfg, 'device_ids') else None

            if cfg.mode == XiaoAIBroadcastMode.TEXT:
                text = (cfg.text or "").strip()
                if not text:
                    logger.warning("Rule %s XiaoAI broadcast skipped: empty text", rule.name)
                    return False

                # Prefer integrated Xiaomi Bridge (open-xiaoai client-rust RPC). If device_ids is None, broadcast to all.
                result = await broadcast_via_bridge(text, device_ids)

                logger.info("Rule %s XiaoAI text broadcast result: %s", rule.name, result)
                return result

            if cfg.mode == XiaoAIBroadcastMode.MODEL_REPLY:
                user_question = (cfg.text or "").strip()
                if not user_question:
                    logger.warning("Rule %s XiaoAI model_reply skipped: empty user question", rule.name)
                    return False

                # Use AI Chat Adapter to process the query with full tool calling capability
                from miloco_server.service.ai_chat_adapter import APIChatAdapter, parse_ai_response
                import uuid
                
                request_id = str(uuid.uuid4())
                chat_adapter = APIChatAdapter(request_id)
                
                # Get MCP list from rule configuration
                mcp_list = rule.mcp_list if hasattr(rule, 'mcp_list') and rule.mcp_list else None
                
                # Process query using AI chat adapter (includes tool calling)
                response_text = ""
                try:
                    async for message in chat_adapter.process_query(
                        query=user_question,
                        camera_ids=[],
                        mcp_list=mcp_list
                    ):
                        if message["type"] == "complete":
                            response_text = message["data"].get("response", "")
                            break
                except Exception as e:
                    logger.error("Rule %s XiaoAI model_reply chat adapter error: %s", rule.name, e)
                    return False

                if not response_text:
                    logger.warning("Rule %s XiaoAI model_reply skipped: empty model response", rule.name)
                    return False

                # Extract only the <final_answer> content for broadcast
                parsed_response = parse_ai_response(response_text)
                broadcast_content = parsed_response.get("final_answer", "").strip()
                
                if not broadcast_content:
                    logger.warning("Rule %s XiaoAI model_reply skipped: no <final_answer> tag found", rule.name)
                    return False

                # Prefer integrated Xiaomi Bridge (open-xiaoai client-rust RPC).
                result = await broadcast_via_bridge(broadcast_content, device_ids)

                logger.info("Rule %s XiaoAI model_reply broadcast result: %s", rule.name, result)
                return result

            logger.warning("Rule %s XiaoAI broadcast skipped: unsupported mode %s", rule.name, cfg.mode)
            return False
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("Rule %s XiaoAI broadcast failed: %s", rule.name, exc)
            return False

    async def _execute_dynamic_action(self, execute_id: str, rule: TriggerRule,
                                    camera_motion_dict: dict[str, dict[int,
                                           tuple[bool,
                                                 Optional[CameraImgSeq]]]]) -> None:
        """Execute dynamic action"""
        try:
            logger.info("[%s] Executing dynamic action: %s", execute_id, rule.name)
            trigger_rule_dynamic_executor = trigger_rule_dynamic_executor_cache.get(rule.id)
            if trigger_rule_dynamic_executor:
                logger.error(
                    "[%s] Dynamic executor already exists pass it, trigger_rule: %s",
                    execute_id, rule.name)
                return

            trigger_rule_dynamic_executor = actor_system.createActor(
                lambda: TriggerRuleDynamicExecutor(
                    execute_id, rule, self.trigger_rule_log_dao, camera_motion_dict))
            trigger_rule_dynamic_executor_cache[rule.id] = trigger_rule_dynamic_executor
            future = actor_system.ask(trigger_rule_dynamic_executor, START, timeout=5)
            result = await asyncio.wait_for(future, timeout=300)
            logger.info("[%s] Dynamic executor executed, result: %s", execute_id, result)
        except asyncio.TimeoutError as exc:
            logger.error("[%s] Dynamic executor timeout: %s", execute_id, exc)
        except Exception as e:  # pylint: disable=broad-except
            logger.error("[%s] Dynamic executor error: %s", execute_id, e)
        finally:
            actor_system.tell(trigger_rule_dynamic_executor, ActorExitRequest())
            trigger_rule_dynamic_executor_cache.pop(rule.id, None)

    async def execute_action(self, action: Action) -> bool:
        """Execute MCP action"""
        try:
            logger.info("Executing MCP action: %s on server %s", action.mcp_tool_name, action.mcp_server_name)

            result: CallToolResult = await self._tool_executor.execute_tool_by_params(
                action.mcp_client_id, action.mcp_tool_name,
                action.mcp_tool_input)

            logger.info("MCP action executed successfully: %s, result: %s", action.mcp_tool_name, result)
            return result.success

        except Exception as e:  # pylint: disable=broad-except
            logger.error(
                "Failed to execute MCP action %s: %s", action.mcp_tool_name, e)
            return False

    def _check_dynamic_action_is_running(self, rule_id: str) -> bool:
        """Check if dynamic action is running"""
        return rule_id in trigger_rule_dynamic_executor_cache

    async def _on_detection_trigger(self, rule_id: str, camera_id: str, reason: str):
        """
        Callback when a detection-based rule is triggered.

        Args:
            rule_id: ID of the triggered rule
            camera_id: ID of the camera that detected the target
            reason: Human-readable trigger reason
        """
        logger.info(
            "Detection trigger callback: rule=%s, camera=%s, reason=%s",
            rule_id, camera_id, reason
        )

        rule = self.trigger_rules.get(rule_id)
        if not rule:
            logger.warning(f"Rule {rule_id} not found for detection trigger")
            return

        if not rule.enabled:
            logger.debug(f"Rule {rule.name} is disabled, ignoring detection trigger")
            return

        # Check filter
        if not trigger_filter.pre_filter(rule):
            logger.debug(f"Rule {rule.name} failed pre-filter, ignoring detection trigger")
            return

        # Execute the rule immediately (detection conditions are already evaluated)
        execute_id = str(uuid.uuid4())
        start_time = int(time.time() * 1000)

        # Prepare camera motion dict for logging
        camera_motion_dict = {}

        try:
            execute_result = await self._execute_trigger_action(execute_id, rule, camera_motion_dict)

            # Create condition result for logging
            from miloco_server.schema.trigger_log_schema import TriggerConditionResult
            condition_result = TriggerConditionResult(
                camera_info=None,  # Could be enhanced to include camera info
                channel=0,
                result=True,
                detection_reason=reason
            )

            await self._log_rule_execution(
                execute_id, start_time, rule,
                camera_motion_dict,
                [condition_result],
                execute_result
            )

            logger.info(f"Detection trigger executed for rule {rule.name}: {execute_id}")

        except Exception as e:
            logger.error(f"Error executing detection trigger for rule {rule.name}: {e}")
