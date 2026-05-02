# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class HabitEventType(Enum):
    DEVICE_STATE_CHANGE = "device_state_change"
    USER_COMMAND = "user_command"
    AUTOMATION_TRIGGER = "automation_trigger"
    ENVIRONMENT_CHANGE = "environment_change"
    DETECTION_EVENT = "detection_event"


class HabitCategory(Enum):
    LIGHT_CONTROL = "light_control"
    CURTAIN_CONTROL = "curtain_control"
    CLIMATE_CONTROL = "climate_control"
    SWITCH_CONTROL = "switch_control"
    BATH_ROUTINE = "bath_routine"
    SLEEP_ROUTINE = "sleep_routine"
    WAKE_UP_ROUTINE = "wake_up_routine"
    DEVICE_USAGE = "device_usage"
    SECURITY_CHECK = "security_check"
    MEDIA_CONTROL = "media_control"
    UNKNOWN = "unknown"


@dataclass
class HabitEvent:
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.now)
    event_type: HabitEventType = HabitEventType.DEVICE_STATE_CHANGE
    category: HabitCategory = HabitCategory.UNKNOWN

    entity_id: Optional[str] = None
    device_domain: Optional[str] = None
    device_name: Optional[str] = None

    old_state: Optional[str] = None
    new_state: Optional[str] = None
    attributes: Optional[Dict[str, Any]] = None

    day_of_week: int = 0
    hour_of_day: int = 0
    minute_of_hour: int = 0
    is_weekend: bool = False
    is_holiday: bool = False

    temperature: Optional[float] = None
    humidity: Optional[float] = None
    light_level: Optional[float] = None
    is_home: Optional[bool] = None
    is_anyone_present: Optional[bool] = None
    outdoor_temperature: Optional[float] = None
    weather: Optional[str] = None
    water_leak_detected: Optional[bool] = None
    traffic_restricted: Optional[str] = None

    source: str = "ha_websocket"
    confidence: float = 1.0
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp.timestamp(),
            "event_type": self.event_type.value,
            "category": self.category.value,
            "entity_id": self.entity_id,
            "device_domain": self.device_domain,
            "device_name": self.device_name,
            "old_state": self.old_state,
            "new_state": self.new_state,
            "attributes": json.dumps(self.attributes) if self.attributes else None,
            "day_of_week": self.day_of_week,
            "hour_of_day": self.hour_of_day,
            "minute_of_hour": self.minute_of_hour,
            "is_weekend": 1 if self.is_weekend else 0,
            "is_holiday": 1 if self.is_holiday else 0,
            "temperature": self.temperature,
            "humidity": self.humidity,
            "light_level": self.light_level,
            "is_home": 1 if self.is_home else (0 if self.is_home is not None else None),
            "is_anyone_present": 1 if self.is_anyone_present else (0 if self.is_anyone_present is not None else None),
            "outdoor_temperature": self.outdoor_temperature,
            "weather": self.weather,
            "water_leak_detected": 1 if self.water_leak_detected else (0 if self.water_leak_detected is not None else None),
            "traffic_restricted": self.traffic_restricted,
            "source": self.source,
            "confidence": self.confidence,
            "metadata": json.dumps(self.metadata) if self.metadata else None,
        }

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "HabitEvent":
        return cls(
            event_id=row["event_id"],
            timestamp=datetime.fromtimestamp(row["timestamp"]),
            event_type=HabitEventType(row["event_type"]),
            category=HabitCategory(row["category"]),
            entity_id=row.get("entity_id"),
            device_domain=row.get("device_domain"),
            device_name=row.get("device_name"),
            old_state=row.get("old_state"),
            new_state=row.get("new_state"),
            attributes=json.loads(row["attributes"]) if row.get("attributes") else None,
            day_of_week=row.get("day_of_week", 0),
            hour_of_day=row.get("hour_of_day", 0),
            minute_of_hour=row.get("minute_of_hour", 0),
            is_weekend=bool(row.get("is_weekend", 0)),
            is_holiday=bool(row.get("is_holiday", 0)),
            temperature=row.get("temperature"),
            humidity=row.get("humidity"),
            light_level=row.get("light_level"),
            is_home=bool(row["is_home"]) if row.get("is_home") is not None else None,
            is_anyone_present=bool(row["is_anyone_present"]) if row.get("is_anyone_present") is not None else None,
            outdoor_temperature=row.get("outdoor_temperature"),
            weather=row.get("weather"),
            water_leak_detected=bool(row["water_leak_detected"]) if row.get("water_leak_detected") is not None else None,
            traffic_restricted=row.get("traffic_restricted"),
            source=row.get("source", "ha_websocket"),
            confidence=row.get("confidence", 1.0),
            metadata=json.loads(row["metadata"]) if row.get("metadata") else None,
        )


@dataclass
class BehaviorPattern:
    id: Optional[int] = None
    pattern_type: str = ""
    user_id: str = "default"
    entity_id: Optional[str] = None
    category: Optional[str] = None
    day_of_week: Optional[int] = None
    hour_of_day: Optional[int] = None
    minute_of_hour: Optional[int] = None
    confidence: float = 0.5
    occurrence_count: int = 1
    last_occurrence: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: Optional[float] = None
    updated_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "pattern_type": self.pattern_type,
            "user_id": self.user_id,
            "entity_id": self.entity_id,
            "category": self.category,
            "day_of_week": self.day_of_week,
            "hour_of_day": self.hour_of_day,
            "minute_of_hour": self.minute_of_hour,
            "confidence": self.confidence,
            "occurrence_count": self.occurrence_count,
            "last_occurrence": self.last_occurrence,
            "metadata": json.dumps(self.metadata) if self.metadata else None,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "BehaviorPattern":
        return cls(
            id=row.get("id"),
            pattern_type=row.get("pattern_type", ""),
            user_id=row.get("user_id", "default"),
            entity_id=row.get("entity_id"),
            category=row.get("category"),
            day_of_week=row.get("day_of_week"),
            hour_of_day=row.get("hour_of_day"),
            minute_of_hour=row.get("minute_of_hour"),
            confidence=row.get("confidence", 0.5),
            occurrence_count=row.get("occurrence_count", 1),
            last_occurrence=row.get("last_occurrence"),
            metadata=json.loads(row["metadata"]) if row.get("metadata") else None,
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )


@dataclass
class LearningModel:
    id: Optional[int] = None
    model_type: str = ""
    model_data: Optional[bytes] = None
    version: int = 1
    accuracy: Optional[float] = None
    training_samples: Optional[int] = None
    created_at: Optional[float] = None


@dataclass
class PredictionContext:
    current_time: datetime = field(default_factory=datetime.now)
    day_of_week: int = 0
    hour_of_day: int = 0
    minute_of_hour: int = 0
    is_weekend: bool = False
    pattern_type: Optional[str] = None
    entity_id: Optional[str] = None
    current_state: Optional[str] = None
    environment: Optional[Dict[str, Any]] = None
    recent_events: List[HabitEvent] = field(default_factory=list)
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    light_level: Optional[float] = None
    is_home: bool = True
    is_anyone_present: bool = True
    outdoor_temperature: Optional[float] = None
    weather: Optional[str] = None
    wind_speed: Optional[float] = None
    air_quality: Optional[float] = None
    time_period: str = "day"
    water_leak_detected: bool = False
    traffic_restricted: Optional[str] = None


@dataclass
class RulePrediction:
    action: Optional[str] = None
    entity_id: Optional[str] = None
    service: Optional[str] = None
    predicted_state: Optional[str] = None
    attributes: Optional[Dict[str, Any]] = None
    confidence: float = 0.0


@dataclass
class TimePrediction:
    time: Optional[datetime] = None
    confidence: float = 0.0


@dataclass
class PredictionResult:
    predicted_action: Optional[str] = None
    predicted_time: Optional[datetime] = None
    predicted_state: Optional[str] = None
    entity_id: Optional[str] = None
    service: Optional[str] = None
    attributes: Optional[Dict[str, Any]] = None
    confidence: float = 0.0
    reasoning: str = ""
    expected_time: float = 0.0
    pattern_type: Optional[str] = None
    time_confidence: Optional[float] = None
    time_slots: Optional[list] = None
    last_occurrence: Optional[datetime] = None
    occurrence_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "predicted_action": self.predicted_action,
            "predicted_time": self.predicted_time.isoformat() if self.predicted_time else None,
            "predicted_state": self.predicted_state,
            "entity_id": self.entity_id,
            "service": self.service,
            "attributes": self.attributes,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "expected_time": self.expected_time,
            "pattern_type": self.pattern_type,
            "time_confidence": self.time_confidence,
            "occurrence_count": self.occurrence_count,
            "last_occurrence": self.last_occurrence.isoformat() if self.last_occurrence else None,
        }


@dataclass
class DecisionAction:
    entity_id: str = ""
    domain: str = ""
    service: str = ""
    new_state: Optional[str] = None
    attributes: Optional[Dict[str, Any]] = None
    prediction_confidence: float = 0.0
    reasoning: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "domain": self.domain,
            "service": self.service,
            "new_state": self.new_state,
            "attributes": self.attributes,
            "prediction_confidence": self.prediction_confidence,
            "reasoning": self.reasoning,
        }


@dataclass
class DecisionContext:
    current_time: datetime = field(default_factory=datetime.now)
    device_states: Dict[str, Any] = field(default_factory=dict)
    environment: Dict[str, Any] = field(default_factory=dict)
    habits: List[BehaviorPattern] = field(default_factory=list)
    day_of_week: int = 0
    is_weekend: bool = False
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    light_level: Optional[float] = None
    is_home: bool = True
    is_anyone_present: bool = True
    outdoor_temperature: Optional[float] = None
    weather: Optional[str] = None
    wind_speed: Optional[float] = None
    air_quality: Optional[float] = None
    time_period: str = "day"
    water_leak_detected: bool = False
    traffic_restricted: Optional[str] = None
