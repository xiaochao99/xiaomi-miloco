# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Wakeup data models
Define wakeup-related data structures for the "Wake Up XiaoAI" feature
"""

from enum import Enum
from typing import Optional, Dict, List, Any
from datetime import datetime
from pydantic import BaseModel, Field


class WakeUpMode(str, Enum):
    """Wakeup mode"""
    DISABLED = "disabled"
    MANUAL = "manual"
    PROACTIVE = "proactive"
    INTERACTIVE = "interactive"


class WakeUpState(str, Enum):
    """Wakeup session state"""
    PENDING = "pending"
    CONTEXT_BUILDING = "context_building"
    TTS_PLAYING = "tts_playing"
    AWAITING_WAKEUP = "awaiting_wakeup"
    VOICE_CAPTURING = "voice_capturing"
    AI_PROCESSING = "ai_processing"
    RESPONSE_SPEAKING = "response_speaking"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


class TriggerSourceType(str, Enum):
    """Trigger source type"""
    DEVICE_STATE = "device_state"
    SECURITY_ALERT = "security_alert"
    SCHEDULE = "schedule"
    ENVIRONMENT = "environment"
    DETECTION = "detection"
    CUSTOM = "custom"


class InquirySource(str, Enum):
    """Inquiry content source"""
    AUTO = "auto"
    CUSTOM = "custom"
    RULE_BROADCAST = "rule_broadcast"


class WakeUpConfig(BaseModel):
    """Wakeup configuration in rule"""
    enabled: bool = Field(False, description="Enable wakeup feature")
    mode: WakeUpMode = Field(
        WakeUpMode.PROACTIVE,
        description="Wakeup mode: disabled/manual/proactive/interactive"
    )
    inquiry_source: InquirySource = Field(
        InquirySource.AUTO,
        description="Inquiry content source"
    )
    custom_inquiry: Optional[str] = Field(
        None,
        description="Custom inquiry content when source is custom",
        max_length=100
    )
    suggested_actions: List[str] = Field(
        default_factory=list,
        description="Suggested action options displayed to user"
    )
    wakeup_timeout: int = Field(
        30,
        description="Wakeup waiting timeout/seconds",
        ge=5,
        le=120
    )
    voice_input_timeout: int = Field(
        60,
        description="Voice input timeout/seconds",
        ge=10,
        le=300
    )
    keep_alive_after_response: bool = Field(
        False,
        description="Keep wakeup active after AI response"
    )
    retry_count: int = Field(
        2,
        description="Wakeup retry count when failed",
        ge=0,
        le=5
    )
    retry_interval: int = Field(
        5,
        description="Retry interval/seconds",
        ge=1,
        le=30
    )
    target_devices: List[str] = Field(
        default_factory=list,
        description="Target device IDs for wakeup"
    )


class EnvironmentalData(BaseModel):
    """Environmental data"""
    temperature: Optional[float] = Field(None, description="Temperature/°C")
    humidity: Optional[float] = Field(None, description="Humidity/%")
    air_quality: Optional[str] = Field(None, description="Air quality")
    pm25: Optional[float] = Field(None, description="PM2.5/μg/m³")
    co2: Optional[float] = Field(None, description="CO2/ppm")


class TriggerInfo(BaseModel):
    """Trigger event information"""
    source_type: TriggerSourceType = Field(
        TriggerSourceType.CUSTOM,
        description="Trigger source type"
    )
    description: str = Field("", description="Trigger event description")
    details: Dict[str, Any] = Field(
        default_factory=dict,
        description="Event details"
    )
    severity: str = Field(
        "normal",
        description="Severity: critical/warning/normal/info"
    )
    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="Event timestamp"
    )


class InquiryDecision(BaseModel):
    """AI inquiry decision result"""
    required: bool = Field(False, description="Whether inquiry is required")
    content: str = Field("", description="Inquiry content")
    reason: str = Field("", description="Decision reason")
    suggested_actions: List[str] = Field(
        default_factory=list,
        description="Suggested action options"
    )


class WakeUpContext(BaseModel):
    """Wakeup context passed to AI dialogue system"""
    session_id: str = Field(..., description="Session ID")
    rule_id: str = Field(..., description="Trigger rule ID")
    rule_name: str = Field(..., description="Rule name")

    trigger_condition: str = Field("", description="Trigger condition description")
    trigger_source: TriggerSourceType = Field(
        TriggerSourceType.CUSTOM,
        description="Trigger source type"
    )
    trigger_details: Dict[str, Any] = Field(
        default_factory=dict,
        description="Trigger event details"
    )
    trigger_severity: str = Field("normal", description="Trigger severity")

    requires_inquiry: bool = Field(False, description="Whether AI requires inquiry")
    inquiry_content: Optional[str] = Field(None, description="Inquiry content")
    inquiry_reason: Optional[str] = Field(None, description="Inquiry decision reason")
    suggested_actions: List[str] = Field(
        default_factory=list,
        description="Suggested action options"
    )

    relevant_data: Dict[str, Any] = Field(
        default_factory=dict,
        description="Relevant data for current trigger"
    )

    recent_interactions: List[Dict[str, str]] = Field(
        default_factory=list,
        description="Recent interaction history"
    )

    created_at: datetime = Field(
        default_factory=datetime.now,
        description="Context creation time"
    )

    def to_prompt_context(self) -> str:
        """Convert to AI prompt context"""
        context = f"""【当前场景】
规则: {self.rule_name}
触发: {self.trigger_condition}
事件类型: {self.trigger_source.value}
严重程度: {self.trigger_severity}"""

        if self.trigger_details:
            context += f"\n\n【事件详情】\n{self.trigger_details}"

        if self.relevant_data:
            context += f"\n\n【相关数据】\n{self.relevant_data}"

        if self.requires_inquiry and self.inquiry_content:
            context += f"\n\n【主动询问】\n{self.inquiry_content}"
            if self.inquiry_reason:
                context += f"\n(原因: {self.inquiry_reason})"

        if self.suggested_actions:
            context += "\n\n【建议操作】\n"
            for action in self.suggested_actions:
                context += f"- {action}\n"

        if self.recent_interactions:
            context += "\n【最近对话】\n"
            for idx, msg in enumerate(self.recent_interactions[-3:], 1):
                context += f"  {idx}. {msg.get('role', 'user')}: {msg.get('content', '')}\n"

        return context


class WakeUpSession(BaseModel):
    """Wakeup session state"""
    session_id: str = Field(..., description="Session ID")
    context: WakeUpContext = Field(..., description="Wakeup context")
    state: WakeUpState = Field(
        WakeUpState.PENDING,
        description="Current session state"
    )
    device_ids: Optional[List[str]] = Field(
        None,
        description="Target device IDs"
    )
    created_at: datetime = Field(
        default_factory=datetime.now,
        description="Session creation time"
    )
    tts_start_time: Optional[datetime] = Field(
        None,
        description="TTS playback start time"
    )
    wakeup_start_time: Optional[datetime] = Field(
        None,
        description="Wakeup listening start time"
    )
    turn_count: int = Field(
        0,
        description="Dialogue turn count"
    )

    class Config:
        arbitrary_types_allowed = True


class IntentType:
    """User intent types for wakeup dialogue"""
    AGREE = "agree"
    REFUSE = "refuse"
    MODIFY = "modify"
    DELAY = "delay"
    CLARIFY = "clarify"
    OTHER = "other"
    UNKNOWN = "unknown"


class IntentResult(BaseModel):
    """Intent understanding result"""
    intent: str = Field(IntentType.UNKNOWN, description="Recognized intent")
    confidence: float = Field(0.0, description="Intent confidence 0.0-1.0")
    action_requested: Optional[str] = Field(
        None,
        description="Action requested by user"
    )
    action_parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Action parameters"
    )
    response_to_user: str = Field("", description="AI response to user")
    reasoning: str = Field("", description="Intent reasoning")


class ProcessResult(BaseModel):
    """Wakeup process result"""
    response: str = Field("", description="AI response to user")
    action_executed: bool = Field(False, description="Whether action was executed")
    action_name: Optional[str] = Field(None, description="Executed action name")
    action_success: Optional[bool] = Field(None, description="Action execution result")
    should_end: bool = Field(True, description="Whether dialogue should end")
    intent: Optional[IntentResult] = Field(None, description="Intent understanding result")


class WakeUpExecutionResult(BaseModel):
    """Wakeup execution result"""
    success: bool = Field(False, description="Overall execution success")
    session_id: str = Field("", description="Session ID")
    user_speech: Optional[str] = Field(None, description="User speech text")
    response: Optional[str] = Field(None, description="AI response")
    action_executed: bool = Field(False, description="Whether action was executed")
    action_success: Optional[bool] = Field(None, description="Action execution result")
    ended: bool = Field(True, description="Whether session ended")
    error: Optional[str] = Field(None, description="Error message if failed")
