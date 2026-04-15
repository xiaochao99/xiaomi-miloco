# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Home Assistant service module
"""

import logging
import json
from typing import List, Optional, Dict, Any

from miloco_server.mcp.mcp_client_manager import MCPClientManager
from miloco_server.middleware.exceptions import (
    HaServiceException,
    ValidationException,
    BusinessException
)
from miloco_server.proxy.ha_proxy import HAProxy
from miloco_server.schema.miot_schema import HAConfig, HADeviceInfo, HAControlRequest
from miloco_server.schema.trigger_schema import Action
from miloco_server.utils.default_action import DefaultPresetActionManager
from miloco_server.mcp.mcp_client import LocalMCPConfig, TransportType
from miloco_server.schema.mcp_schema import LocalMcpClientId

from miot.mcp import (
    HomeAssistantDeviceMcp,
    HomeAssistantDeviceMcpInterface,
    McpHADeviceInfo
)
from miot.types import HAAutomationInfo, HAStateInfo

logger = logging.getLogger(__name__)


class HaService:
    """Home Assistant service class"""

    # Mapping from HA domain to internal icon name
    _HA_DOMAIN_TO_INTERNAL_ICON = {
        "camera": "instantCameraOpen",
        "lock": "lock",
        "weather": "cloud",
        "media_player": "instantDevicePlay",
        "automation": "menuSmart",
        "script": "menuSmart",
        "scene": "menuSmart",
        # Fallbacks for common domains to ensures they have a valid internal icon
        "light": "menuDevice",
        "switch": "menuDevice",
        "fan": "menuDevice",
        "sensor": "menuDevice",
        "binary_sensor": "menuDevice",
        "climate": "menuDevice",
        "cover": "menuDevice",
        "vacuum": "menuDevice",
    }

    # Mapping from HA MDI icon string to internal icon name
    _HA_MDI_TO_INTERNAL_ICON = {
        "mdi:cctv": "instantCameraOpen",
        "mdi:camera": "instantCameraOpen",
        "mdi:lock": "lock",
        "mdi:lock-open": "lock",
        "mdi:cloud": "cloud",
        "mdi:weather-partly-cloudy": "cloud",
    }

    _HA_DOMAIN_DEFAULT_STATES = {
        "light": ["on", "off"],
        "switch": ["on", "off"],
        "fan": ["on", "off"],
        "input_boolean": ["on", "off"],
        "binary_sensor": ["on", "off"],
        "cover": ["open", "closed", "opening", "closing"],
        "lock": ["locked", "unlocked"],
        "alarm_control_panel": ["armed_home", "armed_away", "disarmed"],
    }

    @staticmethod
    def _iter_state_like_values(value: Any):
        """Yield scalar state-like values from mixed trigger payload fields."""
        if value is None:
            return
        if isinstance(value, (str, int, float, bool)):
            yield value
            return
        if isinstance(value, list):
            for item in value:
                yield from HaService._iter_state_like_values(item)
            return
        if isinstance(value, dict):
            # Common structure in HA: {"state": "..."} / {"value": "..."}
            for key in ("state", "value"):
                if key in value:
                    yield from HaService._iter_state_like_values(value.get(key))

    @staticmethod
    def _collect_automation_trigger_states(
        automations: Dict[str, Any],
        entity_id: str,
    ) -> List[tuple[str, str]]:
        """
        Extract candidate states from HA automation trigger definitions for one entity.

        Returns:
            List[(state_value, source)] where source includes automation id.
        """
        results: List[tuple[str, str]] = []
        for automation_id, automation in (automations or {}).items():
            try:
                payload = automation.model_dump() if hasattr(automation, "model_dump") else automation
                if not isinstance(payload, dict):
                    continue

                triggers = payload.get("trigger")
                if not isinstance(triggers, list):
                    continue

                for trig in triggers:
                    if not isinstance(trig, dict):
                        continue

                    # Match entity
                    trig_entity = trig.get("entity_id")
                    if isinstance(trig_entity, list):
                        if entity_id not in trig_entity:
                            continue
                    elif trig_entity != entity_id:
                        continue

                    # Common state-like fields in trigger definitions
                    for key in ("to", "from", "state", "not_to", "not_from", "above", "below"):
                        for raw in HaService._iter_state_like_values(trig.get(key)):
                            value_str = str(raw).strip()
                            if value_str:
                                results.append((value_str, f"automation_trigger:{automation_id}:{key}"))
            except Exception:  # pylint: disable=broad-except
                continue

        return results

    def __init__(
        self,
        ha_proxy: HAProxy,
        mcp_client_manager: MCPClientManager,
        default_preset_action_manager: Optional[DefaultPresetActionManager] = None
    ):
        self._ha_proxy = ha_proxy
        self._mcp_client_manager = mcp_client_manager
        self._default_preset_action_manager = default_preset_action_manager

    @property
    def ha_client(self) -> Optional[object]:
        """Get the HAHttpClient instance."""
        return self._ha_proxy.ha_client

    async def initialize_ha_devices_mcp(self):
        """Initialize HA devices MCP client if HA is configured"""
        if not self.ha_client:
            return

        try:
            # Create HA device MCP client
            async def _get_devices() -> List[McpHADeviceInfo]:
                devices = await self.get_ha_device_list()
                return [
                    McpHADeviceInfo(
                        entity_id=d.entity_id,
                        name=d.name,
                        state=d.state,
                        area=d.room_name,
                        domain=d.model # domain is stored in model
                    ) for d in devices
                ]

            async def _control_device(
                entity_id: str, domain: str, service: str, service_data: Optional[Dict[str, Any]] = None
            ) -> bool:
                try:
                    await self.control_ha_device(HAControlRequest(
                        entity_id=entity_id,
                        domain=domain,
                        service=service,
                        service_data=service_data
                    ))
                    return True
                except Exception:  # pylint: disable=broad-except
                    return False

            ha_devices_mcp = HomeAssistantDeviceMcp(
                interface=HomeAssistantDeviceMcpInterface(
                    translate_async=self._mcp_client_manager.miot_proxy.miot_client.i18n.translate_async,
                    get_devices_async=_get_devices,
                    control_device_async=_control_device
                )
            )
            await ha_devices_mcp.init_async()

            # Register the client with MCPClientManager
            await self._mcp_client_manager.add_client(
                transport_type=TransportType.LOCAL,
                config=LocalMCPConfig(
                    client_id=LocalMcpClientId.HA_DEVICES,
                    server_name="Home Assistant设备控制 (Home Assistant Device Control)",
                    mcp_server=ha_devices_mcp.mcp_instance
                )
            )

            logger.info("Successfully initialized Home Assistant Device MCP client")

        except Exception as e:  # pylint: disable=broad-except
            logger.error("Failed to initialize HA devices MCP: %s", e)

    async def refresh_ha_automations(self):
        """
        Refresh Home Assistant automation information
        """
        try:
            await self._ha_proxy.refresh_ha_automations()
        except Exception as e:  # pylint: disable=broad-except
            logger.error("Failed to refresh Home Assistant automations: %s", e)
            raise HaServiceException(f"Failed to refresh Home Assistant automations: {str(e)}") from e

    async def set_ha_config(self, ha_config: HAConfig):
        try:
            if not ha_config.base_url or not ha_config.base_url.strip():
                raise ValidationException("Home Assistant base URL cannot be empty")
            if not ha_config.token or not ha_config.token.strip():
                raise ValidationException("Home Assistant access token cannot be empty")

            await self._ha_proxy.set_ha_config(ha_config.base_url,
                                                    ha_config.token.strip())

            await self._mcp_client_manager.init_ha_automations()
            # Initialize HA devices MCP client when HA is configured
            await self.initialize_ha_devices_mcp()
            logger.info("Home Assistant configuration saved successfully: base_url=%s", ha_config.base_url)

        except ValidationException:
            raise
        except Exception as e:  # pylint: disable=broad-except
            logger.error("Exception occurred while saving Home Assistant configuration: %s", e)
            raise BusinessException(f"Failed to save Home Assistant configuration: {str(e)}") from e

    async def get_ha_config(self) -> HAConfig | None:
        try:
            ha_config = self._ha_proxy.get_ha_config()
            if not ha_config:
                logger.warning("Home Assistant configuration not set")
            return ha_config
        except Exception as e:  # pylint: disable=broad-except
            logger.error("Exception occurred while getting Home Assistant configuration: %s", e)
            raise HaServiceException(f"Failed to get Home Assistant configuration: {str(e)}") from e

    async def get_ha_automations(self) -> list[HAAutomationInfo]:
        try:
            automations = await self._ha_proxy.get_automations()
            if automations is None:
                logger.warning("Failed to get Home Assistant automation list")
                raise HaServiceException("Failed to get Home Assistant automation list")
            logger.info(
                "Successfully retrieved Home Assistant automation list - count: %d", len(automations.values()))
            return list(automations.values())

        except Exception as e:  # pylint: disable=broad-except
            logger.error("Failed to get Home Assistant automation list: %s", e)
            raise HaServiceException(
                f"Failed to get Home Assistant automation list: {str(e)}") from e

    async def get_ha_automation_actions(self) -> List[Action]:
        """
        Get Home Assistant automation action list

        Returns:
            List[Action]: Home Assistant automation action list

        Raises:
            HaServiceException: When getting automation actions fails
        """
        try:
            if not self._default_preset_action_manager:
                logger.error("DefaultPresetActionManager not initialized")
                raise HaServiceException("DefaultPresetActionManager not initialized")

            actions = await self._default_preset_action_manager.get_ha_automation_actions()

            return list(actions.values())
        except Exception as e:  # pylint: disable=broad-except
            logger.error("Failed to get Home Assistant automation action list: %s", e)
            raise HaServiceException(f"Failed to get Home Assistant automation action list: {str(e)}") from e

    def _get_icon_for_ha_device(self, state_info: HAStateInfo, base_url: str) -> str:
        """
        Determine the icon for HA device.
        Prioritizes entity_picture, then specific mappings, then domain-based mappings.
        """
        # 1. Check for entity_picture
        entity_picture = state_info.attributes.get("entity_picture")
        if entity_picture and isinstance(entity_picture, str):
            if entity_picture.startswith("http"):
                return entity_picture
            # Ensure base_url doesn't end with slash and entity_picture starts with slash
            # pylint: disable=inconsistent-quotes
            return f"{base_url.rstrip('/')}/{entity_picture.lstrip('/')}"

        # 2. Check specific MDI icon in attributes and map it
        ha_icon = state_info.attributes.get("icon")
        if ha_icon and isinstance(ha_icon, str):
            if ha_icon in self._HA_MDI_TO_INTERNAL_ICON:
                return self._HA_MDI_TO_INTERNAL_ICON[ha_icon]
            # If it's a URL, return it directly
            if ha_icon.startswith("http") or ha_icon.startswith("/"):
                return ha_icon

        # 3. Derive from domain
        if state_info.domain in self._HA_DOMAIN_TO_INTERNAL_ICON:
            return self._HA_DOMAIN_TO_INTERNAL_ICON[state_info.domain]
        # 4. Default generic icon
        return "menuDevice"

    async def get_ha_devices_grouped(self) -> Dict[str, Dict[str, Any]]:
        """
        Get HA devices grouped by device ID using templates.
        Returns:
            Dict[device_id, {name, area, entities: [entity_id]}]
        """
        if not self.ha_client:
            logger.debug("HA client not initialized, skipping get_ha_devices_grouped")
            return {}

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
            "{{ dev_id }}": {
               "name": {{ (device_attr(dev_id, 'name_by_user') or device_attr(dev_id, 'name') or dev_id) | to_json }},
               "area": {{ (area_name(dev_id) or '') | to_json }},
               "entities": {{ device_entities(dev_id) | list | to_json }}
            }{% if not loop.last %},{% endif %}
          {% endfor %}
        }
        """
        try:
            res = await self._ha_proxy.ha_client.render_template_async(template)
            devices = json.loads(res)

            # Sort devices: those with area first, then alphabetical by area and name
            sorted_items = sorted(
                devices.items(),
                key=lambda x: (
                    0 if x[1].get("area") else 1,  # Has area comes first
                    (x[1].get("area") or "").lower(),
                    (x[1].get("name") or "").lower()
                )
            )

            return dict(sorted_items)
        except Exception as e:  # pylint: disable=broad-except
            logger.error("Failed to get grouped HA devices: %s", e)
            return {}

    async def get_ha_device_list(self) -> List[HADeviceInfo]:
        """Get Home Assistant device list"""
        try:
            states = await self._ha_proxy.get_states()
            if states is None:
                logger.warning("Failed to get Home Assistant device list")
                return []
            areas = await self._ha_proxy.get_all_areas() or {}
            location_name = await self._ha_proxy.get_location_name() or ""
            ha_config = self._ha_proxy.get_ha_config()
            base_url = ha_config.base_url if ha_config else ""

            device_list = []

            for entity_id, state_info in states.items():
                is_online = state_info.state not in ["unavailable", "unknown"]
                supported_features = state_info.attributes.get("supported_features", 0)

                device_info = HADeviceInfo(
                    did=entity_id,
                    name=state_info.attributes.get("friendly_name") or entity_id,
                    online=is_online,
                    model=state_info.domain,
                    icon=self._get_icon_for_ha_device(state_info, base_url),
                    home_name=location_name,
                    room_name=areas.get(entity_id, ""),
                    entity_id=entity_id,
                    state=state_info.state,
                    attributes=state_info.attributes,
                    supported_features=supported_features
                )
                device_list.append(device_info)

            # Sort devices: devices with rooms first, then devices without rooms
            # Within each group, sort by room name and then device name
            device_list.sort(key=lambda x: (
                0 if x.room_name else 1,  # Devices with rooms come first
                x.room_name or "",        # Sort by room name
                x.name.lower()            # Then by device name (case-insensitive)
            ))

            logger.info("Successfully retrieved Home Assistant device list - count: %d", len(device_list))
            return device_list
        except Exception as e:  # pylint: disable=broad-except
            logger.error("Failed to get Home Assistant device list: %s", e)
            raise HaServiceException(f"Failed to get Home Assistant device list: {str(e)}") from e

    async def control_ha_device(self, control_req: HAControlRequest):
        """Control Home Assistant device"""
        try:
            result = await self._ha_proxy.call_service(
                domain=control_req.domain,
                service=control_req.service,
                entity_id=control_req.entity_id
            )
            if not result:
                raise HaServiceException("Failed to control Home Assistant device")
            logger.info("Successfully controlled Home Assistant device: %s", control_req.entity_id)
        except Exception as e:  # pylint: disable=broad-except
            logger.error("Failed to control Home Assistant device: %s", e)
            raise HaServiceException(f"Failed to control Home Assistant device: {str(e)}") from e

    async def get_entity_state_options(self, entity_id: str) -> Dict[str, Any]:
        """Get selectable state options for a specific HA entity."""
        if not entity_id or "." not in entity_id:
            raise ValidationException("Invalid entity_id")

        states = await self._ha_proxy.get_states()
        if states is None:
            raise HaServiceException("Failed to fetch Home Assistant states")

        target = states.get(entity_id)
        if not target:
            raise ValidationException(f"Entity not found: {entity_id}")

        domain = entity_id.split(".", 1)[0]
        options: Dict[str, str] = {}

        def add_option(value: Any, source: str):
            if value is None:
                return
            value_str = str(value).strip()
            if not value_str:
                return
            if value_str not in options:
                options[value_str] = source

        # Source 1: current state
        add_option(target.state, "current_state")

        # Source 2: attribute-enumerated states
        attributes = target.attributes or {}
        attr_keys = [
            "options",
            "hvac_modes",
            "preset_modes",
            "fan_modes",
            "swing_modes",
            "source_list",
            "effect_list",
        ]
        for key in attr_keys:
            values = attributes.get(key)
            if isinstance(values, list):
                for v in values:
                    add_option(v, f"attribute:{key}")

        # Source 3: domain defaults
        for v in self._HA_DOMAIN_DEFAULT_STATES.get(domain, []):
            add_option(v, f"domain:{domain}")

        # Source 4: HA automation trigger conditions
        automations = await self._ha_proxy.get_automations()
        for value, source in self._collect_automation_trigger_states(automations or {}, entity_id):
            add_option(value, source)

        return {
            "entity_id": entity_id,
            "current_state": target.state,
            "domain": domain,
            "options": [{"value": k, "source": src} for k, src in sorted(options.items())],
        }
