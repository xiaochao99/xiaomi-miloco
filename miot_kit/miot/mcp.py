# -*- coding: utf-8 -*-
# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
"""
MCP server.
"""
import json
import logging
import time
from typing import Annotated, Any, Callable, Coroutine, Dict, Generic, List, Optional, TypeVar, Union
from pydantic import BaseModel, Field

from fastmcp.exceptions import ToolError
from fastmcp import FastMCP, Client
from fastmcp.tools import Tool
from fastmcp.prompts import Prompt, PromptMessage
from fastmcp.resources import Resource
from mcp.types import TextContent
from mcp import ClientSession

from .spec import MIoTSpecDeviceLite, MIoTSpecParser
from .types import HAAutomationInfo, MIoTActionParam, MIoTDeviceInfo, MIoTGetPropertyParam, MIoTHomeInfo, MIoTManualSceneInfo, MIoTSetPropertyParam

_LOGGER = logging.getLogger(__name__)


class _BaseMcpInterface(BaseModel):
    """Base MCP interface."""
    # pylint: disable=pointless-string-statement
    """
    example:
        async def translate_async(
            domain: str,
            key: str,
            replace: Optional[Dict[str, str]] = None,
            default: Union[str, Dict, None] = None
        ) -> Union[str, Dict, None]:
    """
    translate_async: Callable[
        [str, str, Optional[Dict[str, str]], Union[str, Dict, None]],
        Coroutine[Any, Any, Union[str, Dict, None]]
    ]


T = TypeVar("T", bound=_BaseMcpInterface)


class _BaseMcp(Generic[T]):
    """MCP base model."""
    _TRANSLATE_DOMAIN: str = "mcp"
    _MCP_PATH: str = "/mcp"
    _MCP_TAG: str = "mcp_base"
    _mcp: FastMCP
    _interface: T

    _i18n_data: Optional[Dict]
    _name_default: Optional[str]
    _instructions_default: Optional[str]

    def __init__(
        self, interface: T, name: Optional[str] = None, instructions: Optional[str] = None
    ) -> None:
        """Init."""
        self._interface = interface
        self._i18n_data = None
        self._name_default = name or "MCP Server"
        self._instructions_default = instructions or "Provide some tools, prompts and resources."

    async def init_async(self) -> None:
        """Init."""
        data = await self._interface.translate_async(self._TRANSLATE_DOMAIN, self._MCP_TAG, None, None)
        if isinstance(data, Dict | None):
            self._i18n_data = data
        self._mcp = FastMCP(
            name=self.translate(key="name", default=self._name_default),
            instructions=self.translate(key="instructions", default=self._instructions_default),
            on_duplicate="replace",
            mask_error_details=True,          # only error messages from ToolError will include details
        )

    async def deinit_async(self) -> None:
        self._i18n_data = None
        self._mcp = None    # type: ignore

    @property
    def mcp_instance(self) -> FastMCP:
        """MCP Instance."""
        return self._mcp

    @property
    def mcp_client(self) -> Client:
        """MCP Client."""
        return Client(self._mcp)

    @property
    def mcp_session(self) -> ClientSession:
        """MCP Client Session."""
        return Client(self._mcp).session

    async def run_http_async(self, host: Optional[str] = None, port: Optional[int] = None):
        """Start MCP server."""
        await self._mcp.run_http_async(transport="streamable-http", host=host, port=port, path=self._MCP_PATH)

    def translate(
        self, key: str, replace: Optional[Dict[str, str]] = None, default: Optional[str] = None
    ) -> Optional[str]:
        if not self._i18n_data:
            return default
        result = self._i18n_data
        for item in key.split("."):
            if item not in result:
                return default
            result = result[item]
        if isinstance(result, str):
            if replace:
                for k, v in replace.items():
                    result = result.replace("{{"+k+"}}", str(v))
            return result
        return default

    def add_tool(
        self,
        fn: Callable[..., Any],
        name: str,
        description_default: str,
        replace_default: Optional[Dict[str, str]] = None
    ) -> Tool:
        """Add tool."""
        tool = Tool.from_function(
            fn=fn,
            name=name,
            tags=set([self._MCP_TAG]),
            description=self.translate(
                key=f"tools.{name}.description",
                default=description_default,
                replace=replace_default
            )
        )
        # Replace param description.
        # TODO: Pydantic format
        if "properties" in tool.parameters:
            for params_name, param in tool.parameters["properties"].items():
                param_desc = self.translate(key=f"tools.{name}.params.{params_name}")
                if param_desc:
                    param["description"] = param_desc
        # Replace output description.
        if tool.output_schema is not None:
            if "x-fastmcp-wrap-result" in tool.output_schema and "properties" in tool.output_schema:
                pass
            elif "additionalProperties" in tool.output_schema:
                pass

        _LOGGER.info("Add tool params: %s", json.dumps(tool.parameters, ensure_ascii=False))
        _LOGGER.info("Add tool output: %s", json.dumps(tool.output_schema, ensure_ascii=False))
        return self._mcp.add_tool(tool=tool)

    def add_prompt(
        self,
        fn: Callable[..., Any],
        name: str,
        description_default: str,
        replace_default: Optional[Dict[str, str]] = None
    ) -> Prompt:
        """Add prompt."""
        prompt = Prompt.from_function(
            fn=fn,
            name=name,
            tags=set([self._MCP_TAG]),
            description=self.translate(
                key=f"prompts.{name}.description",
                default=description_default,
                replace=replace_default
            )
        )
        return self._mcp.add_prompt(prompt=prompt)

    def add_resource(
        self,
        fn: Callable[..., Any],
        uri: str,
        name: str,
        description_default: str,
        replace_default: Optional[Dict[str, str]] = None
    ) -> Resource:
        """Add resource."""
        resource = Resource.from_function(
            fn=fn,
            uri=uri,
            name=name,
            tags=set([self._MCP_TAG]),
            description=self.translate(
                key=f"resources.{name}.description",
                default=description_default,
                replace=replace_default
            )
        )
        return self._mcp.add_resource(resource=resource)


class McpMIoTManualScene(BaseModel):
    """MIoT manual scene."""
    scene_id: str = Field(description="Manual scene id")
    scene_name: str = Field(description="Manual scene name")
    state: bool = Field(description="Manual scene state")


class MIoTManualSceneMcpInterface(_BaseMcpInterface):
    """Manual scene config."""
    # pylint: disable=pointless-string-statement

    get_manual_scenes_async: Callable[..., Coroutine[Any, Any, Dict[str, MIoTManualSceneInfo]]]

    """
    example:
        async def get_manual_scenes_async() -> Dict[str, MIoTManualSceneInfo]:
    """

    trigger_manual_scene_async: Callable[[MIoTManualSceneInfo], Coroutine[Any, Any, bool]]

    """
    example:
        async def trigger_manual_scene_async(scene_info: MIoTManualSceneInfo) -> bool:
    """

    send_app_notify_async: Callable[[str], Coroutine[Any, Any, bool]]

    """
    example:
        async def send_app_notify_async(notify_content: str) -> bool:
    """


class MIoTManualSceneMcp(_BaseMcp[MIoTManualSceneMcpInterface]):
    """MIoT MCP server."""
    _MCP_PATH: str = "/mcp"
    _MCP_TAG: str = "miot_manual_scenes"
    _TOOL_NAME_GET_SCENES: str = "get_manual_scenes"
    _TOOL_NAME_TRIGGER_SCENE: str = "trigger_manual_scene"
    _TOOL_NAME_SEND_NOTIFY: str = "send_app_notify"

    # manual scene buffer.
    _manual_scene: Dict[str, MIoTManualSceneInfo]

    def __init__(
        self, interface: MIoTManualSceneMcpInterface
    ) -> None:
        super().__init__(
            interface=interface,
            name="Xiaomi Home Manual Scene MCP Server",
            instructions="Support querying and triggering Xiaomi Home manual scenes."
        )
        self._manual_scene = {}

    async def init_async(self) -> None:
        """Init."""
        await super().init_async()
        # get manual scenes.
        self.add_tool(
            fn=self.get_manual_scenes_async,
            name=self._TOOL_NAME_GET_SCENES,
            description_default="Get Xiaomi Home manual scene list."
        )
        # trigger manual scene.
        self.add_tool(
            fn=self.trigger_manual_scene_async,
            name=self._TOOL_NAME_TRIGGER_SCENE,
            description_default="Trigger a Xiaomi Home manual scene."
        )
        # send app notify.
        self.add_tool(
            fn=self.send_app_notify_async,
            name=self._TOOL_NAME_SEND_NOTIFY,
            description_default="Send a notify to Xiaomi Home app."
        )

    async def get_manual_scenes_async(
        self
    ) -> List[McpMIoTManualScene]:
        """Get the manual scene list."""
        # if not self._manual_scene:
        self._manual_scene = await self._interface.get_manual_scenes_async()
        return [
            McpMIoTManualScene(
                scene_id=scene.scene_id,
                scene_name=scene.scene_name,
                state=True,
            ) for scene in self._manual_scene.values()]

    async def trigger_manual_scene_async(
        self, scene_id: Annotated[str, "Manual scene(automation) id"]
    ) -> bool:
        """Trigger manual scene."""
        if scene_id not in self._manual_scene:
            _LOGGER.warning("the scene_id does not exist, %s", scene_id)
            raise ToolError(
                self.translate(
                    key="errors.invalid_scene_id",
                    replace={"scene_id": scene_id},
                    default=(
                        f"The scene_id ({scene_id}) does not exist. Please use the tool `get_manual_scenes` to "
                        "obtain the correct scene_id and continue."
                    )
                )
            )
        return await self._interface.trigger_manual_scene_async(self._manual_scene[scene_id])

    async def send_app_notify_async(
        self, content: Annotated[str, "Notify content"]
    ) -> bool:
        """Send app notify."""
        return await self._interface.send_app_notify_async(content)


class McpMIoTAreaInfo(BaseModel):
    """MIoT area info for MCP."""
    area_id: str = Field(description="Area ID")
    area_name: str = Field(description="Area name")


class McpMIoTDeviceInfo(BaseModel):
    """MIoT device info for MCP."""
    did: str = Field(description="Device ID")
    name: str = Field(description="Device name")
    online: bool = Field(description="Device online state")
    home_info: str = Field(description="Device home and room info")
    device_class: str = Field(description="Device class")


class MIoTDeviceMcpInterface(_BaseMcpInterface):
    """MIoT device MCP Interface."""
    # pylint: disable=pointless-string-statement
    get_homes_async: Callable[..., Coroutine[Any, Any, Dict[str, MIoTHomeInfo]]]

    """
    example:
        async def get_homes_async() -> Dict[str, MIoTHomeInfo]:
            pass
    """

    get_devices_async: Callable[..., Coroutine[Any, Any, Dict[str, MIoTDeviceInfo]]]

    """
    example:
        async def get_devices_async() -> Dict[str, MIoTDeviceInfo]:
            pass
    """

    set_prop_async: Callable[[MIoTSetPropertyParam], Coroutine[Any, Any, Dict]]

    """
    example:
        async def set_prop_async(did: str, siid: int, piid: int, value: Any) -> Dict:
            pass
    """

    get_prop_async: Callable[[MIoTGetPropertyParam], Coroutine[Any, Any, Any]]

    """
    example:
        async def get_prop_async(did: str, siid: int, piid: int) -> Any:
            pass
    """

    action_async: Callable[[MIoTActionParam], Coroutine[Any, Any, Dict]]

    """
    example:
        async def action_async(did: str, siid: int, aiid: int, in_list: List[Any]) -> Dict:
            pass
    """

    get_props_async: Callable[[List[MIoTGetPropertyParam]], Coroutine[Any, Any, List]]

    """
    example:
        async def get_props_async(params: List[MIoTGetPropertyParam]) -> List:
            pass
    """

    set_props_async: Callable[[List[MIoTSetPropertyParam]], Coroutine[Any, Any, List]]

    """
    example:
        async def set_props_async(params: List[MIoTSetPropertyParam]) -> List:
            pass
    """


class MIoTDeviceMcp(_BaseMcp[MIoTDeviceMcpInterface]):
    """MIoT MCP server."""
    _MCP_PATH: str = "/mcp"
    _MCP_TAG: str = "miot_devices"
    _TOOL_NAME_GET_AREA_INFO: str = "get_area_info"
    _TOOL_NAME_GET_DEVICE_CLASSES: str = "get_device_classes"
    _TOOL_NAME_GET_DEVICES: str = "get_devices"
    _TOOL_NAME_GET_DEVICE_SPEC: str = "get_device_spec"
    _TOOL_NAME_SEND_CTRL_RPC: str = "send_ctrl_rpc"
    _TOOL_NAME_SEND_GET_RPC: str = "send_get_rpc"
    _TOOL_NAME_AUTO_CTRL: str = "auto_ctrl_device"
    _TOOL_NAME_AUTO_GET: str = "auto_get_device_prop"
    _TOOL_NAME_BATCH_GET_PROPS: str = "batch_get_props"
    _TOOL_NAME_BATCH_SET_PROPS: str = "batch_set_props"
    _PROMPT_NAME_SEND_CTRL_RPC: str = "prompt_send_ctrl_rpc"
    _PROMPT_NAME_SEND_GET_RPC: str = "prompt_send_get_rpc"
    _spec_parser: MIoTSpecParser
    _mcp: FastMCP
    _prompt_device_count_max: int

    # manual scene buffer.
    _devices: Dict[str, MIoTDeviceInfo]
    _with_extra_info: bool
    # urn: spec_lite.
    _spec_lite_buffer: Dict[str, Dict[str, MIoTSpecDeviceLite]]

    # Device list cache TTL in seconds
    _DEVICES_CACHE_TTL: float = 60.0
    _devices_cache_time: float = 0

    def __init__(
        self,
        interface: MIoTDeviceMcpInterface,
        spec_parser: MIoTSpecParser,
        prompt_device_count_max: int = 20
    ) -> None:
        super().__init__(
            interface=interface,
            name="Xiaomi Home Device Control MCP Server",
            instructions="Support querying and controlling Xiaomi Home devices."
        )
        self._spec_parser = spec_parser
        self._prompt_device_count_max = prompt_device_count_max
        self._devices = {}
        self._with_extra_info = False
        self._spec_lite_buffer = {}

    async def init_async(self) -> None:
        """Init."""
        await super().init_async()
        extra_device_infos: Optional[str] = None
        try:
            self._devices = await self._interface.get_devices_async()
            self._with_extra_info = len(self._devices) > self._prompt_device_count_max
            if self._with_extra_info:
                areas = await self.get_area_info_async()
                device_classes = set([device.model.split(".")[1] for device in self._devices.values()])
                extra_device_infos = self.translate(
                    key="extra.device_infos",
                    replace={
                        "extra_area_infos": "\n"+"\n".join(
                            [f"- {area.area_id}: {area.area_name}" for area in areas.values()]
                        ),
                        "extra_device_classes": "\n"+"\n".join(
                            ["- " + device_cls for device_cls in device_classes]
                        ),
                    }
                )
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.warning("miot device mcp init error, %s", err)
            self._devices = {}
            self._with_extra_info = False
        # add tools.
        # get homes.
        self.add_tool(
            fn=self.get_area_info_async,
            name=self._TOOL_NAME_GET_AREA_INFO,
            description_default="Get Xiaomi Home area(home or room) list."
        )
        # get device class.
        self.add_tool(
            fn=self.get_device_classes_async,
            name=self._TOOL_NAME_GET_DEVICE_CLASSES,
            description_default="Get supported Xiaomi Home device class list."
        )
        # get devices.
        self.add_tool(
            fn=self.get_devices_async if self._with_extra_info else self.get_all_devices_async,
            name=self._TOOL_NAME_GET_DEVICES,
            description_default="Get Xiaomi Home device list.",
            replace_default={
                "extra_device_params": self.translate(key="extra.device_params") or "" if self._with_extra_info else "",
                "extra_device_infos": extra_device_infos or "",
            }
        )
        # get device spec.
        self.add_tool(
            fn=self.get_device_spec_async,
            name=self._TOOL_NAME_GET_DEVICE_SPEC,
            description_default="Get Xiaomi Home device SPEC definition."
        )
        # send ctrl rpc.
        self.add_tool(
            fn=self.send_ctrl_rpc_async,
            name=self._TOOL_NAME_SEND_CTRL_RPC,
            description_default="Control a Xiaomi Home device, support prop and action type SPEC instance iid.",
            replace_default={
                "tool_name_get_devices": self._TOOL_NAME_GET_DEVICES,
                "tool_name_get_device_spec": self._TOOL_NAME_GET_DEVICE_SPEC,
                "tool_name_send_ctrl_rpc": self._TOOL_NAME_SEND_CTRL_RPC
            }
        )
        # send get rpc.
        self.add_tool(
            fn=self.send_get_rpc_async,
            name=self._TOOL_NAME_SEND_GET_RPC,
            description_default="Get a Xiaomi Home device status, only support prop type SPEC instance iid.",
            replace_default={
                "tool_name_get_devices": self._TOOL_NAME_GET_DEVICES,
                "tool_name_get_device_spec": self._TOOL_NAME_GET_DEVICE_SPEC,
                "tool_name_send_get_rpc": self._TOOL_NAME_SEND_GET_RPC
            }
        )
        # auto ctrl device (combined: auto-fetches SPEC + controls)
        self.add_tool(
            fn=self.auto_ctrl_device_async,
            name=self._TOOL_NAME_AUTO_CTRL,
            description_default="Control a Xiaomi Home device by property name. Automatically fetches SPEC and finds the correct iid. Use this to skip the get_device_spec step."
        )
        # auto get device prop (combined: auto-fetches SPEC + queries)
        self.add_tool(
            fn=self.auto_get_device_prop_async,
            name=self._TOOL_NAME_AUTO_GET,
            description_default="Get a Xiaomi Home device property value by name. Automatically fetches SPEC and finds the correct iid. Use this to skip the get_device_spec step."
        )
        # batch get props
        self.add_tool(
            fn=self.batch_get_props_async,
            name=self._TOOL_NAME_BATCH_GET_PROPS,
            description_default="Batch get multiple device properties in a single request. More efficient than calling send_get_rpc multiple times."
        )
        # batch set props
        self.add_tool(
            fn=self.batch_set_props_async,
            name=self._TOOL_NAME_BATCH_SET_PROPS,
            description_default="Batch set multiple device properties in a single request. More efficient than calling send_ctrl_rpc multiple times."
        )
        # add prompts.
        # send ctrl rpc prompt.
        self.add_prompt(
            fn=self.__prompt_send_ctrl_rpc_async,
            name=self._PROMPT_NAME_SEND_CTRL_RPC,
            description_default="Template for controlling Xiaomi Home devices."
        )
        # send get rpc prompt.
        self.add_prompt(
            fn=self.__prompt_send_get_rpc_async,
            name=self._PROMPT_NAME_SEND_GET_RPC,
            description_default="Template for getting Xiaomi Home device properties."
        )

    async def get_area_info_async(self) -> Dict[str, McpMIoTAreaInfo]:
        """Get area(home or room) info, ONLY show the area with devices."""
        await self._ensure_devices_loaded()
        homes = await self._interface.get_homes_async()
        result: Dict[str, McpMIoTAreaInfo] = {}
        for home_id, home in homes.items():
            area_name = home.home_name or self.translate(
                key=f"tools.{self._TOOL_NAME_GET_AREA_INFO}.home_name_default") or "Xiaomi Home"
            if home.dids:
                result[home_id] = McpMIoTAreaInfo(area_id=home_id, area_name=area_name)
            for room_id, room in home.room_list.items():
                if room.dids:
                    result[room_id] = McpMIoTAreaInfo(area_id=room_id, area_name=f"{area_name}-{room.room_name}")

        return result

    async def get_device_classes_async(self) -> Dict[str, str]:
        """Get device class (uses cache with 60s TTL)."""
        await self._ensure_devices_loaded()
        result: Dict[str, str] = {}
        for device in self._devices.values():
            device_class = device.model.split(".")[1]
            result[device_class] = device_class
        return result

    async def _ensure_devices_loaded(self) -> None:
        """Load devices from interface if cache is stale."""
        now = time.monotonic()
        if self._devices and (now - self._devices_cache_time) < self._DEVICES_CACHE_TTL:
            return
        self._devices = await self._interface.get_devices_async()
        self._devices_cache_time = now

    async def get_devices_async(
        self,
        area_id: Annotated[Optional[str], Field(description="Area Id(Home or room id), optional")] = None,
        device_class: Annotated[Optional[str], Field(description="Device class, optional")] = None,
    ) -> Dict[str, McpMIoTDeviceInfo]:
        """Get device list (uses cache with 60s TTL)."""
        await self._ensure_devices_loaded()
        result = {
            did: McpMIoTDeviceInfo(
                did=did,
                name=device.name,
                online=device.online,
                home_info=f"{device.home_name}-{device.room_name}",
                device_class=device.model.split(".")[1],
            ) for did, device in self._devices.items()
            if (not area_id or device.room_id == area_id)
            and (not device_class or device.model.split(".")[1] == device_class)
        }
        if not result:
            if area_id and device_class:
                _LOGGER.warning(
                    "No controllable device found, please confirm whether there is a device of type %s in area %s",
                    device_class, area_id
                )
                raise ToolError(self.translate(
                    key="errors.invalid_area_id_and_device_class",
                    replace={"area_id": area_id, "device_class": device_class},
                    default=(
                        "No controllable device found, please confirm whether there is a device of type "
                        f"{device_class} in area {area_id}"
                    )
                ))
            elif area_id:
                _LOGGER.warning(
                    "No controllable device found, please confirm whether the device exists in the area %s", area_id
                )
                raise ToolError(self.translate(
                    key="errors.invalid_area_id",
                    replace={"area_id": area_id},
                    default=(
                        "No controllable device found, please confirm whether the device exists "
                        f"in the area ({area_id})"
                    )
                ))
            elif device_class:
                _LOGGER.warning(
                    "No controllable device found, please confirm whether there is a device of type %s", device_class
                )
                raise ToolError(self.translate(
                    key="errors.invalid_device_class",
                    replace={"device_class": device_class},
                    default=(
                        "No controllable device found, please confirm whether there is a device of "
                        f"type ({device_class})"
                    )
                ))
            _LOGGER.warning("No controllable device found, please import the device and continue")
            raise ToolError(self.translate(
                key="errors.empty_devices",
                default="No controllable device found, please import the device and continue"
            ))

        return result

    async def get_all_devices_async(self) -> Dict[str, McpMIoTDeviceInfo]:
        """Get all device list."""
        return await self.get_devices_async()

    async def get_device_spec_async(
        self, did: Annotated[str, "Device id"]
    ) -> Dict[str, MIoTSpecDeviceLite]:
        """Get the device spec."""
        if did not in self._devices:
            _LOGGER.warning("The device does not exist, %s", did)
            raise ToolError(self.translate(
                key="errors.spec_invalid_devices",
                replace={"did": did},
                default=(
                    f"The device ({did}) does not exist. Please use the tool `get_devices` to obtain the "
                    "correct device ID before continuing."
                )
            ))

        if self._devices[did].urn in self._spec_lite_buffer:
            return self._spec_lite_buffer[self._devices[did].urn]

        spec_lite = await self._spec_parser.parse_lite_async(urn=self._devices[did].urn)
        if not spec_lite:
            _LOGGER.warning("Failed to obtain device %s SPEC function definition", did)
            raise ToolError(self.translate(
                key="errors.spec_get_failed",
                replace={"did": did},
                default=f"Failed to obtain device ({did}) SPEC function definition, please try again"
            ))

        self._spec_lite_buffer[self._devices[did].urn] = spec_lite
        return spec_lite

    def _validate_spec_iid(self, did: str, iid: str) -> tuple[str, int, int]:
        """Validate and parse SPEC instance id.

        iid must be in the format: ``{cmd}.0.{siid}.{piid}`` e.g. ``prop.0.2.1``
        or ``action.0.3.1``.

        Returns:
            Tuple of (cmd, siid, piid).

        Raises:
            ToolError: If iid format is invalid.
        """
        parts = iid.split(".")
        if len(parts) != 4:
            raise ToolError(self.translate(
                key="errors.invalid_spec_iid",
                replace={"iid": iid},
                default=(
                    f"无效的SPEC实例ID（{iid}），格式必须为 '{{cmd}}.0.{{siid}}.{{piid}}'"
                    "（例如 'prop.0.2.1'），请使用工具 `get_device_spec` 获取正确的SPEC实例ID后继续"
                )
            ))
        cmd, _, siid_str, piid_str = parts
        if cmd not in ("prop", "action"):
            raise ToolError(self.translate(
                key="errors.invalid_spec_iid",
                replace={"iid": iid},
                default=(
                    f"无效的SPEC实例ID（{iid}），命令类型必须为 'prop' 或 'action'，"
                    "请使用工具 `get_device_spec` 获取正确的SPEC实例ID后继续"
                )
            ))
        try:
            siid = int(siid_str)
            piid = int(piid_str)
        except ValueError:
            raise ToolError(self.translate(
                key="errors.invalid_spec_iid",
                replace={"iid": iid},
                default=(
                    f"无效的SPEC实例ID（{iid}），siid和piid必须为整数，"
                    "请使用工具 `get_device_spec` 获取正确的SPEC实例ID后继续"
                )
            ))
        return cmd, siid, piid

    async def send_ctrl_rpc_async(
        self,
        did: Annotated[str, "Device id"],
        iid: Annotated[str, "SPEC instance id"],
        value: Annotated[Union[int, bool, str, float, List], Field(description="SPEC instance value")]
    ) -> bool:
        """Send control cmd rpc."""
        cmd, siid, p_a_aiid = self._validate_spec_iid(did, iid)
        spec: Optional[MIoTSpecDeviceLite] = None
        if did in self._devices:
            # Try to get spec item
            urn: str = self._devices[did].urn
            spec_lite = self._spec_lite_buffer.get(urn, None)
            if not spec_lite:
                spec_lite = await self._spec_parser.parse_lite_async(urn=urn)
                if not spec_lite:
                    _LOGGER.warning("Failed to obtain device %s SPEC function definition", did)
                    raise ToolError(self.translate(
                        key="errors.spec_get_failed",
                        replace={"did": did},
                        default=f"Failed to obtain device ({did}) SPEC function definition, please try again"
                    ))
            spec = spec_lite.get(iid, None)

        if cmd == "prop":
            value_trans: Any = value
            if spec:
                # pylint: disable=broad-exception-caught
                match spec.format:
                    case n if n.startswith(("int", "uint")):
                        # int8, int16, int32, int64
                        # uint8, uint16, uint32, uint64
                        if not isinstance(value, int):
                            try:
                                value_trans = int(value)
                            except Exception:
                                value_trans = None
                    case "float":
                        # float
                        if not isinstance(value, float):
                            try:
                                value_trans = float(value)
                            except Exception:
                                value_trans = None
                    case "string":
                        # string
                        if not isinstance(value, str):
                            try:
                                value_trans = str(value)
                            except Exception:
                                value_trans = None
                    case "bool":
                        # bool
                        if not isinstance(value, bool):
                            if isinstance(value, int):
                                value_trans = value == 1
                            elif isinstance(value, str):
                                value_trans = value.lower() in ["true", "yes", "ok", "1"]
                            else:
                                try:
                                    value_trans = bool(value)
                                except Exception:
                                    value_trans = None
                if value_trans is None:
                    _LOGGER.warning("invalid property value(%s), %s, %s, %s", spec.format, did, iid, value)
                    # TODO: translate
                    raise ToolError("Invalid property value format")
            result = await self._interface.set_prop_async(
                MIoTSetPropertyParam(
                    did=did,
                    siid=int(siid),
                    piid=int(p_a_aiid),
                    value=value_trans
                ))
        elif cmd == "action":
            # TODO: support action
            in_list = []
            if isinstance(value, List):
                in_list = value
            elif isinstance(value, str):
                try:
                    in_list = json.loads(value)
                    if not isinstance(in_list, List):
                        _LOGGER.warning("invalid value format, value must be a array string: %s", iid)
                        raise ToolError(f"invalid value format, value must be a array string: {iid}")
                except Exception:  # pylint: disable=broad-except
                    in_list = [value]
            else:
                _LOGGER.warning("invalid value format, value must be a array string: %s", iid)
                raise ToolError(f"invalid value format, value must be a array string: {iid}")
            result = await self._interface.action_async(
                MIoTActionParam(
                    did=did,
                    siid=int(siid),
                    aiid=int(p_a_aiid),
                    in_=in_list
                ))
        else:
            _LOGGER.warning("Invalid SPEC instance ID, %s", iid)
            raise ToolError(self.translate(
                key="errors.invalid_spec_iid",
                replace={"iid": iid},
                default=(
                    f"Invalid SPEC instance ID ({iid}), please use the tool `get_device_spec` to obtain the "
                    "correct SPEC instance ID before continuing."
                )
            ))
        _LOGGER.info("send control rpc: %s, %s, %s -> %s", did, iid, value, result)
        if not result:
            _LOGGER.warning("Device %s control failed, no response", did)
            raise ToolError(self.translate(
                key="errors.ctrl_without_response",
                replace={"did": did},
                default=f"Device ({did}) control failed, no response, please try again"
            ))
        # TODO: Cloud error code translate
        if "code" not in result or result["code"] not in [0, 1]:
            _LOGGER.warning("Device %s control failed, %s", did, json.dumps(result))
            raise ToolError(self.translate(
                key="errors.ctrl_failed",
                replace={"did": did, "err_msg": json.dumps(result)},
                default=f"Device ({did}) control failed, {json.dumps(result)}"
            ))

        return True

    async def send_get_rpc_async(
        self,
        did: Annotated[str, "Device id"],
        iid: Annotated[str, "SPEC instance id"]
    ) -> Union[int, bool, str, float, None]:
        """Send get prop rpc."""
        cmd, siid, piid = self._validate_spec_iid(did, iid)
        if cmd != "prop":
            _LOGGER.warning("Getting properties only supports SPEC instances of `prop` class, %s, %s", did, iid)
            raise ToolError(self.translate(
                key="errors.spec_only_allow_prop",
                default="Getting properties only supports SPEC instances of `prop` class"
            ))
        result = await self._interface.get_prop_async(MIoTGetPropertyParam(did=did,  siid=siid, piid=piid))
        _LOGGER.info("send get rpc: %s, %s -> %s", did, iid, result)
        return result

    # Common property name aliases (Chinese → English keywords for matching)
    _PROP_ALIASES: Dict[str, List[str]] = {
        "温度": ["temperature", "temp", "当前温度"],
        "湿度": ["humidity", "humid", "当前湿度"],
        "亮度": ["brightness", "luminance", "light"],
        "开关": ["switch", "on", "power", "状态"],
        "色温": ["color_temperature", "color temp"],
        "电量": ["battery", "soc"],
        "功率": ["power", "watt", "watts"],
        "电压": ["voltage"],
        "电流": ["current"],
        "PM2.5": ["pm2.5", "pm25", "pm_2_5"],
        "CO2": ["co2", "carbon_dioxide"],
        "甲醛": ["hcho", "formaldehyde"],
        "噪音": ["noise", "sound"],
        "光照度": ["illumination", "lux"],
    }

    def _find_prop_iid_from_spec(
        self, spec: Dict[str, MIoTSpecDeviceLite], prop_name: str
    ) -> Optional[str]:
        """Find property iid from spec by name with alias support."""
        prop_name_lower = prop_name.lower()
        
        # Get aliases for this property name
        aliases = self._PROP_ALIASES.get(prop_name, [prop_name_lower])
        if prop_name_lower not in [a.lower() for a in aliases]:
            aliases.append(prop_name_lower)
        
        # Pass 1: exact substring match
        for iid, item in spec.items():
            if not iid.startswith("prop."):
                continue
            item_desc = (item.description or "").lower()
            for alias in aliases:
                alias_lower = alias.lower()
                if alias_lower in item_desc or item_desc in alias_lower:
                    return iid
        
        # Pass 2: word boundary match (for partial matches like "temp" in "temperature")
        for iid, item in spec.items():
            if not iid.startswith("prop."):
                continue
            item_desc = (item.description or "").lower()
            for alias in aliases:
                alias_lower = alias.lower()
                # Check if any word in the description starts with the alias
                for word in item_desc.split():
                    if word.startswith(alias_lower) or alias_lower.startswith(word):
                        return iid
        
        return None

    def _find_action_iid_from_spec(
        self, spec: Dict[str, MIoTSpecDeviceLite], action_name: str
    ) -> Optional[str]:
        """Find action iid from spec by name with alias support."""
        action_name_lower = action_name.lower()
        for iid, item in spec.items():
            if not iid.startswith("action."):
                continue
            item_desc = (item.description or "").lower()
            # Exact substring match
            if action_name_lower in item_desc or item_desc in action_name_lower:
                return iid
            # Word boundary match
            for word in item_desc.split():
                if word.startswith(action_name_lower) or action_name_lower.startswith(word):
                    return iid
        return None

    async def auto_ctrl_device_async(
        self,
        did: Annotated[str, "Device id"],
        prop_name: Annotated[str, "Property or action name to control (e.g. 'switch', 'brightness', 'on')"],
        value: Annotated[Union[int, bool, str, float, List], Field(description="Control value")]
    ) -> bool:
        """Control a device by property name. Automatically fetches SPEC, finds the iid, and sends the control command.
        Use this instead of calling get_device_spec + send_ctrl_rpc separately — it saves one LLM round-trip.
        """
        # Ensure devices loaded
        await self._ensure_devices_loaded()
        if did not in self._devices:
            raise ToolError(f"Device {did} not found. Use get_devices to find the correct device id.")

        # Get or cache spec
        urn = self._devices[did].urn
        spec = self._spec_lite_buffer.get(urn)
        if not spec:
            spec = await self._spec_parser.parse_lite_async(urn=urn)
            if not spec:
                raise ToolError(f"Failed to get SPEC for device {did}")
            self._spec_lite_buffer[urn] = spec

        # Try to find as property first, then as action
        iid = self._find_prop_iid_from_spec(spec, prop_name)
        if iid:
            return await self.send_ctrl_rpc_async(did=did, iid=iid, value=value)

        iid = self._find_action_iid_from_spec(spec, prop_name)
        if iid:
            return await self.send_ctrl_rpc_async(did=did, iid=iid, value=value)

        # List available props for helpful error
        available = [
            f"{item.description} ({iid})" for iid, item in spec.items()
            if iid.startswith("prop.") or iid.startswith("action.")
        ]
        raise ToolError(
            f"Cannot find property/action '{prop_name}' in device {did} SPEC. "
            f"Available: {', '.join(available[:10])}"
        )

    async def auto_get_device_prop_async(
        self,
        did: Annotated[str, "Device id"],
        prop_name: Annotated[str, "Property name to query (e.g. 'temperature', 'humidity', 'brightness')"]
    ) -> Union[int, bool, str, float, None]:
        """Get a device property value by name. Automatically fetches SPEC, finds the iid, and queries the value.
        Use this instead of calling get_device_spec + send_get_rpc separately — it saves one LLM round-trip.
        """
        await self._ensure_devices_loaded()
        if did not in self._devices:
            raise ToolError(f"Device {did} not found. Use get_devices to find the correct device id.")

        urn = self._devices[did].urn
        spec = self._spec_lite_buffer.get(urn)
        if not spec:
            spec = await self._spec_parser.parse_lite_async(urn=urn)
            if not spec:
                raise ToolError(f"Failed to get SPEC for device {did}")
            self._spec_lite_buffer[urn] = spec

        iid = self._find_prop_iid_from_spec(spec, prop_name)
        if not iid:
            available = [
                f"{item.description} ({iid})" for iid, item in spec.items()
                if iid.startswith("prop.")
            ]
            raise ToolError(
                f"Cannot find property '{prop_name}' in device {did} SPEC. "
                f"Available properties: {', '.join(available[:10])}. "
                f"TIP: If this device is also connected to Home Assistant, "
                f"use ha_devices___send_get_rpc with the HA entity_id instead."
            )
        return await self.send_get_rpc_async(did=did, iid=iid)

    async def batch_get_props_async(
        self,
        props: Annotated[List[Dict[str, Any]], Field(description="List of {did, siid, piid} objects to query")]
    ) -> List[Dict[str, Any]]:
        """Batch get multiple device properties in a single HTTP request.
        More efficient than calling send_get_rpc multiple times.
        Each item: {"did": "device_id", "siid": 2, "piid": 1}
        """
        params = [MIoTGetPropertyParam(**p) for p in props]
        results = await self._interface.get_props_async(params)
        return results

    async def batch_set_props_async(
        self,
        props: Annotated[List[Dict[str, Any]], Field(
            description="List of {did, siid, piid, value} objects to set"
        )]
    ) -> List[Dict[str, Any]]:
        """Batch set multiple device properties in a single HTTP request.
        More efficient than calling send_ctrl_rpc multiple times.
        Each item: {"did": "device_id", "siid": 2, "piid": 1, "value": true}
        """
        params = [MIoTSetPropertyParam(**p) for p in props]
        results = await self._interface.set_props_async(params)
        return results

    async def __prompt_send_ctrl_rpc_async(self) -> PromptMessage:
        """Send control rpc prompt."""
        await self._ensure_devices_loaded()
        with_extra_info = len(self._devices) > self._prompt_device_count_max
        extra_device_infos: Optional[str] = None
        if with_extra_info:
            areas = await self.get_area_info_async()
            device_classes = set([device.model.split(".")[1] for device in self._devices.values()])
            extra_device_infos = self.translate(
                key="extra.device_infos",
                replace={
                    "extra_area_infos": "\n"+"\n".join(
                        [f"- {area.area_id}: {area.area_name}" for area in areas.values()]),
                    "extra_device_classes": "\n"+"\n".join(
                        ["- " + device_cls for device_cls in device_classes]),
                }
            )

        prompt_content = self.translate(
            key=f"prompts.{self._PROMPT_NAME_SEND_CTRL_RPC}.content",
            replace={
                "extra_device_infos": extra_device_infos or "",
                "extra_device_params": self.translate(key="extra.device_params") or "" if with_extra_info else "",
                "tool_name_get_devices": self._TOOL_NAME_GET_DEVICES,
                "tool_name_get_device_spec": self._TOOL_NAME_GET_DEVICE_SPEC,
                "tool_name_send_ctrl_rpc": self._TOOL_NAME_SEND_CTRL_RPC
            }
        )
        if not prompt_content:
            _LOGGER.warning("prompt content not found")
            raise ToolError("prompt content not found")

        return PromptMessage(role="assistant", content=TextContent(type="text", text=prompt_content))

    async def __prompt_send_get_rpc_async(self) -> PromptMessage:
        """Send get rpc prompt."""
        await self._ensure_devices_loaded()
        with_extra_info = len(self._devices) > self._prompt_device_count_max
        extra_device_infos: Optional[str] = None
        if with_extra_info:
            areas = await self.get_area_info_async()
            device_classes = set([device.model.split(".")[1] for device in self._devices.values()])
            extra_device_infos = self.translate(
                key="extra.device_infos",
                replace={
                    "extra_area_infos": "\n"+"\n".join(
                        [f"- {area.area_id}: {area.area_name}" for area in areas.values()]),
                    "extra_device_classes": "\n"+"\n".join(
                        ["- " + device_cls for device_cls in device_classes]),
                }
            )

        prompt_content = self.translate(
            key=f"prompts.{self._PROMPT_NAME_SEND_GET_RPC}.content",
            replace={
                "extra_device_infos": extra_device_infos or "",
                "extra_device_params": self.translate(key="extra.device_params") or "" if with_extra_info else "",
                "tool_name_get_devices": self._TOOL_NAME_GET_DEVICES,
                "tool_name_get_device_spec": self._TOOL_NAME_GET_DEVICE_SPEC,
                "tool_name_send_ctrl_rpc": self._TOOL_NAME_SEND_CTRL_RPC
            }
        )
        if not prompt_content:
            _LOGGER.warning("prompt content not found")
            raise ToolError("prompt content not found")

        return PromptMessage(role="assistant", content=TextContent(type="text", text=prompt_content))


class MIoTCameraMcp:
    """MIoT Camera MCP server."""
    _MCP_PATH: str = "/mcp"

    def __init__(self) -> None:
        pass


class McpHAAutomation(BaseModel):
    """Home Assistant automation (scene)."""
    automation_id: str = Field(description="Automation (Scene) id")
    automation_name: str = Field(description="Automation (Scene) name")
    state: bool = Field(description="Automation (Scene) state")


class HomeAssistantAutomationMcpInterface(_BaseMcpInterface):
    """Home Assistant automation (scene) interface."""
    get_automations_async: Callable[[], Coroutine[Any, Any, Dict[str, HAAutomationInfo]]]

    """
    example:
        async def get_automations_async() -> Dict[str, HAAutomationInfo]:
            pass
    """

    trigger_automation_async: Callable[[str | HAAutomationInfo], Coroutine[Any, Any, bool]]

    """
    example:
        async def trigger_automation_async(automation: str | HAAutomationInfo) -> bool:
            pass
    """


class HomeAssistantAutomationMcp(_BaseMcp[HomeAssistantAutomationMcpInterface]):
    """Home Assistant MCP server."""
    _MCP_PATH: str = "/mcp"
    _MCP_TAG: str = "ha_automations"
    _TOOL_NAME_GET_AUTOMATIONS: str = "get_automations"
    _TOOL_NAME_TRIGGER_AUTOMATION: str = "trigger_automation"
    _mcp: FastMCP

    # scene buffer.
    _automations: Dict[str, HAAutomationInfo]

    def __init__(
        self, interface: HomeAssistantAutomationMcpInterface
    ) -> None:
        super().__init__(
            interface=interface,
            name="Home Assistant automation MCP Server",
            instructions="Support querying and triggering Home Assistant automations (scenes)."
        )
        self._automations = {}

    async def init_async(self) -> None:
        """Init."""
        await super().init_async()
        # get automations.
        self.add_tool(
            fn=self.get_automations_async,
            name=self._TOOL_NAME_GET_AUTOMATIONS,
            description_default="Get Home Assistant automation(scene) list."
        )
        # trigger automation.
        self.add_tool(
            fn=self.trigger_automation_async,
            name=self._TOOL_NAME_TRIGGER_AUTOMATION,
            description_default="Trigger a Home Assistant automation (scene)."
        )

    async def get_automations_async(
        self
    ) -> List[McpHAAutomation]:
        """Get the automation list."""
        self._automations = await self._interface.get_automations_async()
        return [
            McpHAAutomation(
                automation_id=scene.entity_id,
                automation_name=scene.friendly_name,
                state=scene.state.lower() in ["on", "true", "yes"],
            ) for scene in self._automations.values()]

    async def trigger_automation_async(
        self, automation_id: Annotated[str, "Automation (scene) id"]
    ) -> bool:
        """Trigger automation."""
        if automation_id not in self._automations:
            _LOGGER.warning("the scene was not found, %s", automation_id)
            raise ToolError(self.translate(
                key="error.invalid_automation_id",
                replace={"automation_id": automation_id},
                default=(
                    f"The scene ({automation_id}) was not found. Please use the tool `get_automations` to "
                    "obtain the correct scene ID and continue."
                )
            ))
        return await self._interface.trigger_automation_async(automation_id)


class McpHADeviceInfo(BaseModel):
    """Home Assistant device info for MCP."""
    entity_id: str = Field(description="Device ID (Entity ID)")
    name: str = Field(description="Device name")
    state: str = Field(description="Device state")
    area: str = Field(description="Device area")
    domain: str = Field(description="Device domain")


class McpHADeviceSpecLite(BaseModel):
    """Home Assistant device spec lite."""
    iid: str = Field(description="Entity ID")
    description: str = Field(description="Service name")
    format: str = Field(description="Service domain")
    writeable: bool = Field(description="Writeable")
    readable: bool = Field(description="Readable")
    unit: Optional[str] = Field(default=None, description="Unit")


class HomeAssistantDeviceMcpInterface(_BaseMcpInterface):
    """Home Assistant device MCP Interface."""
    # pylint: disable=pointless-string-statement
    get_devices_async: Callable[[], Coroutine[Any, Any, List[McpHADeviceInfo]]]

    """
    example:
        async def get_devices_async() -> List[McpHADeviceInfo]:
            pass
    """

    control_device_async: Callable[[str, str, str, Optional[Dict[str, Any]]], Coroutine[Any, Any, bool]]

    """
    example:
        async def control_device_async(
            entity_id: str, domain: str, service: str, service_data: Optional[Dict[str, Any]]
        ) -> bool:
            pass
    """


class HomeAssistantDeviceMcp(_BaseMcp[HomeAssistantDeviceMcpInterface]):
    """Home Assistant Device MCP server."""
    _MCP_PATH: str = "/mcp"
    _MCP_TAG: str = "ha_devices"
    _TOOL_NAME_GET_AREA_INFO: str = "get_area_info"
    _TOOL_NAME_GET_DEVICE_CLASSES: str = "get_device_classes"
    _TOOL_NAME_GET_DEVICES: str = "get_devices"
    _TOOL_NAME_GET_DEVICE_SPEC: str = "get_device_spec"
    _TOOL_NAME_SEND_CTRL_RPC: str = "send_ctrl_rpc"
    _TOOL_NAME_SEND_GET_RPC: str = "send_get_rpc"
    _mcp: FastMCP

    _DEVICES_CACHE_TTL: float = 60.0
    _devices_cache_time: float = 0
    _devices_cache: Optional[List[McpHADeviceInfo]] = None

    def __init__(
        self, interface: HomeAssistantDeviceMcpInterface
    ) -> None:
        super().__init__(
            interface=interface,
            name="Home Assistant Device MCP Server",
            instructions="Support querying and controlling Home Assistant devices."
        )

    async def _ensure_devices_loaded(self) -> List[McpHADeviceInfo]:
        """Load devices from interface if cache is stale."""
        now = time.monotonic()
        if self._devices_cache is not None and (now - self._devices_cache_time) < self._DEVICES_CACHE_TTL:
            return self._devices_cache
        self._devices_cache = await self._interface.get_devices_async()
        self._devices_cache_time = now
        return self._devices_cache

    async def init_async(self) -> None:
        """Init."""
        await super().init_async()
        # get area info.
        self.add_tool(
            fn=self.get_area_info_async,
            name=self._TOOL_NAME_GET_AREA_INFO,
            description_default="Get Home Assistant area list."
        )
        # get device classes.
        self.add_tool(
            fn=self.get_device_classes_async,
            name=self._TOOL_NAME_GET_DEVICE_CLASSES,
            description_default="Get supported Home Assistant device class list."
        )
        # get devices.
        self.add_tool(
            fn=self.get_devices_async,
            name=self._TOOL_NAME_GET_DEVICES,
            description_default="Get Home Assistant device list."
        )
        # get device spec.
        self.add_tool(
            fn=self.get_device_spec_async,
            name=self._TOOL_NAME_GET_DEVICE_SPEC,
            description_default="Get Home Assistant device SPEC definition."
        )
        # send ctrl rpc.
        self.add_tool(
            fn=self.send_ctrl_rpc_async,
            name=self._TOOL_NAME_SEND_CTRL_RPC,
            description_default="Control a Home Assistant device, support domain and service.",
            replace_default={
                "tool_name_get_devices": self._TOOL_NAME_GET_DEVICES,
                "tool_name_get_device_spec": self._TOOL_NAME_GET_DEVICE_SPEC,
                "tool_name_send_ctrl_rpc": self._TOOL_NAME_SEND_CTRL_RPC
            }
        )
        # send get rpc.
        self.add_tool(
            fn=self.send_get_rpc_async,
            name=self._TOOL_NAME_SEND_GET_RPC,
            description_default="Get a Home Assistant device status.",
            replace_default={
                "tool_name_get_devices": self._TOOL_NAME_GET_DEVICES,
                "tool_name_get_device_spec": self._TOOL_NAME_GET_DEVICE_SPEC,
                "tool_name_send_get_rpc": self._TOOL_NAME_SEND_GET_RPC
            }
        )
        # batch get states
        self.add_tool(
            fn=self.batch_get_states_async,
            name="batch_get_states",
            description_default="Batch get multiple HA device states in one call. More efficient than calling send_get_rpc multiple times."
        )
        # batch control devices
        self.add_tool(
            fn=self.batch_control_devices_async,
            name="batch_control_devices",
            description_default="Batch control multiple HA devices in one call. More efficient than calling send_ctrl_rpc multiple times."
        )

    async def get_area_info_async(self) -> Dict[str, Any]:
        """Get the area list."""
        devices = await self._ensure_devices_loaded()
        areas = {}
        for device in devices:
            if device.area and device.area.strip():
                # Create area info to match miot format
                areas[device.area] = {
                    "area_id": device.area,
                    "area_name": device.area
                }
        return areas

    async def get_device_classes_async(self) -> Dict[str, str]:
        """Get the device class list."""
        devices = await self._ensure_devices_loaded()
        domains = {}
        for device in devices:
            if device.domain and device.domain.strip():
                domains[device.domain] = device.domain
        return domains

    async def get_devices_async(self) -> List[McpHADeviceInfo]:
        """Get the device list."""
        return await self._ensure_devices_loaded()

    async def get_device_spec_async(self, entity_id: str) -> Dict[str, Any]:
        """Get device spec definition."""
        devices = await self._ensure_devices_loaded()
        for device in devices:
            if device.entity_id == entity_id:
                # Create a basic spec with control service info
                spec = {
                    "iid": device.entity_id,
                    "description": device.name,
                    "format": device.domain,
                    "writeable": True,  # HA devices are generally controllable
                    "readable": True,   # HA devices can report state
                    "unit": None
                }
                return {device.entity_id: spec}
        return {}

    async def send_ctrl_rpc_async(
        self,
        entity_id: Annotated[str, "Entity ID"],
        domain: Annotated[str, "Service Domain (e.g. light, switch)"],
        service: Annotated[str, "Service Name (e.g. turn_on, turn_off)"],
        service_data: Annotated[Optional[Dict[str, Any]], "Service Data (JSON)"] = None
    ) -> bool:
        """Control device."""
        if service_data is None:
            service_data = {}
        return await self._interface.control_device_async(entity_id, domain, service, service_data)

    async def send_get_rpc_async(
        self,
        entity_id: Annotated[str, "Entity ID"]
    ) -> Dict[str, Any]:
        """Get device status."""
        devices = await self._ensure_devices_loaded()
        for device in devices:
            if device.entity_id == entity_id:
                return {
                    "entity_id": device.entity_id,
                    "state": device.state
                }
        return {}

    async def batch_get_states_async(
        self,
        entity_ids: Annotated[List[str], Field(description="List of entity IDs to query")]
    ) -> List[Dict[str, Any]]:
        """Batch get multiple device states from the cached device list.
        More efficient than calling send_get_rpc multiple times.
        """
        devices = await self._ensure_devices_loaded()
        device_map = {d.entity_id: d for d in devices}
        results = []
        for eid in entity_ids:
            if eid in device_map:
                d = device_map[eid]
                results.append({
                    "entity_id": d.entity_id,
                    "name": d.name,
                    "state": d.state,
                    "domain": d.domain,
                    "area": d.area,
                })
            else:
                results.append({"entity_id": eid, "error": "not found"})
        return results

    async def batch_control_devices_async(
        self,
        controls: Annotated[List[Dict[str, Any]], Field(
            description="List of {entity_id, domain, service, service_data?} objects"
        )]
    ) -> List[Dict[str, Any]]:
        """Batch control multiple HA devices in sequence.
        Each item: {"entity_id": "light.living_room", "domain": "light", "service": "turn_on"}
        """
        results = []
        for ctrl in controls:
            eid = ctrl.get("entity_id", "")
            domain = ctrl.get("domain", "")
            service = ctrl.get("service", "")
            service_data = ctrl.get("service_data")
            try:
                ok = await self._interface.control_device_async(eid, domain, service, service_data)
                results.append({"entity_id": eid, "success": ok})
            except Exception as e:  # pylint: disable=broad-except
                results.append({"entity_id": eid, "success": False, "error": str(e)})
        return results
