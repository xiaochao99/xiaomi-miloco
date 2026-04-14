# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Trigger Rule Service Extension for Detection Conditions
处理目标检测触发条件的业务逻辑
"""

import logging
from typing import Optional, Dict, Any, List

from miloco_server.schema.trigger_schema import TriggerRule, DetectionCondition
from miloco_server.detection.detection_service import get_detection_service

logger = logging.getLogger(__name__)


class DetectionTriggerServiceMixin:
    """
    Mixin类用于扩展TriggerRuleService的检测功能
    处理与目标检测相关的业务逻辑
    """

    async def _handle_detection_condition_on_create(
        self,
        trigger_rule: TriggerRule
    ) -> Dict[str, Any]:
        """
        创建规则时处理检测条件

        Args:
            trigger_rule: 新创建的规则

        Returns:
            处理结果信息
        """
        result = {
            "detection_enabled": False,
            "cameras_started": [],
            "errors": []
        }

        if not trigger_rule.detection_condition:
            return result

        condition = trigger_rule.detection_condition
        if not condition.enabled:
            return result

        logger.info(f"[Detection] Rule {trigger_rule.id}: Starting detection for targets={condition.targets}, logic={condition.logic}")

        # 验证摄像头配置
        if not trigger_rule.cameras:
            result["errors"].append("Detection condition requires at least one camera")
            logger.warning(f"[Detection] Rule {trigger_rule.id}: No cameras configured")
            return result

        # 验证目标类型
        if not condition.targets:
            result["errors"].append("Detection condition requires at least one target type")
            logger.warning(f"[Detection] Rule {trigger_rule.id}: No target types specified")
            return result

        # 启动检测服务
        try:
            detection_service = await get_detection_service()

            if not detection_service.is_running():
                logger.info("[Detection] Initializing detection service...")
                success = await detection_service.initialize()
                if not success:
                    result["errors"].append("Failed to initialize detection service")
                    logger.error("[Detection] Failed to initialize detection service")
                    return result
                logger.info("[Detection] Detection service initialized successfully")
            
            # 为每个摄像头启动检测
            logger.info(f"[Detection] Starting detection for cameras: {trigger_rule.cameras}")
            for camera_id in trigger_rule.cameras:
                try:
                    # 获取摄像头处理器
                    camera_handler = await self._get_camera_handler(camera_id)
                    if not camera_handler:
                        result["errors"].append(f"Camera {camera_id} not found or not streaming")
                        logger.warning(f"[Detection] Camera handler not found for {camera_id}")
                        continue

                    # 检查摄像头是否在线且已连接
                    camera_info = await self._get_camera_info(camera_id)
                    if camera_info:
                        from miot.types import MIoTCameraStatus
                        if not camera_info.online or camera_info.camera_status != MIoTCameraStatus.CONNECTED:
                            result["errors"].append(f"Camera {camera_id} is not online/connected")
                            logger.warning(f"[Detection] Camera {camera_id} is not ready, skipping detection")
                            continue

                    # 检查是否已在检测中
                    active_cameras = detection_service.get_active_cameras()
                    if camera_id in active_cameras:
                        logger.info(
                            f"[Detection] Camera {camera_id} already active, "
                            f"will request face enable/upgrade if needed"
                        )

                    # 启动检测
                    enable_face_recognition = any(
                        t.value in ("face", "face_recognition") for t in condition.targets
                    )
                    config_override = {
                        "confidence_threshold": condition.confidence_threshold,
                        "process_fps": self._calculate_optimal_fps(
                            condition.sensitivity, enable_face_recognition
                        ),
                        "enable_face_recognition": enable_face_recognition,
                    }

                    success = await detection_service.start_detection(
                        camera_id=camera_id,
                        camera_handler=camera_handler,
                        config_override=config_override
                    )

                    if success:
                        result["cameras_started"].append(camera_id)
                        logger.info(f"[Detection] Successfully started detection for camera {camera_id}")
                    else:
                        result["errors"].append(f"Failed to start detection for camera {camera_id}")
                        logger.error(f"[Detection] Failed to start detection for camera {camera_id}")

                except Exception as e:
                    logger.error(f"[Detection] Error starting detection for camera {camera_id}: {e}")
                    result["errors"].append(f"Camera {camera_id}: {str(e)}")

            result["detection_enabled"] = len(result["cameras_started"]) > 0
            
        except Exception as e:
            logger.error(f"Error handling detection condition on create: {e}")
            result["errors"].append(f"Detection service error: {str(e)}")
            
        return result

    async def _handle_detection_condition_on_update(
        self,
        trigger_rule: TriggerRule,
        old_rule: Optional[TriggerRule] = None
    ) -> Dict[str, Any]:
        """
        更新规则时处理检测条件

        Args:
            trigger_rule: 更新后的规则
            old_rule: 原始规则（可选）

        Returns:
            处理结果信息
        """
        result = {
            "detection_updated": False,
            "cameras_affected": [],
            "errors": []
        }

        new_condition = trigger_rule.detection_condition
        old_condition = old_rule.detection_condition if old_rule else None

        # 规则被禁用（整体开关关闭）
        if old_rule and old_rule.enabled and not trigger_rule.enabled:
            # 如果检测条件原来是启用的，停止检测
            if old_condition and old_condition.enabled:
                await self._stop_detection_if_unused(trigger_rule.cameras, trigger_rule.id)
                result["detection_updated"] = True
                result["action"] = "rule_disabled"
                logger.info(f"Rule {trigger_rule.id} disabled, stopping detection for cameras: {trigger_rule.cameras}")
            return result

        # 规则被启用（整体开关打开）
        if old_rule and not old_rule.enabled and trigger_rule.enabled:
            # 如果检测条件是启用的，启动检测
            if new_condition and new_condition.enabled:
                create_result = await self._handle_detection_condition_on_create(trigger_rule)
                result.update(create_result)
                result["detection_updated"] = True
                result["action"] = "rule_enabled"
                logger.info(f"Rule {trigger_rule.id} enabled, starting detection for cameras: {trigger_rule.cameras}")
            return result

        # 检测条件没有变化
        if self._conditions_equal(new_condition, old_condition):
            return result

        # 检测条件被禁用
        if old_condition and old_condition.enabled and (not new_condition or not new_condition.enabled):
            # 停止检测（如果没有其他规则使用）
            await self._stop_detection_if_unused(trigger_rule.cameras, trigger_rule.id)
            result["detection_updated"] = True
            result["action"] = "disabled"
            return result

        # 检测条件被启用
        if new_condition and new_condition.enabled and (not old_condition or not old_condition.enabled):
            create_result = await self._handle_detection_condition_on_create(trigger_rule)
            result.update(create_result)
            result["detection_updated"] = True
            result["action"] = "enabled"
            return result

        # 检测配置变更
        if new_condition and new_condition.enabled and old_condition and old_condition.enabled:
            # 检查检测服务是否正在运行
            from miloco_server.detection.detection_service import get_detection_service
            detection_service = await get_detection_service()

            old_has_face = any(t.value in ("face", "face_recognition") for t in old_condition.targets)
            new_has_face = any(t.value in ("face", "face_recognition") for t in new_condition.targets)
            face_flag_changed = old_has_face != new_has_face

            active_cameras = detection_service.get_active_cameras()
            cameras_to_start = [cid for cid in trigger_rule.cameras if cid not in active_cameras]

            if cameras_to_start:
                # 有摄像头检测未启动，需要启动检测
                logger.info(f"[Detection] Restarting detection for cameras: {cameras_to_start}")
                create_result = await self._handle_detection_condition_on_create(trigger_rule)
                result.update(create_result)
                result["detection_updated"] = True
                result["action"] = "restarted"
            else:
                if face_flag_changed:
                    # face 目标开关影响检测器是否需要启用 face 分支
                    logger.info(
                        "[Detection] Face flag changed, requesting detection re-init for cameras: %s",
                        trigger_rule.cameras,
                    )
                    create_result = await self._handle_detection_condition_on_create(trigger_rule)
                    result.update(create_result)
                    result["detection_updated"] = True
                    result["action"] = "restarted_face"
                else:
                    # 更新检测配置（仅 YOLO 相关参数）
                    result["detection_updated"] = True
                    result["action"] = "updated"
                    await self._update_detection_config(trigger_rule)

        return result

    async def _handle_detection_condition_on_delete(
        self,
        trigger_rule: TriggerRule
    ) -> Dict[str, Any]:
        """
        删除规则时处理检测条件
        
        Args:
            trigger_rule: 被删除的规则
            
        Returns:
            处理结果信息
        """
        result = {
            "detection_stopped": False,
            "cameras_affected": []
        }
        
        if not trigger_rule.detection_condition or not trigger_rule.detection_condition.enabled:
            return result
            
        # 停止检测（如果没有其他规则使用）
        await self._stop_detection_if_unused(trigger_rule.cameras, trigger_rule.id)
        result["detection_stopped"] = True
        
        return result

    def _conditions_equal(
        self,
        cond1: Optional[DetectionCondition],
        cond2: Optional[DetectionCondition]
    ) -> bool:
        """比较两个检测条件是否相等"""
        if cond1 is None and cond2 is None:
            return True
        if cond1 is None or cond2 is None:
            return False
            
        return (
            cond1.enabled == cond2.enabled and
            cond1.targets == cond2.targets and
            cond1.logic == cond2.logic and
            cond1.min_count == cond2.min_count and
            abs(cond1.confidence_threshold - cond2.confidence_threshold) < 0.001 and
            cond1.sensitivity == cond2.sensitivity and
            cond1.cooldown_seconds == cond2.cooldown_seconds and
            cond1.min_duration_seconds == cond2.min_duration_seconds
        )

    def _get_condition_changes(
        self,
        old_condition: DetectionCondition,
        new_condition: DetectionCondition
    ) -> List[str]:
        """获取检测条件的变更项"""
        changes = []
        
        if old_condition.targets != new_condition.targets:
            changes.append("targets")
        if old_condition.logic != new_condition.logic:
            changes.append("logic")
        if old_condition.min_count != new_condition.min_count:
            changes.append("min_count")
        if abs(old_condition.confidence_threshold - new_condition.confidence_threshold) > 0.001:
            changes.append("confidence_threshold")
        if old_condition.sensitivity != new_condition.sensitivity:
            changes.append("sensitivity")
        if old_condition.cooldown_seconds != new_condition.cooldown_seconds:
            changes.append("cooldown_seconds")
        if old_condition.min_duration_seconds != new_condition.min_duration_seconds:
            changes.append("min_duration_seconds")
            
        return changes

    async def _stop_detection_if_unused(
        self,
        camera_ids: List[str],
        exclude_rule_id: str
    ):
        """
        如果没有其他规则使用，停止摄像头检测
        
        Args:
            camera_ids: 摄像头ID列表
            exclude_rule_id: 排除的规则ID（正在删除的规则）
        """
        try:
            from miloco_server.dao.trigger_dao import TriggerRuleDAO
            dao = TriggerRuleDAO()
            
            detection_service = await get_detection_service()
            
            for camera_id in camera_ids:
                # 检查是否有其他规则在使用这个摄像头的检测
                other_rules_v2 = dao.get_rules_by_camera_with_detection_v2(camera_id, exclude_rule_id)
                
                if not other_rules_v2:
                    # 没有其他规则使用，停止检测
                    await detection_service.stop_detection(camera_id)
                    logger.info(f"Stopped detection for camera {camera_id} (no more rules)")
                    
        except Exception as e:
            logger.error(f"Error stopping detection on delete: {e}")

    async def _update_detection_config(self, trigger_rule: TriggerRule):
        """更新检测配置"""
        if not trigger_rule.detection_condition:
            return

        condition = trigger_rule.detection_condition
        detection_service = await get_detection_service()

        for camera_id in trigger_rule.cameras:
            config = {
                "confidence_threshold": condition.confidence_threshold,
                "process_fps": self._calculate_optimal_fps(
                    condition.sensitivity,
                    any(t.value in ("face", "face_recognition") for t in condition.targets),
                ),
                "enable_face_recognition": any(t.value in ("face", "face_recognition") for t in condition.targets),
            }
            detection_service.update_config(camera_id, config)

    def _calculate_optimal_fps(
        self,
        sensitivity: int,
        enable_face_recognition: bool,
    ) -> float:
        """
        根据灵敏度计算最优FPS
        
        Args:
            sensitivity: 灵敏度 1-10
            
        Returns:
            推荐的FPS值
        """
        # 灵敏度越高，FPS越高。
        # face 识别通常更耗 CPU，所以给更保守的上限，避免抢占系统资源。
        base_fps = 2 + (sensitivity - 1) * 0.9
        if not enable_face_recognition:
            return base_fps

        # 保守上限：1.5~3.0 FPS
        capped = 1.5 + (sensitivity - 1) * 0.15
        return float(min(base_fps, capped))

    async def _get_camera_handler(self, camera_id: str):
        """
        获取摄像头处理器

        Args:
            camera_id: 摄像头ID

        Returns:
            摄像头处理器或None
        """
        try:
            from miloco_server.service.manager import get_manager
            manager = get_manager()
            miot_proxy = manager.miot_proxy

            if hasattr(miot_proxy, '_camera_img_managers'):
                return miot_proxy._camera_img_managers.get(camera_id)
        except Exception as e:
            logger.error(f"Error getting camera handler for {camera_id}: {e}")

        return None

    async def _get_camera_info(self, camera_id: str):
        """
        获取摄像头信息

        Args:
            camera_id: 摄像头ID

        Returns:
            摄像头信息或None
        """
        try:
            from miloco_server.service.manager import get_manager
            manager = get_manager()
            cameras = await manager.miot_proxy.get_cameras()
            return cameras.get(camera_id)
        except Exception as e:
            logger.error(f"[_get_camera_info] Error getting camera info for {camera_id}: {e}")
            return None

    def validate_detection_condition(
        self,
        condition: Optional[DetectionCondition]
    ) -> tuple[bool, Optional[str]]:
        """
        验证检测条件配置

        Args:
            condition: 检测条件

        Returns:
            (是否有效, 错误信息)
        """
        if not condition:
            return True, None

        if not condition.enabled:
            return True, None

        # 验证目标类型
        if not condition.targets:
            return False, "At least one target type must be selected"

        # 验证人脸识别目标及相关参数
        has_face_recognition = "face_recognition" in [t.value for t in condition.targets]
        if has_face_recognition:
            if not condition.face_target:
                return False, "Face recognition target must be specified"

            # 验证人脸识别专用参数
            if not 0.0 <= condition.min_face_score <= 1.0:
                return False, "Min face score must be between 0.0 and 1.0"

            if not 1 <= condition.max_faces <= 32:
                return False, "Max faces must be between 1 and 32"

        # 验证置信度阈值（仅非人脸识别模式）
        if not has_face_recognition:
            if not 0.0 <= condition.confidence_threshold <= 1.0:
                return False, "Confidence threshold must be between 0.0 and 1.0"

            # 验证灵敏度（仅非人脸识别模式）
            if not 1 <= condition.sensitivity <= 10:
                return False, "Sensitivity must be between 1 and 10"

            # 验证COUNT逻辑（仅非人脸识别模式）
            if condition.logic.value == "count":
                if condition.min_count is None or condition.min_count < 1:
                    return False, "Min count must be at least 1 for COUNT logic"

            # 验证最小持续时长（仅非人脸识别模式）
            if condition.min_duration_seconds is not None:
                if not 1 <= condition.min_duration_seconds <= 300:
                    return False, "Min duration must be between 1 and 300 seconds"

        # 验证冷却时间（通用）
        if not 5 <= condition.cooldown_seconds <= 3600:
            return False, "Cooldown must be between 5 and 3600 seconds"

        return True, None
