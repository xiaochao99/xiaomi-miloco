# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Trigger data models
Define trigger-related data structures
"""
from enum import Enum
from typing import Optional, List, Any, TYPE_CHECKING

from pydantic import BaseModel, Field

from miloco_server.schema.mcp_schema import MCPClientStatus
from miloco_server.schema.miot_schema import CameraInfo, HADeviceInfo
from miloco_server.schema.wakeup_schema import WakeUpConfig

if TYPE_CHECKING:
    pass


class Action(BaseModel):
    """Action data model"""
    mcp_client_id: str = Field(..., description="MCP client ID")
    mcp_tool_name: str = Field(..., description="MCP tool name")
    mcp_tool_input: dict = Field(..., description="MCP tool input")
    mcp_server_name: str = Field(..., description="MCP service name")
    introduction: str = Field(..., description="Introduction, used for user to understand the action introduction")


class ExecuteType(Enum):
    """Execute type enumeration"""
    STATIC = "static" # LLM generated static action, direct action
    DYNAMIC = "dynamic" # action description, use LLM dynamic action


class ConditionType(Enum):
    """Condition check type enumeration"""
    LLM = "llm" # Use LLM to check condition (natural language)
    DIRECT = "direct" # Use direct state matching (no LLM, zero token cost)
    HYBRID = "hybrid" # Hybrid: First use direct mode for HA devices, if matched then use LLM to analyze camera
    DETECTION = "detection" # Use object detection (YOLO) for trigger condition
    FACE_RECOGNITION = "face_recognition" # Use face recognition for trigger condition


class Notify(BaseModel):
    """Notification data model"""
    id: Optional[str] = Field(None, description="Notification ID")
    content: str = Field(..., description="Notification content")


class XiaoAIBroadcastMode(str, Enum):
    """XiaoAI broadcast mode"""
    TEXT = "text"
    MODEL_REPLY = "model_reply"


class XiaoAIBroadcast(BaseModel):
    """XiaoAI broadcast action"""
    mode: XiaoAIBroadcastMode = Field(
        XiaoAIBroadcastMode.TEXT, description="Broadcast mode: text or model_reply"
    )
    text: Optional[str] = Field(
        None, description="Text to play when mode=text"
    )
    device_ids: Optional[List[str]] = Field(
        None, description="List of device IDs to broadcast to. If None, broadcasts to all connected devices."
    )


class ExecuteInfo(BaseModel):
    """Execute info"""
    ai_recommend_execute_type: ExecuteType = Field(
        ExecuteType.STATIC, description="AI recommend execute type")
    ai_recommend_action_descriptions: Optional[list[str]] = Field(
        None, description="Action descriptions")
    ai_recommend_actions: Optional[list[Action]] = Field(
        None, description="Actions to execute")
    automation_actions: Optional[list[Action]] = Field(
        None, description="MIoT or Home Assistant automation actions to execute")
    mcp_list: Optional[list[str]] = Field(None, description="MCP list")
    notify: Optional[Notify] = Field(None, description="Mi Home send notification")
    xiaoai_broadcast: Optional[XiaoAIBroadcast] = Field(
        None, description="XiaoAI speaker broadcast action"
    )
    xiaoai_wakeup: Optional[WakeUpConfig] = Field(
        None, description="Wake up XiaoAI configuration"
    )

class ExecuteInfoDetail(ExecuteInfo):
    """Execute info detail"""
    mcp_list: Optional[list[MCPClientStatus]] = Field(None, description="MCP list")

    @classmethod
    def from_execute_info(
            cls, execute_info: ExecuteInfo,
            mcp_list: Optional[list[MCPClientStatus]]) -> "ExecuteInfoDetail":
        execute_info_data = execute_info.model_dump(exclude={"mcp_list"})
        if mcp_list:
            execute_info_data["mcp_list"] = [mcp.model_dump() for mcp in mcp_list]
        return cls.model_validate(execute_info_data)

    @classmethod
    def to_execute_info(cls, instance) -> ExecuteInfo:
        execute_info_data = instance.model_dump(exclude={"mcp_list"})
        mcp_list = [client.client_id for client in instance.mcp_list] if instance.mcp_list else None
        return ExecuteInfo(**execute_info_data, mcp_list=mcp_list)


class TriggerFrequencyFilter(BaseModel):
    """Trigger frequency filter data model"""
    frequency: int = Field(..., description="Trigger frequency/times", le=50)
    period: int = Field(..., description="Trigger period/seconds")


class TriggerFilter(BaseModel):
    """Trigger filter data model"""
    period: Optional[str] = Field(None, description="Trigger time period filter, cron expression")
    interval: Optional[int] = Field(None, description="Trigger interval filter/seconds")
    frequency: Optional[TriggerFrequencyFilter] = Field(None, description="Trigger frequency filter")


class DetectionTargetType(str, Enum):
    """Detection target types"""
    PERSON = "person"
    CAT = "cat"
    DOG = "dog"
    # NOTE: keep FACE for backward compatibility (old rules) but prefer FACE_RECOGNITION.
    FACE = "face"
    FACE_RECOGNITION = "face_recognition"


class DetectionLogicType(str, Enum):
    """Detection logic types for multiple targets"""
    ANY = "any"      # Any target detected triggers
    ALL = "all"      # All specified targets must be detected
    COUNT = "count"  # Minimum count of targets


class DetectionCondition(BaseModel):
    """Detection condition configuration"""
    enabled: bool = Field(False, description="Enable detection-based trigger")
    targets: List[DetectionTargetType] = Field(
        default_factory=list,
        description="Target types to detect: person, cat, dog, face"
    )
    logic: DetectionLogicType = Field(
        DetectionLogicType.ANY,
        description="Logic for multiple targets: any, all, count"
    )
    min_count: Optional[int] = Field(
        None,
        description="Minimum target count for COUNT logic",
        ge=1, le=10
    )
    confidence_threshold: float = Field(
        0.5,
        description="Detection confidence threshold (0.0-1.0)",
        ge=0.0, le=1.0
    )
    sensitivity: int = Field(
        5,
        description="Trigger sensitivity 1-10, higher = more sensitive",
        ge=1, le=10
    )
    cooldown_seconds: int = Field(
        30,
        description="Cooldown period between triggers (seconds)",
        ge=5, le=3600
    )
    min_duration_seconds: Optional[int] = Field(
        None,
        description="Minimum duration target must be present (seconds)",
        ge=1, le=300
    )
    # Face recognition specific fields
    face_target: Optional[str] = Field(
        None,
        description="Target face name for face recognition mode. Use 'unknown' for unknown faces."
    )
    min_face_score: float = Field(
        0.1,
        description="Minimum face detection confidence score (0.0-1.0), used for face recognition mode",
        ge=0.0, le=1.0
    )
    max_faces: int = Field(
        10,
        description="Maximum number of faces to detect, used for face recognition mode",
        ge=1, le=32
    )


class TriggerRule(BaseModel):
    """Trigger rule data model - supports create/update and query operations"""
    id: Optional[str] = Field(None, description="Rule ID (UUID format)")
    enabled: bool = Field(True, description="Whether enabled")
    name: str = Field(..., description="Rule name")
    cameras: List[str] = Field(..., description="Camera device ID list")
    ha_devices: Optional[List[str]] = Field(default_factory=list, description="Home Assistant device ID list")
    condition: Optional[str] = Field(None, description="Trigger condition (for LLM analysis in hybrid/llm mode)")
    condition_type: ConditionType = Field(ConditionType.LLM, description="Condition check type: llm or direct")
    ha_condition: Optional[str] = Field(None, description="HA device state condition for hybrid mode (direct check)")
    trigger_entity_id: Optional[str] = Field(None, description="Specific HA entity ID for direct/hybrid state matching")
    execute_info: ExecuteInfo = Field(..., description="Trigger execute info")
    filter: Optional[TriggerFilter] = Field(None, description="Trigger filter")
    detection_condition: Optional[DetectionCondition] = Field(
        None, description="Object detection trigger condition"
    )


class TriggerRuleDetail(TriggerRule):
    """Trigger rule response data model, includes camera name and scene name"""
    cameras: List[CameraInfo] = Field(..., description="Camera information list, includes ID and name")
    ha_devices: Optional[List[HADeviceInfo]] = Field(
        default_factory=list, description="Home Assistant device information list")
    execute_info: ExecuteInfoDetail = Field(..., description="Trigger execute info details")

    @classmethod
    def from_trigger_rule(cls,
        trigger_rule: TriggerRule,
        cameras: List[CameraInfo],
        execute_info: ExecuteInfoDetail,
        ha_devices: Optional[List[HADeviceInfo]] = None,
    ) -> "TriggerRuleDetail":
        trigger_rule_data = trigger_rule.model_dump(exclude={"cameras", "execute_info", "ha_devices"})
        return cls(
            **trigger_rule_data,
            cameras=cameras,
            ha_devices=ha_devices or [],
            execute_info=execute_info,
        )

    @classmethod
    def to_trigger_rule(cls, instance) -> TriggerRule:
        camera_dids = [camera.did for camera in instance.cameras]
        ha_device_ids = [device.did for device in instance.ha_devices] if instance.ha_devices else []
        execute_info = ExecuteInfoDetail.to_execute_info(instance.execute_info)
        instance_data = instance.model_dump(exclude={"cameras", "execute_info", "ha_devices"})
        return TriggerRule(
            **instance_data,
            cameras=camera_dids,
            ha_devices=ha_device_ids,
            execute_info=execute_info)


class TriggerConditionV2(BaseModel):
    """Unified trigger condition for v2 rules."""
    type: ConditionType = Field(ConditionType.LLM, description="Condition type")
    llm_condition: Optional[str] = Field(None, description="Natural language condition for LLM mode")
    camera_condition: Optional[str] = Field(None, description="Camera condition used in hybrid mode")
    ha_condition: Optional[str] = Field(None, description="HA condition used in direct/hybrid mode")
    detection_condition: Optional[DetectionCondition] = Field(None, description="Detection condition config")


class TriggerTargetV2(BaseModel):
    """Trigger targets for v2 rules."""
    camera_ids: List[str] = Field(default_factory=list, description="Camera IDs")
    ha_device_ids: List[str] = Field(default_factory=list, description="HA device IDs")
    trigger_entity_id: Optional[str] = Field(None, description="Specific HA entity used for direct/hybrid matching")


class TriggerRuleV2(BaseModel):
    """Trigger rule v2 data model."""
    id: Optional[str] = Field(None, description="Rule ID")
    enabled: bool = Field(True, description="Whether enabled")
    name: str = Field(..., description="Rule name")
    trigger: TriggerConditionV2 = Field(..., description="Trigger condition config")
    targets: TriggerTargetV2 = Field(default_factory=TriggerTargetV2, description="Trigger targets")
    execute_info: ExecuteInfo = Field(..., description="Execute info")
    filter: Optional[TriggerFilter] = Field(None, description="Trigger filter")

    def to_runtime_rule(self) -> TriggerRule:
        """Convert v2 rule to runtime TriggerRule used by runner."""
        condition_type = self.trigger.type
        # Runtime condition is aligned with original behavior.
        if condition_type == ConditionType.DIRECT:
            condition = self.trigger.ha_condition
        elif condition_type == ConditionType.HYBRID:
            condition = self.trigger.camera_condition or self.trigger.llm_condition
        elif condition_type in (ConditionType.DETECTION, ConditionType.FACE_RECOGNITION):
            condition = self.trigger.llm_condition
        else:
            condition = self.trigger.llm_condition

        return TriggerRule(
            id=self.id,
            enabled=self.enabled,
            name=self.name,
            cameras=self.targets.camera_ids,
            ha_devices=self.targets.ha_device_ids,
            condition=condition,
            condition_type=condition_type,
            ha_condition=self.trigger.ha_condition,
            trigger_entity_id=self.targets.trigger_entity_id,
            detection_condition=self.trigger.detection_condition,
            execute_info=self.execute_info,
            filter=self.filter,
        )

    @classmethod
    def from_runtime_rule(cls, rule: TriggerRule) -> "TriggerRuleV2":
        """Convert runtime TriggerRule back to v2 shape for API responses."""
        condition_type = rule.condition_type
        trigger = TriggerConditionV2(
            type=condition_type,
            llm_condition=rule.condition if condition_type in (ConditionType.LLM, ConditionType.DETECTION, ConditionType.FACE_RECOGNITION) else None,
            camera_condition=rule.condition if condition_type == ConditionType.HYBRID else None,
            ha_condition=rule.ha_condition if condition_type in (ConditionType.DIRECT, ConditionType.HYBRID) else None,
            detection_condition=rule.detection_condition,
        )
        targets = TriggerTargetV2(
            camera_ids=rule.cameras or [],
            ha_device_ids=rule.ha_devices or [],
            trigger_entity_id=rule.trigger_entity_id,
        )
        return cls(
            id=rule.id,
            enabled=rule.enabled,
            name=rule.name,
            trigger=trigger,
            targets=targets,
            execute_info=rule.execute_info,
            filter=rule.filter,
        )


