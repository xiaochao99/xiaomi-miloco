# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Context Provider - provides real-time environmental context from Home Assistant.
Supports manual entity configuration: user specifies which HA entity to use for each dimension.
Falls back to auto-detection when no entity is configured.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

CONTEXT_ENTITY_KEYS = [
    "indoor_temperature",
    "humidity",
    "outdoor_temperature",
    "light_level",
    "is_home",
    "is_anyone_present",
    "weather",
    "air_quality",
]


@dataclass
class EnvironmentContext:
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    outdoor_temperature: Optional[float] = None
    outdoor_humidity: Optional[float] = None
    light_level: Optional[float] = None
    is_home: bool = True
    is_anyone_present: bool = True
    weather: Optional[str] = None
    weather_temperature: Optional[float] = None
    wind_speed: Optional[float] = None
    air_quality: Optional[float] = None
    time_period: str = "day"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "temperature": self.temperature,
            "humidity": self.humidity,
            "outdoor_temperature": self.outdoor_temperature,
            "outdoor_humidity": self.outdoor_humidity,
            "light_level": self.light_level,
            "is_home": self.is_home,
            "is_anyone_present": self.is_anyone_present,
            "weather": self.weather,
            "weather_temperature": self.weather_temperature,
            "wind_speed": self.wind_speed,
            "air_quality": self.air_quality,
            "time_period": self.time_period,
        }

    def similarity_score(self, other: "EnvironmentContext") -> float:
        if other is None:
            return 0.5

        scores: List[float] = []

        if self.temperature is not None and other.temperature is not None:
            diff = abs(self.temperature - other.temperature)
            scores.append(max(0.0, 1.0 - diff / 10.0))
        elif self.temperature is None and other.temperature is None:
            scores.append(1.0)

        if self.humidity is not None and other.humidity is not None:
            diff = abs(self.humidity - other.humidity)
            scores.append(max(0.0, 1.0 - diff / 30.0))
        elif self.humidity is None and other.humidity is None:
            scores.append(1.0)

        if self.light_level is not None and other.light_level is not None:
            diff = abs(self.light_level - other.light_level)
            scores.append(max(0.0, 1.0 - diff / 500.0))
        elif self.light_level is None and other.light_level is None:
            scores.append(1.0)

        if self.is_home == other.is_home:
            scores.append(1.0)
        else:
            scores.append(0.0)

        if self.is_anyone_present == other.is_anyone_present:
            scores.append(1.0)
        else:
            scores.append(0.2)

        if self.weather and other.weather:
            scores.append(1.0 if self.weather == other.weather else 0.3)
        elif not self.weather and not other.weather:
            scores.append(0.8)

        if not scores:
            return 0.5

        return round(sum(scores) / len(scores), 3)


class ContextProvider:
    _instance: Optional["ContextProvider"] = None

    TEMP_DEVICE_CLASSES = {"temperature"}
    HUMIDITY_DEVICE_CLASSES = {"humidity"}
    PRESENCE_DOMAINS = {"person", "device_tracker", "group"}
    PRESENCE_BINARY_PREFIXES = (
        "binary_sensor.motion",
        "binary_sensor.occupancy",
        "binary_sensor.presence",
        "binary_sensor.door",
        "binary_sensor.window",
    )
    LIGHT_SENSOR_DOMAINS = {"sensor"}
    WEATHER_DOMAIN = "weather"
    AIR_QUALITY_DEVICE_CLASSES = {"aqi", "pm25", "pm2.5"}
    IGNORED_DOMAINS = {"automation", "script", "scene", "zone", "weather_forecast"}

    def __init__(self, ha_listener=None, context_entities: Optional[Dict[str, str]] = None):
        self._ha_listener = ha_listener
        self._context_entities: Dict[str, str] = context_entities or {}
        ContextProvider._instance = self
        logger.info("ContextProvider initialized, configured entities: %s", self._context_entities)

    @classmethod
    def get_instance(cls) -> Optional["ContextProvider"]:
        return cls._instance

    def set_ha_listener(self, listener) -> None:
        self._ha_listener = listener

    def set_context_entities(self, entities: Dict[str, str]) -> None:
        self._context_entities = entities or {}
        logger.info("ContextProvider entities updated: %s", list(self._context_entities.keys()))

    def get_context_entities(self) -> Dict[str, str]:
        return dict(self._context_entities)

    def _get_all_states(self) -> Dict[str, Dict[str, Any]]:
        if self._ha_listener:
            return self._ha_listener.get_all_states()
        return {}

    def get_context(self) -> EnvironmentContext:
        states = self._get_all_states()
        if not states:
            return EnvironmentContext()

        ctx = EnvironmentContext()
        ctx.temperature = self._extract_indoor_temperature(states)
        ctx.humidity = self._extract_indoor_humidity(states)
        ctx.outdoor_temperature = self._extract_outdoor_temperature(states)
        ctx.outdoor_humidity = self._extract_outdoor_humidity(states)
        ctx.light_level = self._extract_light_level(states)
        ctx.is_home = self._check_is_home(states)
        ctx.is_anyone_present = self._check_anyone_present(states)
        ctx.weather = self._extract_weather(states)
        ctx.weather_temperature = self._extract_weather_temperature(states)
        ctx.wind_speed = self._extract_wind_speed(states)
        ctx.air_quality = self._extract_air_quality(states)
        ctx.time_period = self._get_time_period(states)
        return ctx

    def get_all_entities(self) -> list:
        states = self._get_all_states()
        result = []
        if not states:
            return result
        for entity_id, state_obj in states.items():
            domain = entity_id.split(".")[0] if "." in entity_id else ""
            if domain in self.IGNORED_DOMAINS:
                continue
            attrs = state_obj.get("attributes", {}) if isinstance(state_obj, dict) else {}
            result.append({
                "entity_id": entity_id,
                "state": state_obj.get("state") if isinstance(state_obj, dict) else None,
                "friendly_name": attrs.get("friendly_name", ""),
                "device_class": attrs.get("device_class", ""),
                "domain": domain,
            })
        result.sort(key=lambda x: x["entity_id"])
        return result

    def get_entity_current_state(self, entity_id: str) -> Optional[str]:
        states = self._get_all_states()
        state_obj = states.get(entity_id)
        if state_obj:
            return state_obj.get("state")
        return None

    def _get_configured_entity(self, key: str, states: Dict) -> Optional[str]:
        entity_id = self._context_entities.get(key)
        if entity_id and entity_id in states:
            return entity_id
        if entity_id:
            logger.debug("Configured entity %s for '%s' not found in HA states", entity_id, key)
        return None

    def _read_float_from_entity(self, entity_id: str, states: Dict) -> Optional[float]:
        state_obj = states.get(entity_id)
        if not state_obj:
            return None
        return self._parse_float(state_obj.get("state"))

    def _read_bool_from_entity(self, entity_id: str, states: Dict) -> Optional[bool]:
        state_obj = states.get(entity_id)
        if not state_obj:
            return None
        state_val = state_obj.get("state", "").lower()
        if state_val in ("on", "home", "online", "true", "1", "open"):
            return True
        if state_val in ("off", "away", "not_home", "false", "0", "closed"):
            return False
        return None

    def _read_string_from_entity(self, entity_id: str, states: Dict) -> Optional[str]:
        state_obj = states.get(entity_id)
        if not state_obj:
            return None
        return state_obj.get("state")

    def _read_attr_float(self, entity_id: str, attr_name: str, states: Dict) -> Optional[float]:
        state_obj = states.get(entity_id)
        if not state_obj:
            return None
        attrs = state_obj.get("attributes", {})
        return self._parse_float(attrs.get(attr_name))

    def _extract_indoor_temperature(self, states: Dict) -> Optional[float]:
        configured = self._get_configured_entity("indoor_temperature", states)
        if configured:
            val = self._read_float_from_entity(configured, states)
            if val is not None:
                return val

        for entity_id, state_obj in states.items():
            if not entity_id.startswith("sensor."):
                continue
            attrs = state_obj.get("attributes", {})
            device_class = attrs.get("device_class", "")
            if device_class in self.TEMP_DEVICE_CLASSES:
                val = self._parse_float(state_obj.get("state"))
                if val is not None and -20 <= val <= 60:
                    return val
        return None

    def _extract_indoor_humidity(self, states: Dict) -> Optional[float]:
        configured = self._get_configured_entity("humidity", states)
        if configured:
            val = self._read_float_from_entity(configured, states)
            if val is not None:
                return val

        candidates: List[float] = []
        for entity_id, state_obj in states.items():
            if not entity_id.startswith("sensor."):
                continue
            attrs = state_obj.get("attributes", {})
            device_class = attrs.get("device_class", "")
            if device_class in self.HUMIDITY_DEVICE_CLASSES:
                val = self._parse_float(state_obj.get("state"))
                if val is not None and 0 <= val <= 100:
                    candidates.append(val)
        if candidates:
            return round(sum(candidates) / len(candidates), 1)
        return None

    def _extract_outdoor_temperature(self, states: Dict) -> Optional[float]:
        configured = self._get_configured_entity("outdoor_temperature", states)
        if configured:
            val = self._read_float_from_entity(configured, states)
            if val is not None:
                return val
            val = self._read_attr_float(configured, "temperature", states)
            if val is not None:
                return val

        for entity_id, state_obj in states.items():
            if entity_id.startswith(self.WEATHER_DOMAIN):
                attrs = state_obj.get("attributes", {})
                temp = attrs.get("temperature")
                if temp is not None:
                    return self._parse_float(temp)
                break

        for entity_id, state_obj in states.items():
            if not entity_id.startswith("sensor."):
                continue
            attrs = state_obj.get("attributes", {})
            friendly_name = attrs.get("friendly_name", "").lower()
            if "outdoor" in friendly_name or "outdoor" in entity_id:
                device_class = attrs.get("device_class", "")
                if device_class in self.TEMP_DEVICE_CLASSES:
                    return self._parse_float(state_obj.get("state"))
        return None

    def _extract_outdoor_humidity(self, states: Dict) -> Optional[float]:
        configured = self._get_configured_entity("outdoor_temperature", states)
        for entity_id, state_obj in states.items():
            if not entity_id.startswith("sensor."):
                continue
            attrs = state_obj.get("attributes", {})
            friendly_name = attrs.get("friendly_name", "").lower()
            if "outdoor" in friendly_name or "outdoor" in entity_id:
                device_class = attrs.get("device_class", "")
                if device_class in self.HUMIDITY_DEVICE_CLASSES:
                    return self._parse_float(state_obj.get("state"))
        return None

    def _extract_light_level(self, states: Dict) -> Optional[float]:
        configured = self._get_configured_entity("light_level", states)
        if configured:
            val = self._read_float_from_entity(configured, states)
            if val is not None:
                return val

        for entity_id, state_obj in states.items():
            if not entity_id.startswith("sensor."):
                continue
            attrs = state_obj.get("attributes", {})
            device_class = attrs.get("device_class", "")
            if device_class in ("illuminance", "light"):
                return self._parse_float(state_obj.get("state"))
            if "light" in entity_id and "level" in entity_id:
                return self._parse_float(state_obj.get("state"))
        return None

    def _check_is_home(self, states: Dict) -> bool:
        configured = self._get_configured_entity("is_home", states)
        if configured:
            val = self._read_bool_from_entity(configured, states)
            if val is not None:
                return val
            state_val = self._read_string_from_entity(configured, states)
            if state_val:
                return state_val.lower() == "home"

        for entity_id, state_obj in states.items():
            domain = entity_id.split(".")[0]
            if domain in self.PRESENCE_DOMAINS:
                state_val = state_obj.get("state", "").lower()
                if state_val in ("home", "away", "not_home"):
                    return state_val == "home"

        for entity_id, state_obj in states.items():
            if entity_id.startswith("group."):
                state_val = state_obj.get("state", "").lower()
                if state_val in ("home", "not_home"):
                    return state_val == "home"

        return True

    def _check_anyone_present(self, states: Dict) -> bool:
        configured = self._get_configured_entity("is_anyone_present", states)
        if configured:
            val = self._read_bool_from_entity(configured, states)
            if val is not None:
                return val
            state_val = self._read_string_from_entity(configured, states)
            if state_val:
                return state_val.lower() in ("on", "home", "online", "true")

        for entity_id, state_obj in states.items():
            domain = entity_id.split(".")[0]
            if domain in self.PRESENCE_DOMAINS:
                state_val = state_obj.get("state", "").lower()
                if state_val in ("home", "on", "online"):
                    return True

        for entity_id, state_obj in states.items():
            if entity_id.startswith(self.PRESENCE_BINARY_PREFIXES):
                state_val = state_obj.get("state", "").lower()
                if state_val == "on":
                    return True

        return True

    def _extract_weather(self, states: Dict) -> Optional[str]:
        configured = self._get_configured_entity("weather", states)
        if configured:
            return self._read_string_from_entity(configured, states)

        for entity_id, state_obj in states.items():
            if entity_id.startswith(self.WEATHER_DOMAIN):
                return state_obj.get("state")
        return None

    def _extract_weather_temperature(self, states: Dict) -> Optional[float]:
        configured = self._get_configured_entity("weather", states)
        if configured:
            val = self._read_attr_float(configured, "temperature", states)
            if val is not None:
                return val
            return self._read_float_from_entity(configured, states)

        for entity_id, state_obj in states.items():
            if entity_id.startswith(self.WEATHER_DOMAIN):
                attrs = state_obj.get("attributes", {})
                temp = attrs.get("temperature")
                if temp is not None:
                    return self._parse_float(temp)
                return self._parse_float(state_obj.get("state"))
        return None

    def _extract_wind_speed(self, states: Dict) -> Optional[float]:
        configured = self._get_configured_entity("weather", states)
        if configured:
            val = self._read_attr_float(configured, "wind_speed", states)
            if val is not None:
                return val

        for entity_id, state_obj in states.items():
            if entity_id.startswith(self.WEATHER_DOMAIN):
                attrs = state_obj.get("attributes", {})
                wind = attrs.get("wind_speed")
                if wind is not None:
                    return self._parse_float(wind)
        return None

    def _extract_air_quality(self, states: Dict) -> Optional[float]:
        configured = self._get_configured_entity("air_quality", states)
        if configured:
            val = self._read_float_from_entity(configured, states)
            if val is not None:
                return val

        for entity_id, state_obj in states.items():
            if not entity_id.startswith("sensor."):
                continue
            attrs = state_obj.get("attributes", {})
            device_class = attrs.get("device_class", "")
            if device_class in self.AIR_QUALITY_DEVICE_CLASSES:
                return self._parse_float(state_obj.get("state"))
            if "aqi" in entity_id or "pm25" in entity_id or "pm2.5" in entity_id:
                return self._parse_float(state_obj.get("state"))
        return None

    def _get_time_period(self, states: Dict) -> str:
        for entity_id, state_obj in states.items():
            if entity_id.startswith("sun."):
                state_val = state_obj.get("state", "").lower()
                if state_val == "above_horizon":
                    attrs = state_obj.get("attributes", {})
                    elevation = attrs.get("elevation", 0)
                    if elevation > 10:
                        return "day"
                    if elevation > 0:
                        return "twilight"
                    return "night"
                return "night"
        from datetime import datetime
        hour = datetime.now().hour
        if 7 <= hour < 18:
            return "day"
        if 18 <= hour < 20 or 5 <= hour < 7:
            return "twilight"
        return "night"

    @staticmethod
    def _parse_float(value) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            pass
        try:
            if isinstance(value, str):
                cleaned = ''.join([c for c in value if c in '0123456789.-'])
                if cleaned.replace('.', '', 1).isdigit():
                    return float(cleaned)
        except (ValueError, TypeError):
            pass
        return None
