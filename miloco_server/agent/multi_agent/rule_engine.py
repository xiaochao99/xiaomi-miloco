# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Rule Engine Module

轻量级规则引擎 - 处理简单任务，无需LLM调用

优势:
1. 毫秒级响应
2. 结果确定性强，无幻觉风险
3. 资源消耗极低
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Callable, Awaitable
from enum import Enum, auto

logger = logging.getLogger(__name__)


class RuleAction(Enum):
    """规则动作类型"""
    DEVICE_CONTROL = auto()
    DEVICE_QUERY = auto()
    CHAT = auto()
    VISION = auto()
    AUTOMATION = auto()
    CUSTOM = auto()


@dataclass
class RuleMatchResult:
    """规则匹配结果"""
    rule_name: str
    action: RuleAction
    confidence: float
    extracted_entities: Dict[str, Any] = field(default_factory=dict)
    tool_name: Optional[str] = None
    tool_params: Optional[Dict[str, Any]] = None
    response_template: Optional[str] = None


@dataclass
class Rule:
    """规则定义"""
    name: str
    pattern: str
    action: RuleAction
    priority: int = 0
    tool_name: Optional[str] = None
    tool_params_template: Optional[Dict[str, Any]] = None
    response_template: Optional[str] = None
    entity_extractors: Optional[Dict[str, str]] = None
    conditions: Optional[List[Callable[[Dict[str, Any]], bool]]] = None
    description: str = ""

    def match(self, query: str) -> Optional[Dict[str, Any]]:
        match = re.search(self.pattern, query, re.IGNORECASE)
        if not match:
            return None

        entities = {}
        if self.entity_extractors:
            for entity_name, extractor_pattern in self.entity_extractors.items():
                entity_match = re.search(extractor_pattern, query, re.IGNORECASE)
                if entity_match:
                    entities[entity_name] = entity_match.group(1) if entity_match.lastindex else entity_match.group(0)

        for group_name, group_value in match.groupdict().items():
            if group_value:
                entities[group_name] = group_value

        return entities


class RuleEngine:
    """
    规则引擎 - AHAA架构的快速响应层

    处理简单的、高频的任务，避免不必要的LLM调用。

    用法:
        engine = RuleEngine()
        result = await engine.match("开灯")
        if result:
            print(result.action, result.tool_name)
    """

    def __init__(self):
        self._rules: List[Rule] = []
        self._custom_handlers: Dict[str, Callable[..., Awaitable[Optional[str]]]] = {}
        self._load_default_rules()
        logger.info(f"RuleEngine initialized with {len(self._rules)} rules")

    def _load_default_rules(self) -> None:
        self._rules = [
            Rule(
                name="turn_on_light",
                pattern=r"(?:打开|开|开启)\s*(?P<location>.*?)\s*(?:的)?\s*(?:灯|照明|灯光)",
                action=RuleAction.DEVICE_CONTROL,
                priority=10,
                tool_name="send_ctrl_rpc",
                tool_params_template={"action": "turn_on", "device_type": "light", "location": "{location}"},
                response_template="好的，已为您打开{location}的灯",
                description="开灯指令",
            ),
            Rule(
                name="turn_off_light",
                pattern=r"(?:关闭|关|关掉)\s*(?P<location>.*?)\s*(?:的)?\s*(?:灯|照明|灯光)",
                action=RuleAction.DEVICE_CONTROL,
                priority=10,
                tool_name="send_ctrl_rpc",
                tool_params_template={"action": "turn_off", "device_type": "light", "location": "{location}"},
                response_template="好的，已为您关闭{location}的灯",
                description="关灯指令",
            ),
            Rule(
                name="turn_on_ac",
                pattern=r"(?:打开|开|开启)\s*(?P<location>.*?)\s*(?:的)?\s*(?:空调|冷气|暖气)",
                action=RuleAction.DEVICE_CONTROL,
                priority=10,
                tool_name="send_ctrl_rpc",
                tool_params_template={"action": "turn_on", "device_type": "ac", "location": "{location}"},
                response_template="好的，已为您打开{location}的空调",
                description="开空调指令",
            ),
            Rule(
                name="turn_off_ac",
                pattern=r"(?:关闭|关|关掉)\s*(?P<location>.*?)\s*(?:的)?\s*(?:空调|冷气|暖气)",
                action=RuleAction.DEVICE_CONTROL,
                priority=10,
                tool_name="send_ctrl_rpc",
                tool_params_template={"action": "turn_off", "device_type": "ac", "location": "{location}"},
                response_template="好的，已为您关闭{location}的空调",
                description="关空调指令",
            ),
            Rule(
                name="set_temperature",
                pattern=r"(?:把|将)?\s*(?P<location>.*?)\s*(?:的)?\s*(?:空调|温度)\s*(?:调|设置|设定)\s*(?:到|成|为)?\s*(?P<temperature>\d+)\s*(?:度|℃|°)",
                action=RuleAction.DEVICE_CONTROL,
                priority=9,
                tool_name="send_ctrl_rpc",
                tool_params_template={"action": "set_temperature", "device_type": "ac", "location": "{location}", "temperature": "{temperature}"},
                response_template="好的，已将{location}的空调温度设置为{temperature}度",
                description="设置空调温度",
            ),
            Rule(
                name="query_temperature",
                pattern=r"(?P<location>.*?)\s*(?:的)?\s*(?:温度|气温)\s*(?:是多少|多少|几度|什么)",
                action=RuleAction.DEVICE_QUERY,
                priority=5,
                tool_name="send_get_rpc",
                tool_params_template={"property": "temperature", "location": "{location}"},
                response_template="{location}的当前温度为{value}°C",
                description="查询温度",
            ),
            Rule(
                name="query_humidity",
                pattern=r"(?P<location>.*?)\s*(?:的)?\s*(?:湿度)\s*(?:是多少|多少|几)",
                action=RuleAction.DEVICE_QUERY,
                priority=5,
                tool_name="send_get_rpc",
                tool_params_template={"property": "humidity", "location": "{location}"},
                response_template="{location}的当前湿度为{value}%",
                description="查询湿度",
            ),
            Rule(
                name="query_device_status",
                pattern=r"(?P<location>.*?)\s*(?:的)?\s*(?P<device_type>灯|空调|窗帘|风扇|净化器)\s*(?:开着吗|开着没|状态|情况)",
                action=RuleAction.DEVICE_QUERY,
                priority=5,
                tool_name="send_get_rpc",
                tool_params_template={"property": "status", "location": "{location}", "device_type": "{device_type}"},
                response_template="{location}的{device_type}当前状态: {value}",
                description="查询设备状态",
            ),
            Rule(
                name="open_curtain",
                pattern=r"(?:打开|开|拉开)\s*(?P<location>.*?)\s*(?:的)?\s*(?:窗帘|帘子)",
                action=RuleAction.DEVICE_CONTROL,
                priority=8,
                tool_name="send_ctrl_rpc",
                tool_params_template={"action": "open", "device_type": "curtain", "location": "{location}"},
                response_template="好的，已为您打开{location}的窗帘",
                description="打开窗帘",
            ),
            Rule(
                name="close_curtain",
                pattern=r"(?:关闭|关|拉上)\s*(?P<location>.*?)\s*(?:的)?\s*(?:窗帘|帘子)",
                action=RuleAction.DEVICE_CONTROL,
                priority=8,
                tool_name="send_ctrl_rpc",
                tool_params_template={"action": "close", "device_type": "curtain", "location": "{location}"},
                response_template="好的，已为您关闭{location}的窗帘",
                description="关闭窗帘",
            ),
            Rule(
                name="greeting",
                pattern=r"^(?:你好|hi|hello|嗨|哈喽|早|早上好|晚上好|下午好)",
                action=RuleAction.CHAT,
                priority=1,
                response_template="你好！我是小米智能助手，有什么可以帮您的吗？",
                description="问候语",
            ),
            Rule(
                name="thanks",
                pattern=r"^(?:谢谢|感谢|多谢|thanks|thank)",
                action=RuleAction.CHAT,
                priority=1,
                response_template="不客气！如果还有其他需要，随时告诉我。",
                description="感谢语",
            ),
            Rule(
                name="look_camera",
                pattern=r"(?:看看|查看|看一下)\s*(?P<location>.*?)\s*(?:的)?\s*(?:摄像头|监控|画面|情况)",
                action=RuleAction.VISION,
                priority=7,
                tool_name="vision_understand",
                tool_params_template={"location": "{location}", "question": "描述当前画面"},
                response_template="正在为您查看{location}的画面",
                description="查看摄像头画面",
            ),
            Rule(
                name="who_at_door",
                pattern=r"(?:门口|门外)\s*(?:有)?\s*(?:谁|什么人|人)",
                action=RuleAction.VISION,
                priority=7,
                tool_name="vision_understand",
                tool_params_template={"location": "门口", "question": "门口有谁？"},
                response_template="正在为您查看门口情况",
                description="查看门口来人",
            ),
        ]

    def register_rule(self, rule: Rule) -> None:
        self._rules.append(rule)
        self._rules.sort(key=lambda r: -r.priority)
        logger.info(f"Registered rule: {rule.name}")

    def register_custom_handler(
        self, action_name: str, handler: Callable[..., Awaitable[Optional[str]]]
    ) -> None:
        self._custom_handlers[action_name] = handler
        logger.info(f"Registered custom handler: {action_name}")

    async def match(self, query: str) -> Optional[RuleMatchResult]:
        for rule in self._rules:
            entities = rule.match(query)
            if entities is None:
                continue

            if rule.conditions:
                context = {"query": query, **entities}
                if not all(cond(context) for cond in rule.conditions):
                    continue

            tool_params = None
            if rule.tool_params_template:
                tool_params = {}
                for k, v in rule.tool_params_template.items():
                    if isinstance(v, str) and v.startswith("{") and v.endswith("}"):
                        entity_key = v[1:-1]
                        tool_params[k] = entities.get(entity_key, v)
                    else:
                        tool_params[k] = v

            response = None
            if rule.response_template:
                try:
                    response = rule.response_template.format(**entities)
                except KeyError as e:
                    logger.warning(f"Rule '{rule.name}' response template missing entity: {e}")
                    response = rule.response_template

            logger.info(f"Rule matched: {rule.name} (confidence=1.0, entities={entities})")

            return RuleMatchResult(
                rule_name=rule.name,
                action=rule.action,
                confidence=1.0,
                extracted_entities=entities,
                tool_name=rule.tool_name,
                tool_params=tool_params,
                response_template=response,
            )

        return None

    async def execute(self, query: str) -> Optional[str]:
        result = await self.match(query)
        if result is None:
            return None

        if result.action == RuleAction.CUSTOM:
            handler = self._custom_handlers.get(result.rule_name)
            if handler:
                return await handler(**result.extracted_entities)
            return None

        if result.response_template and not result.tool_name:
            return result.response_template

        return result.response_template

    def get_rules_summary(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": rule.name,
                "action": rule.action.name,
                "priority": rule.priority,
                "tool": rule.tool_name,
                "description": rule.description,
            }
            for rule in self._rules
        ]
