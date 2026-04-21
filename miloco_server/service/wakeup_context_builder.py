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

    def __init__(self, llm_proxy=None, ha_proxy=None, tool_executor=None):
        self._llm_proxy = llm_proxy
        self._ha_proxy = ha_proxy
        self._tool_executor = tool_executor

    def set_llm_proxy(self, llm_proxy):
        """Set LLM proxy for AI decision making"""
        self._llm_proxy = llm_proxy

    def set_ha_proxy(self, ha_proxy):
        """Set HA proxy for device state fetching"""
        self._ha_proxy = ha_proxy

    def set_tool_executor(self, tool_executor):
        """Set tool executor for action execution"""
        self._tool_executor = tool_executor

    async def build_from_rule(
        self,
        rule: TriggerRule,
        trigger_event: Optional[Dict[str, Any]] = None,
        skip_inquiry_decision: bool = False
    ) -> WakeUpContext:
        """
        Build wakeup context from rule and trigger event

        Args:
            rule: Triggered rule
            trigger_event: Trigger event details (optional)
            skip_inquiry_decision: If True, skip AI inquiry decision (for async execution)

        Returns:
            WakeUpContext with all necessary information for AI dialogue
        """

        trigger_info = self._analyze_trigger_source(rule, trigger_event)

        relevant_data = await self._fetch_relevant_data(rule, trigger_info)

        # 检查是否是 MODEL_REPLY 模式
        broadcast_mode = relevant_data.get("broadcast_mode")
        broadcast_text = relevant_data.get("broadcast_text")
        model_reply_content = None

        # 如果是 MODEL_REPLY 模式
        if broadcast_mode and broadcast_mode.lower() == "model_reply":
            # 优先从指定的实体获取数据（最快）
            if rule.execute_info and rule.execute_info.target_entities:
                # 直接从HA获取实体状态（不使用MCP工具）
                entity_states = await self._fetch_entity_states(rule.execute_info.target_entities)
                if entity_states:
                    relevant_data["entity_states"] = entity_states
                    # 将实体状态发送给模型进行智能总结（像智能管家一样组织成一段话）
                    # 如果没有配置问题文本，使用默认指令
                    summary_instruction = broadcast_text if broadcast_text else "播报当前设备状态"
                    model_reply_content = await self._summarize_entity_states(summary_instruction, entity_states)
                    if model_reply_content:
                        relevant_data["model_reply_content"] = model_reply_content
            # 其次使用配置的问题文本
            elif broadcast_text:
                model_reply_content = await self._query_model_for_data(rule, broadcast_text)
                if model_reply_content:
                    relevant_data["model_reply_content"] = model_reply_content
            # 如果没有配置问题文本，尝试执行设备控制动作并获取结果
            elif rule.execute_info and rule.execute_info.automation_actions:
                model_reply_content = await self._execute_actions_for_model_reply(rule)
                if model_reply_content:
                    relevant_data["model_reply_content"] = model_reply_content

        inquiry_decision = InquiryDecision(required=False)

        # 根据模型回复内容（如果有）判断是否需要主动询问
        if not skip_inquiry_decision:
            inquiry_decision = await self._ai_decide_inquiry(
                rule=rule,
                trigger_info=trigger_info,
                relevant_data=relevant_data,
                model_reply_content=model_reply_content
            )

        if inquiry_decision.required:
            inquiry_content = inquiry_decision.content
        else:
            # 如果不需要询问，使用模型回复内容或默认内容
            if model_reply_content:
                inquiry_content = model_reply_content
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

    async def make_inquiry_decision(
        self,
        rule: TriggerRule,
        context: WakeUpContext
    ) -> InquiryDecision:
        """
        Make AI inquiry decision based on model reply content

        Args:
            rule: Triggered rule
            context: WakeUpContext with model reply content

        Returns:
            InquiryDecision with required flag and inquiry content
        """
        trigger_info = TriggerInfo(
            source_type=context.trigger_source,
            description=context.trigger_condition,
            details=context.trigger_details,
            severity=context.trigger_severity
        )

        model_reply_content = context.relevant_data.get("model_reply_content")

        return await self._ai_decide_inquiry(
            rule=rule,
            trigger_info=trigger_info,
            relevant_data=context.relevant_data,
            model_reply_content=model_reply_content
        )

    async def _query_model_for_data(self, rule: TriggerRule, query_text: str) -> Optional[str]:
        """
        调用模型查询实际数据，并将结果发送给模型进行智能总结

        Args:
            rule: 触发规则
            query_text: 查询文本（如"播报室内温度"）

        Returns:
            模型总结后的回复内容
        """
        from miloco_server.service.ai_chat_adapter import APIChatAdapter, parse_ai_response

        request_id = str(uuid.uuid4())
        chat_adapter = APIChatAdapter(request_id)

        # 获取 MCP 服务列表
        mcp_list = rule.execute_info.mcp_list if rule.execute_info and rule.execute_info.mcp_list else None

        # 调用模型查询实际数据
        response_text = ""
        try:
            async for message in chat_adapter.process_query(
                query=query_text,
                camera_ids=[],
                mcp_list=mcp_list
            ):
                if message["type"] == "complete":
                    response_text = message["data"].get("response", "")
                    break
        except Exception as e:
            logger.error(f"[WakeUpContextBuilder] Model query error: {e}")
            return None

        # 提取 <final_answer> 内容
        if response_text:
            parsed_response = parse_ai_response(response_text)
            final_answer = parsed_response.get("final_answer", "").strip()
            if final_answer:
                logger.info(f"[WakeUpContextBuilder] Model query raw result: {final_answer}")
                
                # 将查询结果发送给模型进行智能总结（像智能管家一样组织成一段话）
                summarized_content = await self._summarize_entity_states(query_text, final_answer)
                if summarized_content:
                    logger.info(f"[WakeUpContextBuilder] Model query summarized result: {summarized_content}")
                    return summarized_content
                
                return final_answer

        return None

    async def _fetch_entity_states(self, entity_ids: list[str]) -> Optional[str]:
        """
        直接从HA获取指定实体的状态（最快方式）

        Args:
            entity_ids: HA实体ID列表

        Returns:
            实体状态的自然语言描述，用于播报和AI决策
        """
        if not self._ha_proxy:
            logger.warning("[WakeUpContextBuilder] No HA proxy available")
            return None

        try:
            states = await self._ha_proxy.get_states()
            if not states:
                logger.warning("[WakeUpContextBuilder] Failed to get HA states")
                return None

            entity_results = []
            for entity_id in entity_ids:
                if entity_id in states:
                    state_info = states[entity_id]
                    description = self._format_entity_state(entity_id, state_info)
                    if description:
                        entity_results.append(description)

            if entity_results:
                result_text = "\n".join(entity_results)
                logger.info(f"[WakeUpContextBuilder] Entity states fetched: {result_text}")
                return result_text

        except Exception as e:
            logger.error(f"[WakeUpContextBuilder] Failed to fetch entity states: {e}")

        return None

    def _format_entity_state(self, entity_id: str, state_info: Any) -> str:
        """
        将HA实体状态格式化为自然语言描述

        Args:
            entity_id: 实体ID
            state_info: 实体状态信息（HAStateInfo对象）

        Returns:
            自然语言描述的状态
        """
        # 从entity_id提取设备类型
        domain = entity_id.split(".")[0]
        entity_name = entity_id.split(".")[1].replace("_", " ")

        # 获取状态值 - HAStateInfo是对象，使用属性访问
        state = getattr(state_info, "state", "unknown")
        attributes = getattr(state_info, "attributes", {})

        # 根据不同设备类型格式化输出
        if domain == "sensor":
            # 传感器类型
            unit = attributes.get("unit_of_measurement", "")
            friendly_name = attributes.get("friendly_name", entity_name)
            
            if "temperature" in entity_id.lower():
                return f"{friendly_name}：{state}{unit}"
            elif "humidity" in entity_id.lower():
                return f"{friendly_name}：{state}{unit}"
            elif "illuminance" in entity_id.lower() or "light" in entity_id.lower():
                return f"{friendly_name}：{state}{unit}"
            elif "power" in entity_id.lower() or "energy" in entity_id.lower():
                return f"{friendly_name}：{state}{unit}"
            else:
                return f"{friendly_name}：{state}{unit}"
                
        elif domain == "binary_sensor":
            friendly_name = attributes.get("friendly_name", entity_name)
            if state == "on":
                return f"{friendly_name}：已触发"
            else:
                return f"{friendly_name}：正常"
                
        elif domain == "switch" or domain == "light":
            friendly_name = attributes.get("friendly_name", entity_name)
            if state == "on":
                return f"{friendly_name}：已打开"
            else:
                return f"{friendly_name}：已关闭"
                
        elif domain == "climate":
            friendly_name = attributes.get("friendly_name", entity_name)
            current_temp = attributes.get("current_temperature", "未知")
            target_temp = attributes.get("temperature", "未知")
            hvac_mode = attributes.get("hvac_mode", "未知")
            
            mode_map = {
                "heat": "制热",
                "cool": "制冷",
                "auto": "自动",
                "off": "关闭",
                "fan_only": "送风"
            }
            mode_text = mode_map.get(hvac_mode, hvac_mode)
            
            return f"{friendly_name}：{mode_text}模式，当前温度 {current_temp}°C，目标温度 {target_temp}°C"
            
        else:
            # 默认格式
            friendly_name = attributes.get("friendly_name", entity_name)
            return f"{friendly_name}：{state}"

    async def _summarize_entity_states(self, instruction: str, entity_states: str) -> Optional[str]:
        """
        将实体状态发送给模型进行智能总结

        Args:
            instruction: 用户的问题或指令（如"播报家里的环境信息"）
            entity_states: 实体状态的自然语言描述

        Returns:
            模型总结后的回复内容
        """
        try:
            # 构建总结请求
            summary_prompt = f"""
你是一个智能管家，请根据以下设备状态信息，按照用户的要求进行总结回复。

用户指令：{instruction}

设备状态：
{entity_states}

请将以上信息组织成一段自然、友好的语音播报内容，就像智能管家一样。
"""
            # 调用模型进行总结
            messages = [
                {"role": "system", "content": "你是一个友好的智能管家，善于将设备状态信息总结成自然的语音播报内容。"},
                {"role": "user", "content": summary_prompt}
            ]
            
            result = await self._llm_proxy.async_call_llm(messages)
            if result.get("success"):
                content = result.get("content", "")
                logger.info(f"[WakeUpContextBuilder] Entity states summarized successfully: {content[:50]}...")
                return content.strip()
            else:
                logger.warning(f"[WakeUpContextBuilder] Failed to summarize entity states")
                return entity_states
                
        except Exception as e:
            logger.error(f"[WakeUpContextBuilder] Error summarizing entity states: {str(e)}")
            # 如果模型调用失败，返回原始状态信息
            return entity_states

    async def _execute_actions_for_model_reply(self, rule: TriggerRule) -> Optional[str]:
        """
        执行设备控制动作并获取模型回复内容

        Args:
            rule: 触发规则

        Returns:
            动作执行结果的自然语言描述，用于播报和AI决策
        """
        from miloco_server.schema.mcp_schema import CallToolResult

        if not self._tool_executor:
            logger.warning("[WakeUpContextBuilder] No tool executor available")
            return None

        action_results = []
        for action in rule.execute_info.automation_actions:
            try:
                logger.info(f"[WakeUpContextBuilder] Executing action for model reply: {action.introduction}")
                
                result: CallToolResult = await self._tool_executor.execute_tool_by_params(
                    action.mcp_client_id, action.mcp_tool_name,
                    action.mcp_tool_input)
                
                if result.success and result.response:
                    # 将工具返回结果转换为自然语言描述
                    result_text = self._format_action_result(action, result.response)
                    action_results.append(result_text)
                elif result.error_message:
                    logger.error(f"[WakeUpContextBuilder] Action execution error: {result.error_message}")
                    
            except Exception as e:
                logger.error(f"[WakeUpContextBuilder] Action execution exception: {e}")

        if action_results:
            model_reply_content = "\n".join(action_results)
            logger.info(f"[WakeUpContextBuilder] Actions result for model reply: {model_reply_content}")
            return model_reply_content

        return None

    def _format_action_result(self, action: Any, response: Dict[str, Any]) -> str:
        """
        将工具执行结果格式化为自然语言描述

        Args:
            action: 执行的动作
            response: 工具返回的结果

        Returns:
            自然语言描述的结果
        """
        # 获取动作介绍作为描述基础
        description = action.introduction if hasattr(action, 'introduction') else "执行操作"
        
        # 尝试提取关键信息
        if isinstance(response, dict):
            # 尝试获取温度、湿度等常见传感器数据
            if "temperature" in response:
                return f"{description}结果：温度 {response['temperature']}°C"
            elif "humidity" in response:
                return f"{description}结果：湿度 {response['humidity']}%"
            elif "state" in response:
                return f"{description}结果：{response['state']}"
            elif "result" in response:
                return f"{description}结果：{response['result']}"
            
            # 如果有数值字段，尝试提取
            for key, value in response.items():
                if isinstance(value, (int, float)):
                    return f"{description}结果：{key} = {value}"
        
        # 默认格式
        return f"{description}执行成功"

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
        relevant_data: Dict[str, Any],
        model_reply_content: Optional[str] = None
    ) -> InquiryDecision:
        """
        AI decides whether proactive inquiry is needed

        Key design: AI decides based on complete context,
        not preset rules. If model_reply_content is provided,
        AI will decide based on the model's reply content.
        """

        if not self._llm_proxy:
            logger.warning("[WakeUpContextBuilder] No LLM proxy, using default inquiry")
            return InquiryDecision(
                required=True,
                content="有什么可以帮您的吗？",
                reason="默认询问（无LLM）",
                suggested_actions=["查看状态", "执行操作", "不需要"]
            )

        prompt = self._build_inquiry_decision_prompt(rule, trigger_info, relevant_data, model_reply_content)

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
        relevant_data: Dict[str, Any],
        model_reply_content: Optional[str] = None
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

        # 如果有模型回复内容，优先使用它来判断
        model_reply_section = ""
        if model_reply_content:
            model_reply_section = f"""
【模型查询结果】
{model_reply_content}

请根据模型查询结果判断是否需要主动询问用户。
例如：
- 如果温度过高（>28度）或过低（<18度），询问是否打开空调
- 如果湿度异常，询问是否开启除湿/加湿
- 如果空气质量差，询问是否开启净化器
- 如果数据正常，不需要询问，直接播报即可
"""

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

{model_reply_section}

【决策标准】

需要询问的情况：
1. 模型查询结果显示异常数据，需要用户确认操作（如"温度过高，是否打开空调"）
2. 检测到异常需要用户决策（如"温度过高，是否降温"）
3. 安全相关事件需要用户响应（如"检测到陌生人，是否查看"）
4. 例行提醒需要用户反馈（如"该吃药了，是否已服药"）
5. 用户可能想主动了解情况（如"检测到门口有人，是否查看"）

不需要询问的情况：
1. 模型查询结果数据正常，直接播报即可
2. 紧急安全事件（燃气泄漏、烟雾报警等）→ 应立即执行安全动作
3. 用户明确配置为"静默执行"的规则
4. 纯通知类场景（如"天气预报已更新"）
5. 高频重复性操作（避免骚扰用户）

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
