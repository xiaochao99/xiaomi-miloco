# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
WakeUp Chat Agent
Wakeup scenario specialized dialogue agent for understanding natural language responses
"""

import json
import logging
from typing import Optional, List, Dict, Any, TYPE_CHECKING

from miloco_server.schema.wakeup_schema import (
    WakeUpContext, WakeUpSession,
    IntentResult, ProcessResult,
    IntentType, WakeUpState
)
from miloco_server.schema.trigger_schema import Action

if TYPE_CHECKING:
    from miloco_server.mcp.tool_executor import ToolExecutor

logger = logging.getLogger(__name__)


class WakeUpChatAgent:
    """
    WakeUp Chat Agent

    Responsibilities:
    1. Understand user's natural language response to proactive inquiry
    2. Convert user intent into specific action execution
    3. Generate friendly voice responses
    4. Maintain multi-turn dialogue context
    """

    def __init__(
        self,
        session_id: str,
        context: WakeUpContext,
        llm_proxy=None,
        tool_executor: "ToolExecutor" = None,
        chat_history: Optional[List[Dict[str, str]]] = None
    ):
        self._session_id = session_id
        self._context = context
        self._llm_proxy = llm_proxy
        self._tool_executor = tool_executor
        self._chat_history = chat_history or []
        self._turn_count = 0

        logger.info(
            f"[WakeUp:{self._session_id}] WakeUpChatAgent initialized, "
            f"inquiry: {context.inquiry_content[:30] if context.inquiry_content else 'N/A'}..."
        )

    def set_llm_proxy(self, llm_proxy):
        """Set LLM proxy"""
        self._llm_proxy = llm_proxy

    def set_tool_executor(self, tool_executor: "ToolExecutor"):
        """Set tool executor"""
        self._tool_executor = tool_executor

    async def process(self, user_speech: str) -> ProcessResult:
        """
        Process user's natural language response

        Args:
            user_speech: User speech converted to text

        Returns:
            ProcessResult: Processing result with AI response, executed action, etc.
        """
        self._turn_count += 1
        logger.info(
            f"[WakeUp:{self._session_id}] Processing turn {self._turn_count}: "
            f"{user_speech[:50]}..."
        )

        intent = await self._understand_intent(user_speech)

        if intent.intent == IntentType.AGREE:
            result = await self._handle_agree(intent, user_speech)
        elif intent.intent == IntentType.REFUSE:
            result = await self._handle_refuse(intent, user_speech)
        elif intent.intent == IntentType.MODIFY:
            result = await self._handle_modify(intent, user_speech)
        elif intent.intent == IntentType.DELAY:
            result = await self._handle_delay(intent, user_speech)
        elif intent.intent == IntentType.CLARIFY:
            result = await self._handle_clarify(intent, user_speech)
        else:
            result = await self._handle_other(intent, user_speech)

        self._chat_history.append({
            "role": "user",
            "content": user_speech
        })
        self._chat_history.append({
            "role": "assistant",
            "content": result.response
        })

        return result

    async def _understand_intent(self, user_speech: str) -> IntentResult:
        """
        AI understands user intent

        Uses LLM to analyze user response and determine what user wants
        """

        if not self._llm_proxy:
            logger.warning(f"[WakeUp:{self._session_id}] No LLM proxy, using fallback intent")
            return await self._fallback_intent_understanding(user_speech)

        prompt = self._build_intent_understanding_prompt(user_speech)

        try:
            response = await self._llm_proxy.chat(prompt)
            intent_data = self._parse_intent_response(response)

            return IntentResult(
                intent=intent_data.get("intent", IntentType.UNKNOWN),
                confidence=float(intent_data.get("confidence", 0.5)),
                action_requested=intent_data.get("action_requested"),
                action_parameters=intent_data.get("action_parameters", {}),
                response_to_user=intent_data.get("response_to_user", ""),
                reasoning=intent_data.get("reasoning", "")
            )
        except Exception as e:
            logger.error(f"[WakeUp:{self._session_id}] Intent understanding error: {e}")
            return IntentResult(
                intent=IntentType.UNKNOWN,
                confidence=0.0,
                response_to_user="抱歉，我没有听清楚，您能再说一次吗？"
            )

    async def _fallback_intent_understanding(self, user_speech: str) -> IntentResult:
        """
        Fallback intent understanding when no LLM is available

        Uses keyword matching for basic intent recognition
        """

        user_lower = user_speech.lower().strip()

        agree_keywords = ["好", "行", "可以", "是", "要", "开", "执行", "好", "嗯", "对", "打开", "启动", "好嘞", "好呀", "好的"]
        refuse_keywords = ["不", "算", "别", "拒", "否", "不用", "不要", "算了", "不用了", "不需要", "no", "not", "don't"]
        delay_keywords = ["等", "先", "稍", "回头", "回来", "等会", "等等", "待会", "等一下", "稍等"]

        for keyword in agree_keywords:
            if keyword in user_lower and not any(r in user_lower for r in refuse_keywords):
                return IntentResult(
                    intent=IntentType.AGREE,
                    confidence=0.7,
                    response_to_user="好的",
                    reasoning=f"关键词匹配同意: {keyword}"
                )

        for keyword in refuse_keywords:
            if keyword in user_lower:
                return IntentResult(
                    intent=IntentType.REFUSE,
                    confidence=0.7,
                    response_to_user="好的，有需要随时叫我",
                    reasoning=f"关键词匹配拒绝: {keyword}"
                )

        for keyword in delay_keywords:
            if keyword in user_lower:
                return IntentResult(
                    intent=IntentType.DELAY,
                    confidence=0.6,
                    response_to_user="好的，那稍后再提醒您",
                    reasoning=f"关键词匹配推迟: {keyword}"
                )

        return IntentResult(
            intent=IntentType.OTHER,
            confidence=0.3,
            response_to_user="抱歉，我没有完全理解，您能再说一次吗？",
            reasoning="无法识别意图"
        )

    def _build_intent_understanding_prompt(self, user_speech: str) -> List[Dict[str, str]]:
        """Build prompt for intent understanding"""

        suggested_options = ""
        if self._context.suggested_actions:
            suggested_options = "建议的操作选项:\n"
            for i, action in enumerate(self._context.suggested_actions, 1):
                suggested_options += f"  {i}. {action}\n"

        available_actions = ""
        if self._context.relevant_data.get("broadcast_text"):
            broadcast_text = self._context.relevant_data.get("broadcast_text", "")
            available_actions = f"当前询问内容: {broadcast_text}\n"

        user_preferences = ""
        if self._context.recent_interactions:
            user_preferences = "\n用户近期选择记录:\n"
            for interaction in self._context.recent_interactions[-3:]:
                user_preferences += f"  - {interaction.get('content', '')}\n"

        system_prompt = f"""你是一个智能家居助手，正在理解用户对【主动询问】的回复。

【当前询问场景】
规则名称: {self._context.rule_name}
刚才询问用户: "{self._context.inquiry_content}"
询问原因: {self._context.inquiry_reason or '需要用户确认或选择'}

{available_actions}

{suggested_options}

{user_preferences}

【用户刚才说】
"{user_speech}"

【理解要求】
1. 准确判断用户的真实意图
2. 即使用户没有直接说"同意"或"拒绝"，也要理解其隐含意图
3. 注意用户的模糊表达，如"好啊"、"算了"、"等等"等
4. 如果用户提出了不同的动作需求，尽量理解并执行

【意图类型定义】
- agree: 用户明确或隐含同意执行建议的操作
- refuse: 用户明确或隐含拒绝，不希望执行任何操作
- modify: 用户想执行类似操作，但想修改参数或替换为其他动作
- delay: 用户希望推迟操作，不立即执行
- clarify: 用户需要更多信息或解释
- other: 其他意图
- unknown: 无法确定用户意图

请以JSON格式回复:
{{
  "intent": "agree|refuse|modify|delay|clarify|other|unknown",
  "confidence": 0.0-1.0,
  "action_requested": "用户想执行的动作描述（如果是refuse则为空）",
  "action_parameters": {{动作参数}},
  "response_to_user": "AI简短回复用户的话（20字以内）",
  "reasoning": "意图判断的理由简述"
}}"""

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"用户回复: {user_speech}"}
        ]

    def _parse_intent_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM intent recognition response"""
        try:
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.startswith("```"):
                response = response[3:]
            if response.endswith("```"):
                response = response[:-3]

            return json.loads(response.strip())
        except json.JSONDecodeError:
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(response[start:end])
                except:
                    pass
            logger.warning(f"[WakeUp:{self._session_id}] Failed to parse intent response")
            return {}

    async def _handle_agree(
        self,
        intent: IntentResult,
        user_speech: str
    ) -> ProcessResult:
        """Handle user agreement"""

        action_to_execute = None

        if intent.action_requested:
            action_to_execute = self._match_action(intent)
        else:
            if self._context.suggested_actions:
                action_to_execute = self._find_action_by_name(
                    self._context.suggested_actions[0]
                )

        if not action_to_execute and self._context.relevant_data.get("automation_actions"):
            automation_actions = self._context.relevant_data.get("automation_actions", [])
            if automation_actions:
                if isinstance(automation_actions[0], dict):
                    action_to_execute = Action(**automation_actions[0])
                elif isinstance(automation_actions[0], Action):
                    action_to_execute = automation_actions[0]

        executed = False
        execution_result_msg = None

        if action_to_execute and self._tool_executor:
            try:
                action_params = intent.action_parameters if intent.action_parameters else {}
                actual_params = {**action_to_execute.mcp_tool_input, **action_params}

                result = await self._tool_executor.execute_tool_by_params(
                    action_to_execute.mcp_client_id,
                    action_to_execute.mcp_tool_name,
                    actual_params
                )
                executed = result.success
                execution_result_msg = action_to_execute.introduction
                logger.info(
                    f"[WakeUp:{self._session_id}] Action executed: "
                    f"{action_to_execute.mcp_tool_name}, success: {executed}"
                )
            except Exception as e:
                logger.error(f"[WakeUp:{self._session_id}] Action execution error: {e}")
                executed = False

        if executed:
            response = intent.response_to_user or f"好的，已执行{execution_result_msg or '操作'}"
        else:
            response = "抱歉，操作执行失败了"

        return ProcessResult(
            response=response,
            action_executed=executed,
            action_name=execution_result_msg,
            action_success=executed,
            should_end=False,
            intent=intent
        )

    async def _handle_refuse(
        self,
        intent: IntentResult,
        user_speech: str
    ) -> ProcessResult:
        """Handle user refusal"""

        logger.info(
            f"[WakeUp:{self._session_id}] User refused, "
            f"reasoning: {intent.reasoning}"
        )

        await self._record_user_preference(
            action=intent.action_requested,
            accepted=False
        )

        response = intent.response_to_user or "好的，有需要随时叫我"

        return ProcessResult(
            response=response,
            action_executed=False,
            action_name=None,
            action_success=None,
            should_end=True,
            intent=intent
        )

    async def _handle_modify(
        self,
        intent: IntentResult,
        user_speech: str
    ) -> ProcessResult:
        """Handle user wanting to modify action or parameters"""

        action_to_execute = self._match_action(intent)

        if not action_to_execute:
            response = intent.response_to_user or "抱歉，我没有理解您的意思，您能再说一次吗？"
            return ProcessResult(
                response=response,
                action_executed=False,
                action_name=None,
                action_success=None,
                should_end=False,
                intent=intent
            )

        executed = False
        try:
            if self._tool_executor:
                action_params = intent.action_parameters if intent.action_parameters else {}
                actual_params = {**action_to_execute.mcp_tool_input, **action_params}

                result = await self._tool_executor.execute_tool_by_params(
                    action_to_execute.mcp_client_id,
                    action_to_execute.mcp_tool_name,
                    actual_params
                )
                executed = result.success
        except Exception as e:
            logger.error(f"[WakeUp:{self._session_id}] Modified action error: {e}")

        response = intent.response_to_user or f"好的，{action_to_execute.introduction}"

        return ProcessResult(
            response=response,
            action_executed=executed,
            action_name=action_to_execute.introduction,
            action_success=executed,
            should_end=False,
            intent=intent
        )

    async def _handle_delay(
        self,
        intent: IntentResult,
        user_speech: str
    ) -> ProcessResult:
        """Handle user wanting to delay"""

        logger.info(f"[WakeUp:{self._session_id}] User wants to delay")

        await self._record_user_preference(
            action=intent.action_requested,
            accepted=False,
            note="用户希望推迟"
        )

        response = intent.response_to_user or "好的，那稍后再提醒您"

        return ProcessResult(
            response=response,
            action_executed=False,
            action_name=None,
            action_success=None,
            should_end=True,
            intent=intent
        )

    async def _handle_clarify(
        self,
        intent: IntentResult,
        user_speech: str
    ) -> ProcessResult:
        """Handle user needing explanation"""

        explanation = self._context.inquiry_reason or "这是根据当前情况系统自动发出的询问"

        response = f"{explanation}，您可以告诉我'好的执行'或者'不用了'"

        return ProcessResult(
            response=response,
            action_executed=False,
            action_name=None,
            action_success=None,
            should_end=False,
            intent=intent
        )

    async def _handle_other(
        self,
        intent: IntentResult,
        user_speech: str
    ) -> ProcessResult:
        """Handle other/unknown intents"""

        if self._turn_count < 3:
            response = "抱歉，我没有完全理解您的意思。您可以简单说'好的执行'或者'不用了'"
        else:
            response = "抱歉，还是没有听清楚，下次再帮您处理"

        return ProcessResult(
            response=response,
            action_executed=False,
            action_name=None,
            action_success=None,
            should_end=True,
            intent=intent
        )

    def _match_action(self, intent: IntentResult) -> Optional[Action]:
        """Match action based on intent description"""

        if not intent.action_requested:
            return None

        action_requested = intent.action_requested.lower()

        actions = self._context.relevant_data.get("automation_actions", [])
        if not actions and hasattr(self._context, 'available_actions'):
            actions = self._context.available_actions

        for action in actions:
            if isinstance(action, dict):
                action_name = action.get("introduction", "").lower()
                action_obj = Action(**action)
            elif isinstance(action, Action):
                action_name = action.introduction.lower()
                action_obj = action
            else:
                continue

            keywords = [k for k in action_name.split() if len(k) > 1]
            match_count = sum(1 for kw in keywords if kw in action_requested)

            if match_count >= max(1, len(keywords) * 0.5):
                if intent.action_parameters:
                    action_obj.mcp_tool_input.update(intent.action_parameters)
                return action_obj

        return None

    def _find_action_by_name(self, name: str) -> Optional[Action]:
        """Find action by name"""

        name_lower = name.lower()

        actions = self._context.relevant_data.get("automation_actions", [])
        if not actions and hasattr(self._context, 'available_actions'):
            actions = self._context.available_actions

        for action in actions:
            if isinstance(action, dict):
                action_name = action.get("introduction", "").lower()
                if name_lower in action_name:
                    return Action(**action)
            elif isinstance(action, Action):
                if name_lower in action.introduction.lower():
                    return action

        return None

    async def _record_user_preference(
        self,
        action: Optional[str],
        accepted: bool,
        note: str = ""
    ):
        """Record user preference"""

        logger.info(
            f"[WakeUp:{self._session_id}] Recording preference: "
            f"action={action}, accepted={accepted}, note={note}"
        )
