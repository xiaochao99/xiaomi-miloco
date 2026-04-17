# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
WakeUp Context Builder
Builds wakeup context from trigger rules, AI decides whether inquiry is needed
"""

import json
import logging
import uuid
from typing import Optional, List, Dict, Any

from miloco_server.schema.trigger_schema import (
    TriggerRule, ConditionType, Action, ExecuteInfo
)
from miloco_server.schema.wakeup_schema import (
    WakeUpContext, WakeUpConfig, WakeUpMode,
    TriggerInfo, TriggerSourceType,
    InquiryDecision, InquirySource,
    EnvironmentalData
)

logger = logging.getLogger(__name__)


class WakeUpContextBuilder:
    """
    WakeUp Context Builder

    Responsibilities:
    1. Extract key information from trigger rules
    2. Fetch relevant device/environmental data
    3. AI decides whether proactive inquiry is needed
    4. Generate inquiry content if needed
    """

    def __init__(self, llm_proxy=None, ha_proxy=None):
        self._llm_proxy = llm_proxy
        self._ha_proxy = ha_proxy

    def set_llm_proxy(self, llm_proxy):
        """Set LLM proxy for AI decision making"""
        self._llm_proxy = llm_proxy

    def set_ha_proxy(self, ha_proxy):
        """Set HA proxy for device state fetching"""
        self._ha_proxy = ha_proxy

    async def build_from_rule(
        self,
        rule: TriggerRule,
        trigger_event: Optional[Dict[str, Any]] = None
    ) -> WakeUpContext:
        """
        Build wakeup context from rule and trigger event

        Args:
            rule: Triggered rule
            trigger_event: Trigger event details (optional)

        Returns:
            WakeUpContext with all necessary information for AI dialogue
        """

        trigger_info = self._analyze_trigger_source(rule, trigger_event)

        relevant_data = await self._fetch_relevant_data(rule, trigger_info)

        inquiry_decision = await self._ai_decide_inquiry(
            rule=rule,
            trigger_info=trigger_info,
            relevant_data=relevant_data
        )

        if inquiry_decision.required:
            inquiry_content = inquiry_decision.content
        else:
            inquiry_content = await self._generate_default_content(rule)

        available_actions = self._get_available_actions(rule)
        # Inject available actions into context so WakeUpChatAgent can match/execute them.
        # Must be JSON-serializable because inquiry prompt uses json.dumps(relevant_data).
        if available_actions:
            relevant_data["automation_actions"] = [
                a.model_dump() if hasattr(a, "model_dump") else a for a in available_actions
            ]

        recent_interactions = await self._get_recent_interactions(rule.id)

        return WakeUpContext(
            session_id=str(uuid.uuid4()),
            rule_id=rule.id,
            rule_name=rule.name,
            trigger_condition=trigger_info.description,
            trigger_source=TriggerSourceType(trigger_info.source_type),
            trigger_details=trigger_info.details,
            trigger_severity=trigger_info.severity,
            requires_inquiry=inquiry_decision.required,
            inquiry_content=inquiry_content,
            inquiry_reason=inquiry_decision.reason,
            suggested_actions=inquiry_decision.suggested_actions,
            relevant_data=relevant_data,
            recent_interactions=recent_interactions
        )

    def _analyze_trigger_source(
        self,
        rule: TriggerRule,
        trigger_event: Optional[Dict[str, Any]]
    ) -> TriggerInfo:
        """Analyze trigger source type"""

        source_type = TriggerSourceType.CUSTOM
        description = ""
        details = {}
        severity = "normal"

        if rule.condition_type == ConditionType.DETECTION:
            source_type = TriggerSourceType.DETECTION
            if rule.detection_condition and rule.detection_condition.enabled:
                targets = [t.value for t in rule.detection_condition.targets]
                description = f"检测到{'/'.join(targets)}"
                details = {
                    "targets": targets,
                    "cameras": rule.cameras
                }
                severity = "warning"

        elif rule.ha_devices and len(rule.ha_devices) > 0:
            source_type = TriggerSourceType.DEVICE_STATE
            if trigger_event:
                description = trigger_event.get("description", "设备状态变化")
                details = trigger_event.get("details", {})
                severity = trigger_event.get("severity", "normal")
            else:
                description = rule.condition or "设备状态变化"
                details = {"ha_devices": rule.ha_devices}

        elif rule.condition:
            source_type = TriggerSourceType.CUSTOM
            description = rule.condition
            details = {"condition": rule.condition}

        security_keywords = ["燃气", "烟雾", "入侵", "撬锁", "紧急", "alert", "security", "gas", "smoke"]
        if any(kw in description.lower() for kw in security_keywords):
            severity = "critical"

        return TriggerInfo(
            source_type=source_type,
            description=description,
            details=details,
            severity=severity
        )

    async def _fetch_relevant_data(
        self,
        rule: TriggerRule,
        trigger_info: TriggerInfo
    ) -> Dict[str, Any]:
        """Fetch data relevant to current trigger"""

        data = {}

        if trigger_info.source_type == TriggerSourceType.DEVICE_STATE:
            for device_id in rule.ha_devices or []:
                try:
                    states = await self._get_ha_device_states(device_id)
                    if states:
                        data[device_id] = states
                except Exception as e:
                    logger.warning(f"Failed to fetch HA device {device_id}: {e}")

        elif trigger_info.source_type == TriggerSourceType.DETECTION:
            data["cameras"] = rule.cameras
            data["detection_targets"] = trigger_info.details.get("targets", [])

        env_data = await self._try_fetch_environmental_data(rule)
        if env_data:
            data["environmental"] = env_data

        if rule.execute_info and rule.execute_info.xiaoai_broadcast:
            broadcast = rule.execute_info.xiaoai_broadcast
            data["broadcast_mode"] = broadcast.mode.value
            data["broadcast_text"] = broadcast.text

        return data

    async def _get_ha_device_states(self, device_id: str) -> Optional[List[Dict]]:
        """Get HA device states"""
        if not self._ha_proxy:
            return None

        try:
            if self._ha_proxy.ha_client:
                template = '{{ states|%s }}' % device_id
                result = await self._ha_proxy.ha_client.render_template_async(template)
                if result:
                    return json.loads(result) if isinstance(result, str) else result
        except Exception as e:
            logger.debug(f"Failed to get HA device states for {device_id}: {e}")

        return None

    async def _try_fetch_environmental_data(
        self,
        rule: TriggerRule
    ) -> Optional[Dict[str, Any]]:
        """Try to fetch environmental data (temperature, humidity, etc.)"""

        try:
            env_patterns = ["temperature", "humidity", "air_quality", "pm25", "co2"]

            env_states = {}

            for device_id in rule.ha_devices or []:
                try:
                    states = await self._get_ha_device_states(device_id)
                    if states:
                        for state in states:
                            entity_id = state.get("entity_id", "").lower()
                            for pattern in env_patterns:
                                if pattern in entity_id:
                                    env_states[entity_id] = state.get("state")
                                    break
                except:
                    continue

            return env_states if env_states else None

        except Exception as e:
            logger.debug(f"Failed to fetch environmental data: {e}")
            return None

    async def _ai_decide_inquiry(
        self,
        rule: TriggerRule,
        trigger_info: TriggerInfo,
        relevant_data: Dict[str, Any]
    ) -> InquiryDecision:
        """
        AI decides whether proactive inquiry is needed

        Key design: AI decides based on complete context,
        not preset rules
        """

        if not self._llm_proxy:
            logger.warning("[WakeUpContextBuilder] No LLM proxy, using default inquiry")
            return InquiryDecision(
                required=True,
                content="有什么可以帮您的吗？",
                reason="默认询问（无LLM）",
                suggested_actions=["查看状态", "执行操作", "不需要"]
            )

        prompt = self._build_inquiry_decision_prompt(rule, trigger_info, relevant_data)

        try:
            response = await self._llm_proxy.chat(prompt)
            decision = self._parse_inquiry_decision(response)
            return decision
        except Exception as e:
            logger.error(f"AI inquiry decision error: {e}")
            return InquiryDecision(
                required=True,
                content="有什么可以帮您的吗？",
                reason=f"AI决策出错: {e}",
                suggested_actions=["查看状态", "执行操作", "不需要"]
            )

    def _build_inquiry_decision_prompt(
        self,
        rule: TriggerRule,
        trigger_info: TriggerInfo,
        relevant_data: Dict[str, Any]
    ) -> List[Dict[str, str]]:
        """Build prompt for inquiry decision"""

        broadcast_content = ""
        if rule.execute_info and rule.execute_info.xiaoai_broadcast:
            broadcast = rule.execute_info.xiaoai_broadcast
            if broadcast.text:
                broadcast_content = f"\n用户已配置的播报内容: {broadcast.text}"

        available_actions_desc = ""
        if rule.execute_info:
            if rule.execute_info.automation_actions:
                available_actions_desc = "规则关联的自动化动作:\n"
                for action in rule.execute_info.automation_actions:
                    available_actions_desc += f"  - {action.introduction}\n"
            elif rule.execute_info.ai_recommend_actions:
                available_actions_desc = "AI推荐动作:\n"
                for action in rule.execute_info.ai_recommend_actions:
                    available_actions_desc += f"  - {action.introduction}\n"

        system_prompt = f"""你是一个智能家居决策助手，需要判断当前场景是否需要【主动询问用户】。

【触发规则信息】
规则名称: {rule.name}
触发条件: {rule.condition or '无'}
规则类型: {rule.condition_type.value if rule.condition_type else 'unknown'}

【触发事件】
事件类型: {trigger_info.source_type.value}
事件描述: {trigger_info.description}
严重程度: {trigger_info.severity}
事件详情: {json.dumps(trigger_info.details, ensure_ascii=False, indent=2)}

【相关数据】
{json.dumps(relevant_data, ensure_ascii=False, indent=2)}

{broadcast_content}

{available_actions_desc}

【决策标准】

需要询问的情况：
1. 需要用户确认的操作（如"是否打开空调"）
2. 检测到异常需要用户决策（如"温度过高，是否降温"）
3. 安全相关事件需要用户响应（如"检测到陌生人，是否查看"）
4. 例行提醒需要用户反馈（如"该吃药了，是否已服药"）
5. 用户可能想主动了解情况（如"检测到门口有人，是否查看"）

不需要询问的情况：
1. 紧急安全事件（燃气泄漏、烟雾报警等）→ 应立即执行安全动作
2. 用户明确配置为"静默执行"的规则
3. 纯通知类场景（如"天气预报已更新"）
4. 高频重复性操作（避免骚扰用户）

【输出要求】
请以JSON格式回复：
{{
  "required": true/false,
  "content": "如果需要询问，生成一句自然的询问内容（20字以内）",
  "reason": "判断理由简述",
  "suggested_actions": ["建议选项1", "建议选项2"]
}}"""

        return [{"role": "system", "content": system_prompt}]

    def _parse_inquiry_decision(self, response: str) -> InquiryDecision:
        """Parse AI inquiry decision response"""
        try:
            response = response.strip()

            if response.startswith("```json"):
                response = response[7:]
            if response.startswith("```"):
                response = response[3:]
            if response.endswith("```"):
                response = response[:-3]

            data = json.loads(response)
            return InquiryDecision(
                required=data.get("required", False),
                content=data.get("content", ""),
                reason=data.get("reason", ""),
                suggested_actions=data.get("suggested_actions", [])
            )
        except Exception as e:
            logger.warning(f"Failed to parse inquiry decision: {e}")
            return InquiryDecision(required=False)

    async def _generate_default_content(self, rule: TriggerRule) -> str:
        """Generate default broadcast content when AI decides no inquiry needed"""

        if rule.execute_info and rule.execute_info.xiaoai_broadcast:
            if rule.execute_info.xiaoai_broadcast.text:
                return rule.execute_info.xiaoai_broadcast.text

        return f"{rule.name}已执行"

    def _get_available_actions(self, rule: TriggerRule) -> List[Action]:
        """Get available actions for current rule"""

        actions = []

        if rule.execute_info:
            if rule.execute_info.automation_actions:
                actions.extend(rule.execute_info.automation_actions)
            if rule.execute_info.ai_recommend_actions:
                actions.extend(rule.execute_info.ai_recommend_actions)

        return actions

    async def _get_recent_interactions(
        self,
        rule_id: str,
        limit: int = 5
    ) -> List[Dict[str, str]]:
        """Get recent interaction history for this rule"""

        return []
