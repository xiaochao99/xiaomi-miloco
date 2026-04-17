# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Trigger rule service module
"""

import logging
from typing import List, Optional, Any

from fastapi import WebSocket
from miot.types import MIoTCameraInfo
from miloco_server.schema.mcp_schema import MCPClientStatus, choose_mcp_list

from miloco_server import actor_system
from miloco_server.dao.trigger_dao import TriggerRuleDAO
from miloco_server.dao.trigger_rule_log_dao import TriggerRuleLogDAO
from miloco_server.mcp.mcp_client_manager import MCPClientManager
from miloco_server.middleware.exceptions import (
    ConflictException,
    ValidationException,
    ResourceNotFoundException,
    BusinessException,
)
from miloco_server.proxy.miot_proxy import MiotProxy
from miloco_server.schema.miot_schema import choose_camera_list, HADeviceInfo
from miloco_server.schema.trigger_log_schema import TriggerRuleLog
from miloco_server.schema.trigger_schema import (
    Action, Notify, TriggerRule, TriggerRuleV2, ConditionType)
from miloco_server.service.trigger_rule_runner import TriggerRuleRunner
from miloco_server.service.ha_service import HaService
from miloco_server.service.trigger_rule_service_detection import DetectionTriggerServiceMixin

from miloco_server.service import trigger_rule_dynamic_executor_cache
from miloco_server.service.trigger_rule_dynamic_executor import RegisterWebSocket

logger = logging.getLogger(__name__)


class TriggerRuleService(DetectionTriggerServiceMixin):
    """Trigger rule service class"""

    def __init__(self, trigger_rule_dao: TriggerRuleDAO,
                 trigger_rule_log_dao: TriggerRuleLogDAO,
                 trigger_rule_runner: TriggerRuleRunner,
                 miot_proxy: MiotProxy,
                 mcp_client_manager: MCPClientManager,
                 ha_service: Optional[HaService] = None):
        self._trigger_rule_dao = trigger_rule_dao
        self._trigger_rule_log_dao = trigger_rule_log_dao
        self._trigger_rule_runner = trigger_rule_runner
        self._miot_proxy = miot_proxy
        self._mcp_client_manager = mcp_client_manager
        self._ha_service = ha_service

    async def initialize_detection_on_startup(self):
        """
        服务启动时初始化所有已启用的目标检测规则
        用于服务器重启后恢复检测状态
        """
        logger.info("[Startup] Initializing detection rules on startup...")
        try:
            # 等待一段时间让摄像头连接
            logger.info("[Startup] Waiting 5 seconds for cameras to connect...")
            import asyncio
            await asyncio.sleep(5)

            # 获取所有启用的规则（v2），并转换为运行时 TriggerRule
            all_rules_v2 = self._trigger_rule_dao.get_all_v2(enabled_only=True)
            all_rules = [r.to_runtime_rule() for r in all_rules_v2]
            logger.info(f"[Startup] Found {len(all_rules)} enabled rules (v2)")

            detection_rules_started = 0
            cameras_started = set()

            for rule in all_rules:
                logger.info(f"[Startup] Checking rule {rule.id}: condition_type={rule.condition_type}, "
                           f"has_detection={rule.detection_condition is not None}")

                # 检查规则是否有检测条件且启用
                if (rule.detection_condition and
                    rule.detection_condition.enabled and
                    rule.cameras):

                    logger.info(f"[Startup] Starting detection for rule {rule.id} with cameras {rule.cameras}")
                    try:
                        detection_result = await self._handle_detection_condition_on_create(rule)
                        if detection_result.get("cameras_started"):
                            detection_rules_started += 1
                            cameras_started.update(detection_result["cameras_started"])
                            logger.info(f"[Startup] Successfully started detection for rule {rule.id}")

                        if detection_result.get("errors"):
                            logger.warning(f"[Startup] Failed to start detection for rule {rule.id}: {detection_result['errors']}")

                    except Exception as e:
                        logger.error(f"[Startup] Error starting detection for rule {rule.id}: {e}", exc_info=True)
                else:
                    logger.info(f"[Startup] Rule {rule.id} has no detection condition or disabled")

            logger.info(f"[Startup] Detection initialization completed: {detection_rules_started} rules started, {len(cameras_started)} cameras active")

        except Exception as e:
            logger.error(f"[Startup] Error initializing detection on startup: {e}", exc_info=True)

    async def create_trigger_rule_v2(self, trigger_rule: TriggerRuleV2) -> str:
        """Create trigger rule using v2 schema/table."""
        if self._trigger_rule_dao.exists_by_name_v2(trigger_rule.name):
            raise ConflictException(f"Trigger rule name '{trigger_rule.name}' already exists")
        await self._validate_trigger_rule_v2(trigger_rule)
        if trigger_rule.execute_info and trigger_rule.execute_info.notify:
            await self._check_notify(trigger_rule.execute_info.notify)

        rule_id = self._trigger_rule_dao.create_v2(trigger_rule)
        if not rule_id:
            raise BusinessException("Failed to create trigger rule")

        trigger_rule.id = rule_id
        runtime_rule = trigger_rule.to_runtime_rule()
        self._trigger_rule_runner.add_trigger_rule(runtime_rule)

        if runtime_rule.detection_condition and runtime_rule.detection_condition.enabled:
            await self._handle_detection_condition_on_create(runtime_rule)
        return rule_id

    async def get_all_trigger_rules_v2(self, enabled_only: bool = False) -> List[TriggerRuleV2]:
        """Get all v2 trigger rules."""
        return self._trigger_rule_dao.get_all_v2(enabled_only)

    async def update_trigger_rule_v2(self, trigger_rule: TriggerRuleV2) -> bool:
        """Update trigger rule in v2 table."""
        if not trigger_rule.id:
            raise ValidationException("Rule ID is required")
        if not self._trigger_rule_dao.exists_v2(trigger_rule.id):
            raise ResourceNotFoundException(f"Trigger rule with ID '{trigger_rule.id}' not found")
        if self._trigger_rule_dao.exists_by_name_v2(trigger_rule.name, trigger_rule.id):
            raise ConflictException(f"Trigger rule name '{trigger_rule.name}' already exists")
        await self._validate_trigger_rule_v2(trigger_rule)
        if trigger_rule.execute_info and trigger_rule.execute_info.notify:
            await self._check_notify(trigger_rule.execute_info.notify)

        # for detection update diff we need old runtime rule
        old_v2 = self._trigger_rule_dao.get_by_id_v2(trigger_rule.id)
        old_runtime = old_v2.to_runtime_rule() if old_v2 else None

        success = self._trigger_rule_dao.update_v2(trigger_rule)
        if success:
            runtime_rule = trigger_rule.to_runtime_rule()
            self._trigger_rule_runner.add_trigger_rule(runtime_rule)
            try:
                await self._handle_detection_condition_on_update(runtime_rule, old_runtime)
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.error("Error handling detection condition update for rule %s: %s", trigger_rule.id, e)
        return success

    async def delete_trigger_rule_v2(self, rule_id: str) -> bool:
        """Delete trigger rule from v2 table."""
        if not self._trigger_rule_dao.exists_v2(rule_id):
            raise ResourceNotFoundException(f"Trigger rule with ID '{rule_id}' not found")

        old_v2 = self._trigger_rule_dao.get_by_id_v2(rule_id)
        old_runtime = old_v2.to_runtime_rule() if old_v2 else None

        success = self._trigger_rule_dao.delete_v2(rule_id)
        if success:
            self._trigger_rule_runner.remove_trigger_rule(rule_id)
            if old_runtime:
                try:
                    await self._handle_detection_condition_on_delete(old_runtime)
                except Exception as e:  # pylint: disable=broad-exception-caught
                    logger.error("Error handling detection condition delete for rule %s: %s", rule_id, e)
        return success

    async def _validate_trigger_rule_v2(self, trigger_rule: TriggerRuleV2) -> None:
        """Validate v2 trigger rule with condition-aware checks."""
        condition_type = trigger_rule.trigger.type
        camera_ids = trigger_rule.targets.camera_ids or []
        ha_device_ids = trigger_rule.targets.ha_device_ids or []

        valid_cameras = await self._miot_proxy.get_camera_dids()
        invalid_cameras = [did for did in camera_ids if did not in valid_cameras]
        if invalid_cameras:
            raise ValidationException(f"Invalid camera device IDs: {', '.join(invalid_cameras)}")

        ha_devices_grouped = await self._ha_service.get_ha_devices_grouped() if self._ha_service else {}
        if ha_device_ids:
            valid_ha_dids = set(ha_devices_grouped.keys())
            invalid_ha = [did for did in ha_device_ids if did not in valid_ha_dids]
            if invalid_ha:
                raise ValidationException(f"Invalid HA device IDs: {', '.join(invalid_ha)}")

        if condition_type == ConditionType.DIRECT:
            if not ha_device_ids:
                raise ValidationException("Direct mode requires at least one HA device")
            if camera_ids:
                raise ValidationException("Direct mode does not support camera_ids")
            if not trigger_rule.targets.trigger_entity_id:
                raise ValidationException("Direct mode requires trigger_entity_id")
            if not trigger_rule.trigger.ha_condition:
                raise ValidationException("Direct mode requires ha_condition")

        if condition_type == ConditionType.HYBRID:
            if not camera_ids or not ha_device_ids:
                raise ValidationException("Hybrid mode requires both camera_ids and ha_device_ids")
            if not trigger_rule.trigger.ha_condition:
                raise ValidationException("Hybrid mode requires ha_condition")
            if not (trigger_rule.trigger.camera_condition or trigger_rule.trigger.llm_condition):
                raise ValidationException("Hybrid mode requires camera condition")

        if condition_type in (ConditionType.DETECTION, ConditionType.FACE_RECOGNITION):
            if not camera_ids:
                raise ValidationException("Detection mode requires at least one camera")

            is_valid, error_msg = self.validate_detection_condition(trigger_rule.trigger.detection_condition)
            if not is_valid:
                raise ValidationException(error_msg or "Invalid detection condition")

        trigger_entity_id = trigger_rule.targets.trigger_entity_id
        if trigger_entity_id and ha_device_ids:
            valid_entities = set()
            for did in ha_device_ids:
                valid_entities.update(ha_devices_grouped.get(did, {}).get("entities", []))
            if trigger_entity_id not in valid_entities:
                raise ValidationException(f"Invalid trigger_entity_id '{trigger_entity_id}' for selected HA devices")

    async def get_trigger_rule_logs(self, limit: int = 10) -> tuple[List[TriggerRuleLog], int]:
        """
        Get trigger rule execution logs

        Args:
            limit: Number of logs to retrieve

        Returns:
            tuple[List[TriggerRuleLog], int]: Log list and total count
        """
        logger.info("Getting trigger rule logs: limit=%d", limit)

        rule_logs = self._trigger_rule_log_dao.get_all(limit=limit)
        total_items = self._trigger_rule_log_dao.count_all()

        logger.info("Retrieved %d trigger rule logs", len(rule_logs))
        return rule_logs, total_items

    async def _check_notify(self, notify: Optional[Notify]):
        """Check notification content for filtering"""
        if not notify:
            return

        if not notify.content:
            raise ValidationException("Notification content is required")

        notify_id = await self._miot_proxy.get_miot_app_notify_id(notify.content)
        if not notify_id:
            raise ValidationException("Notification content is inappropriate, please re-enter")
        notify.id = notify_id

    async def send_dynamic_execute_log(self, log_id: str, websocket: WebSocket) -> None:
        """Send dynamic execute log"""
        execute_result, rule_id = self._trigger_rule_log_dao.get_execute_result(log_id)
        if (execute_result and
            execute_result.ai_recommend_dynamic_execute_result and
            execute_result.ai_recommend_dynamic_execute_result.chat_history_session):
            for session in execute_result.ai_recommend_dynamic_execute_result.chat_history_session.data:
                await websocket.send_text(session.model_dump_json())
        elif rule_id:
            trigger_rule_dynamic_executor = trigger_rule_dynamic_executor_cache.get(rule_id)
            if trigger_rule_dynamic_executor:
                register_web_socket = RegisterWebSocket(websocket)
                actor_system.tell(trigger_rule_dynamic_executor, register_web_socket)
                return
            else:
                raise ResourceNotFoundException(
                    f"Trigger rule dynamic executor not found for log ID: {log_id}")
        else:
            raise ResourceNotFoundException(
                f"Trigger rule log not found for log ID: {log_id}")

    async def execute_actions(self, actions: list[Action]) -> list[bool]:
        """Execute actions"""
        results: list[bool] = []
        for action in actions:
            result: bool = await self._trigger_rule_runner.execute_action(action)
            results.append(result)
        return results
