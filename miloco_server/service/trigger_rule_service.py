# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Trigger rule service module
"""

import logging
from typing import List, Optional, Any

from fastapi import WebSocket
from miot.types import MIoTCameraInfo
from schema.mcp_schema import MCPClientStatus, choose_mcp_list

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
    Action, ExecuteInfoDetail, Notify, TriggerRule, TriggerRuleDetail, TriggerRuleV2, ConditionType)
from miloco_server.service.trigger_rule_runner import TriggerRuleRunner
from miloco_server.service.ha_service import HaService
from miloco_server.service.trigger_rule_service_detection import DetectionTriggerServiceMixin

from service import trigger_rule_dynamic_executor_cache
from service.trigger_rule_dynamic_executor import RegisterWebSocket

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

            # 获取所有启用的规则
            all_rules = self._trigger_rule_dao.get_all(enabled_only=True)
            logger.info(f"[Startup] Found {len(all_rules)} enabled rules")

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

    async def create_trigger_rule(self, trigger_rule: TriggerRule) -> str:
        """
        Create trigger rule

        Args:
            trigger_rule: Trigger rule object (without ID, system auto-generates on creation)

        Returns:
            str: Created rule ID

        Raises:
            ConflictException: When rule name already exists
            ValidationException: When camera device ID is invalid
            BusinessException: When creation fails
        """
        # Check if rule name already exists
        if self._trigger_rule_dao.exists_by_name(trigger_rule.name):
            raise ConflictException(f"Trigger rule name '{trigger_rule.name}' already exists")

        # Validate if camera device IDs are valid
        valid_cameras = await self._miot_proxy.get_camera_dids()
        invalid_dids = [
            did for did in trigger_rule.cameras if did not in valid_cameras
        ]
        if invalid_dids:
            ids = ", ".join(invalid_dids)
            raise ValidationException(f"Invalid camera device IDs: {ids}")

        # Validate HA devices if ha_service is available
        if trigger_rule.ha_devices and self._ha_service:
            ha_devices_grouped = await self._ha_service.get_ha_devices_grouped()
            valid_ha_dids = set(ha_devices_grouped.keys())
            # ha_devices is already a list of device ID strings
            invalid_ha_dids = [did for did in trigger_rule.ha_devices if did not in valid_ha_dids]
            if invalid_ha_dids:
                ids = ", ".join(invalid_ha_dids)
                raise ValidationException(f"Invalid HA device IDs: {ids}")

            if trigger_rule.trigger_entity_id:
                valid_entities = set()
                for did in trigger_rule.ha_devices:
                    valid_entities.update(ha_devices_grouped.get(did, {}).get("entities", []))
                if trigger_rule.trigger_entity_id not in valid_entities:
                    raise ValidationException(
                        f"Invalid trigger_entity_id '{trigger_rule.trigger_entity_id}' for selected HA devices"
                    )

        # Validate notification for content filtering
        if trigger_rule.execute_info and trigger_rule.execute_info.notify:
            await self._check_notify(trigger_rule.execute_info.notify)

        # Create rule object
        rule_id = self._trigger_rule_dao.create(trigger_rule)

        if not rule_id:
            logger.error("Trigger rule creation failed")
            raise BusinessException("Failed to create trigger rule")

        trigger_rule.id = rule_id
        self._trigger_rule_runner.add_trigger_rule(trigger_rule)

        logger.info(f"[CreateRule] Rule {rule_id} created, condition_type={trigger_rule.condition_type}, "
                   f"has_detection_condition={trigger_rule.detection_condition is not None}")

        # Handle detection condition if present
        if trigger_rule.detection_condition:
            logger.info(f"[CreateRule] Detection condition found: enabled={trigger_rule.detection_condition.enabled}, "
                       f"targets={trigger_rule.detection_condition.targets}")
            if trigger_rule.detection_condition.enabled:
                logger.info(f"[CreateRule] Calling _handle_detection_condition_on_create for rule {rule_id}")
                try:
                    detection_result = await self._handle_detection_condition_on_create(trigger_rule)
                    logger.info(f"[CreateRule] Detection result for rule {rule_id}: {detection_result}")
                    if detection_result.get("errors"):
                        logger.warning(f"[CreateRule] Detection condition errors: {detection_result['errors']}")
                except Exception as e:
                    logger.error(f"[CreateRule] Error handling detection condition: {e}", exc_info=True)
            else:
                logger.info(f"[CreateRule] Detection condition disabled for rule {rule_id}")
        else:
            logger.info(f"[CreateRule] No detection condition for rule {rule_id}")

        logger.info("Trigger rule created successfully: %s", rule_id)
        return rule_id

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
        self._trigger_rule_runner.add_trigger_rule(trigger_rule.to_runtime_rule())
        return rule_id

    async def get_trigger_rule(self, rule_id: str) -> TriggerRuleDetail:
        """
        Get trigger rule details

        Args:
            rule_id: Rule ID (UUID)

        Returns:
            TriggerRule: Trigger rule object

        Raises:
            ResourceNotFoundException: When rule does not exist
        """
        logger.info("Getting trigger rule details: id=%s", rule_id)

        trigger_rule = self._trigger_rule_dao.get_by_id(rule_id)

        if not trigger_rule:
            raise ResourceNotFoundException(f"Trigger rule with ID '{rule_id}' not found")

        trigger_rule_response = await self.make_trigger_rule_detail(trigger_rule)

        logger.info("Trigger rule retrieved successfully: %s", rule_id)
        return trigger_rule_response

    async def get_all_trigger_rules(self, enabled_only: bool = False) -> List[TriggerRuleDetail]:
        """
        Get all trigger rules

        Args:
            enabled_only: Whether to return only enabled rules

        Returns:
            List[TriggerRuleDetail]: List of trigger rule objects
        """
        logger.info("Getting all trigger rules: enabled_only=%s", enabled_only)

        trigger_rules: List[TriggerRule] = self._trigger_rule_dao.get_all(
            enabled_only)

        if not trigger_rules:
            return []

        trigger_rule_responses = await self.make_trigger_rule_details(trigger_rules)

        logger.info("Retrieved %d trigger rules", len(trigger_rule_responses))
        return trigger_rule_responses

    async def get_all_trigger_rules_v2(self, enabled_only: bool = False) -> List[TriggerRuleV2]:
        """Get all v2 trigger rules."""
        return self._trigger_rule_dao.get_all_v2(enabled_only)

    async def update_trigger_rule(self, trigger_rule: TriggerRule) -> bool:
        """
        Update trigger rule

        Args:
            trigger_rule: Trigger rule object (with ID)

        Returns:
            bool: True if update successful, False otherwise

        Raises:
            ResourceNotFoundException: When rule does not exist
            ConflictException: When rule name already exists
            ValidationException: When camera device ID is invalid
        """
        logger.info("Updating trigger rule: id=%s", trigger_rule.id)
        if not trigger_rule.id:
            raise ValidationException("Rule ID is required")

        # Check if rule exists
        if not self._trigger_rule_dao.exists(trigger_rule.id):
            raise ResourceNotFoundException(f"Trigger rule with ID '{trigger_rule.id}' not found")

        # Check if rule name already exists (excluding current rule)
        if self._trigger_rule_dao.exists_by_name(trigger_rule.name, trigger_rule.id):
            raise ConflictException(f"Trigger rule name '{trigger_rule.name}' already exists")

        # Validate if camera device IDs are valid
        valid_cameras = await self._miot_proxy.get_camera_dids()
        invalid_dids = [
            did for did in trigger_rule.cameras if did not in valid_cameras
        ]
        if invalid_dids:
            ids = ", ".join(invalid_dids)
            raise ValidationException(f"Invalid camera device IDs: {ids}")

        # Validate HA devices if ha_service is available
        if trigger_rule.ha_devices and self._ha_service:
            ha_devices_grouped = await self._ha_service.get_ha_devices_grouped()
            valid_ha_dids = set(ha_devices_grouped.keys())
            # ha_devices is already a list of device ID strings
            invalid_ha_dids = [did for did in trigger_rule.ha_devices if did not in valid_ha_dids]
            if invalid_ha_dids:
                ids = ", ".join(invalid_ha_dids)
                raise ValidationException(f"Invalid HA device IDs: {ids}")

            if trigger_rule.trigger_entity_id:
                valid_entities = set()
                for did in trigger_rule.ha_devices:
                    valid_entities.update(ha_devices_grouped.get(did, {}).get("entities", []))
                if trigger_rule.trigger_entity_id not in valid_entities:
                    raise ValidationException(
                        f"Invalid trigger_entity_id '{trigger_rule.trigger_entity_id}' for selected HA devices"
                    )

        # Validate notification for content filtering
        if trigger_rule.execute_info and trigger_rule.execute_info.notify:
            await self._check_notify(trigger_rule.execute_info.notify)

        # Get old rule for detection condition comparison
        old_rule = self._trigger_rule_dao.get_by_id(trigger_rule.id)

        success = self._trigger_rule_dao.update(trigger_rule)

        if success:
            self._trigger_rule_runner.add_trigger_rule(trigger_rule)

            # Handle detection condition changes
            try:
                detection_result = await self._handle_detection_condition_on_update(
                    trigger_rule, old_rule
                )
                if detection_result.get("detection_updated"):
                    logger.info(
                        f"Detection condition updated for rule {trigger_rule.id}: "
                        f"action={detection_result.get('action')}, "
                        f"cameras={detection_result.get('cameras_affected', [])}"
                    )
                if detection_result.get("errors"):
                    logger.warning(
                        f"Detection condition errors for rule {trigger_rule.id}: "
                        f"{detection_result['errors']}"
                    )
            except Exception as e:
                logger.error(f"Error handling detection condition update for rule {trigger_rule.id}: {e}")

            logger.info("Trigger rule updated successfully: %s", trigger_rule.id)
        else:
            logger.error("Failed to update trigger rule: %s", trigger_rule.id)

        return success

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

        success = self._trigger_rule_dao.update_v2(trigger_rule)
        if success:
            self._trigger_rule_runner.add_trigger_rule(trigger_rule.to_runtime_rule())
        return success

    async def delete_trigger_rule(self, rule_id: str) -> bool:
        """
        Delete trigger rule

        Args:
            rule_id: Rule ID (UUID)

        Returns:
            bool: True if deletion successful, False otherwise

        Raises:
            ResourceNotFoundException: When rule does not exist
            BusinessException: When deletion fails
        """
        logger.info("Deleting trigger rule: id=%s", rule_id)

        # Check if rule exists
        if not self._trigger_rule_dao.exists(rule_id):
            raise ResourceNotFoundException(f"Trigger rule with ID '{rule_id}' not found")

        # Delete rule
        success = self._trigger_rule_dao.delete(rule_id)

        if success:
            self._trigger_rule_runner.remove_trigger_rule(rule_id)
            logger.info("Trigger rule deleted successfully: %s", rule_id)
        else:
            logger.error("Failed to delete trigger rule: %s", rule_id)

        return success

    async def delete_trigger_rule_v2(self, rule_id: str) -> bool:
        """Delete trigger rule from v2 table."""
        if not self._trigger_rule_dao.exists_v2(rule_id):
            raise ResourceNotFoundException(f"Trigger rule with ID '{rule_id}' not found")
        success = self._trigger_rule_dao.delete_v2(rule_id)
        if success:
            self._trigger_rule_runner.remove_trigger_rule(rule_id)
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


    async def make_trigger_rule_details(
            self, trigger_rules: List[TriggerRule]) -> List[TriggerRuleDetail]:
        """Generate trigger rule response"""
        camera_info_dict = await self._miot_proxy.get_cameras()
        ha_devices_grouped = await self._ha_service.get_ha_devices_grouped() if self._ha_service else {}
        all_mcp_list = await self._mcp_client_manager.get_all_clients_status()
        return [
            self._build_trigger_rule_detail(trigger_rule, camera_info_dict, ha_devices_grouped, all_mcp_list)
            for trigger_rule in trigger_rules
        ]


    async def make_trigger_rule_detail(self, trigger_rule: TriggerRule) -> TriggerRuleDetail:
        """Generate trigger rule response"""
        camera_info_dict = await self._miot_proxy.get_cameras()
        ha_devices_grouped = await self._ha_service.get_ha_devices_grouped() if self._ha_service else {}
        all_mcp_list = await self._mcp_client_manager.get_all_clients_status()
        return self._build_trigger_rule_detail(trigger_rule, camera_info_dict, ha_devices_grouped, all_mcp_list)

    def _build_trigger_rule_detail(
        self,
        trigger_rule: TriggerRule,
        camera_info_dict: dict[str, MIoTCameraInfo],
        ha_devices_grouped: dict[str, dict[str, Any]],
        all_mcp_list: List[MCPClientStatus],
    ) -> TriggerRuleDetail:
        """Generate trigger rule response"""
        camera_list = choose_camera_list(trigger_rule.cameras, camera_info_dict)

        ha_device_list = []
        for did in trigger_rule.ha_devices:
            if did in ha_devices_grouped:
                info = ha_devices_grouped[did]
                ha_device_list.append(HADeviceInfo(
                    did=did,
                    name=info["name"],
                    online=True,
                    model="ha_device",
                    entity_id=info["entities"][0] if info["entities"] else did,
                    state="online",
                    room_name=info["area"]
                ))

        choosed_mcp_list = choose_mcp_list(trigger_rule.execute_info.mcp_list, all_mcp_list)
        execute_info = ExecuteInfoDetail.from_execute_info(
            trigger_rule.execute_info, choosed_mcp_list)
        return TriggerRuleDetail.from_trigger_rule(
            trigger_rule=trigger_rule,
            cameras=camera_list,
            ha_devices=ha_device_list,
            execute_info=execute_info)

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
