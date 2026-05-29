# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Enhanced Chat Agent

Advanced chat agent with AHAA Agent integration.
Features intelligent role management, context-aware responses,
adaptive learning, and robust error handling.
"""

import asyncio
import json
import logging
import re
from typing import AsyncGenerator, Any, ClassVar, Optional, Dict, List
from datetime import datetime

from openai.types.chat import ChatCompletionChunk
from openai.types.chat.chat_completion_chunk import ChoiceDeltaToolCall
from openai.types.chat.chat_completion_message_tool_call import ChatCompletionMessageToolCall
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
from thespian.actors import Actor, ActorAddress, ActorExitRequest

from miloco_server import actor_system
from miloco_server.config import CHAT_CONFIG
from miloco_server.config.prompt_config import PromptType, UserLanguage
from miloco_server.middleware.exceptions import LLMServiceException, ResourceNotFoundException
from miloco_server.schema.chat_history_schema import ChatHistoryMessages
from miloco_server.schema.chat_schema import Dialog, Event, InstructionPayload, Template
from miloco_server.schema.mcp_schema import CallToolResult, LocalMcpClientId
from miloco_server.utils.chat_companion import ChatCachedData
from miloco_server.utils.local_models import ModelPurpose

# Import new framework components
from miloco_server.agent.core import (
    Role, RoleManager, RoleCapability,
    PromptTemplate, PromptContext, template_engine,
    ToolSelector, ToolContext, ToolSelectionStrategy,
    ContextManager, ContextState, context_manager,
    AdaptiveLearner, LearningRecord, adaptive_learner,
    ErrorHandler, FallbackStrategy, error_handler,
    PersonaManager, PersonaSettings, persona_manager,
)

logger = logging.getLogger(__name__)


class EnhancedChatAgent(Actor):
    """
    Enhanced Chat Agent with AHAA Agent Integration
    
    Features:
    - Dynamic role management with capability-based tool assignment
    - Context-aware prompt generation
    - Intelligent tool selection with adaptive learning
    - Comprehensive error handling with fallback strategies
    - Multi-turn conversation support with state tracking
    """

    _local_tools_cache: ClassVar[Optional[List[ChatCompletionToolParam]]] = None

    def __init__(
        self,
        request_id: str,
        out_actor_address: ActorAddress,
        chat_history_messages: Optional[ChatHistoryMessages] = None,
        role_name: Optional[str] = None,
    ):
        """Initialize Enhanced Chat Agent.

        Args:
            request_id: Unique identifier for the request.
            out_actor_address: Address of the output actor.
            chat_history_messages: Optional chat history.
            role_name: Optional role name to use.
        """
        super().__init__()
        from miloco_server.service.manager import get_manager
        self._manager = get_manager()

        self._request_id = request_id
        self._chat_companion = self._manager.chat_companion
        self._llm_proxy = self._manager.get_llm_proxy_by_purpose(ModelPurpose.PLANNING)
        self._language = self._manager.auth_service.get_user_language().language
        self._tool_executor = self._manager.tool_executor
        
        # Initialize role management
        self._role_manager = RoleManager()
        self._role_manager.initialize_default_roles()
        
        if role_name:
            self._active_role = self._role_manager.switch_role(role_name)
        else:
            self._active_role = self._role_manager.get_active_role()
            # If no active role, set default
            if self._active_role is None:
                self._active_role = self._role_manager.switch_role("智能家居助手")
        
        # Initialize context management
        self._context_manager = context_manager
        self._conversation_context = self._context_manager.get_or_create_context(
            request_id,
            role=self._active_role.config.name if self._active_role else None,
            language=self._language,
        )
        
        # Initialize tool selector
        self._tool_selector = ToolSelector(strategy=ToolSelectionStrategy.HYBRID)
        
        # Initialize adaptive learner
        self._adaptive_learner = adaptive_learner
        
        # Initialize error handler
        self._error_handler = error_handler

        self._out_actor_address = out_actor_address
        self._max_steps = CHAT_CONFIG.get("agent_max_steps", 10)

        # Tool metadata
        self._local_default_mcp_tools_meta: List[ChatCompletionToolParam] = []
        self._other_mcp_tools_meta: List[ChatCompletionToolParam] = []
        self._all_mcp_tools_meta: List[ChatCompletionToolParam] = []
        self._selected_tool_names: Optional[List[str]] = None
        self._is_no_tool_query: bool = False
        
        # Track consecutive tool errors to prevent infinite loops
        self._consecutive_tool_errors = 0
        self._max_consecutive_errors = 3
        
        # Track tool execution patterns for step optimization
        self._tool_execution_count = 0
        self._max_tool_executions = 8
        self._completed_tool_chains = 0

        # Track called tools to avoid repeated calls
        self._called_tool_keys: set[str] = set()
        # Track consecutive skipped (repeated) tool calls for early termination
        self._consecutive_skipped_calls = 0
        self._max_consecutive_skips = 2
        # Interactive UI tools that should never be retried —
        # once the user has interacted (or an error occurred), the result is final.
        self._no_retry_tools = {
            "create_rule",
        }
        # Track if we already have a queryable result (e.g., temperature value)
        self._has_query_result = False
        self._last_tool_result_type: Optional[str] = None
        self._current_query: str = ""

        # Track which devices have had their spec retrieved (did → True)
        # Used to enforce the get_devices → get_device_spec → send_ctrl_rpc/send_get_rpc flow
        self._device_spec_retrieved: set[str] = set()
        # Tools that require get_device_spec to be called first
        self._spec_required_tools = {"send_ctrl_rpc", "send_get_rpc"}

        self._init_conversation(chat_history_messages)
        
        # Initialize template engine
        self._init_templates()
        
        # Register tools with selector
        self._init_tool_selector()

        self._chat_companion.set_chat_data(
            self._request_id,
            ChatCachedData(
                out_actor_address=self._out_actor_address,
            ))

        logger.info("[%s] EnhancedChatAgent initialized with role: %s", 
                   self._request_id, 
                   self._active_role.config.name if self._active_role else "default")

    def _init_templates(self) -> None:
        """Initialize prompt templates"""
        template_engine.initialize_default_templates()
        
        # Create role-specific template
        if self._active_role:
            from miloco_server.agent.core.prompt_template import PromptSection
            role_template = PromptTemplate(
                name="dynamic_role_context",
                content=self._active_role.get_system_prompt_additions(),
                section=PromptSection.ROLE,
                priority=95,
            )
            template_engine.register_template(role_template)

    def _init_tool_selector(self) -> None:
        """Initialize tool selector with available tools"""
        self._tool_selector.set_llm_proxy(self._llm_proxy)

    def _set_tools_meta(
        self,
        mcp_list: Optional[list[str]] = None,
        exclude_tool_names: Optional[list[str]] = None,
    ) -> list[ChatCompletionToolParam]:
        """Initialize tool metadata and register with selector.

        Args:
            mcp_list: List of MCP client IDs.
            exclude_tool_names: Tool names to exclude.

        Returns:
            List of chat completion tool parameters.
        """
        if mcp_list is None:
            mcp_list = []

        if EnhancedChatAgent._local_tools_cache is not None:
            self._local_default_mcp_tools_meta = EnhancedChatAgent._local_tools_cache
            logger.debug("[%s] Using cached local default tools (%d tools)",
                        self._request_id, len(self._local_default_mcp_tools_meta))
        else:
            self._local_default_mcp_tools_meta = self._tool_executor.get_mcp_chat_completion_tools(
                mcp_client_ids=[LocalMcpClientId.LOCAL_DEFAULT],
                exclude_tool_names=exclude_tool_names,
            )
            EnhancedChatAgent._local_tools_cache = self._local_default_mcp_tools_meta
            logger.info("[%s] Cached local default tools (%d tools)",
                       self._request_id, len(self._local_default_mcp_tools_meta))

        mcp_list = list(
            filter(lambda x: x != LocalMcpClientId.LOCAL_DEFAULT, mcp_list))

        self._other_mcp_tools_meta = self._tool_executor.get_mcp_chat_completion_tools(
            mcp_list, exclude_tool_names=exclude_tool_names)
        self._all_mcp_tools_meta = self._local_default_mcp_tools_meta + self._other_mcp_tools_meta

        # Register tools with selector
        self._tool_selector.register_tools_from_openai_format(self._all_mcp_tools_meta)
        
        # Filter by role capabilities
        if self._active_role:
            filtered_tools = []
            for tool in self._all_mcp_tools_meta:
                try:
                    # Get function object - could be dict or FunctionDefinition
                    func = None
                    if isinstance(tool, dict):
                        func = tool.get("function")
                    else:
                        # Handle ChatCompletionToolParam / Pydantic models
                        func = getattr(tool, "function", None)
                    
                    # Extract name - handle both dict and FunctionDefinition
                    if func is None:
                        tool_name = ""
                    elif isinstance(func, dict):
                        tool_name = func.get("name", "")
                    else:
                        tool_name = getattr(func, "name", "") or ""
                    
                    if self._active_role.can_use_tool(tool_name):
                        filtered_tools.append(tool)
                except Exception as e:
                    logger.debug("[%s] Failed to filter tool: %s", self._request_id, e)
                    filtered_tools.append(tool)  # Keep tool if filtering fails
            self._all_mcp_tools_meta = filtered_tools

        tool_names = []
        for t in self._all_mcp_tools_meta:
            try:
                # Get function object - could be dict or FunctionDefinition
                func = None
                if isinstance(t, dict):
                    func = t.get("function")
                else:
                    # Handle ChatCompletionToolParam / Pydantic models
                    func = getattr(t, "function", None)
                
                # Extract name - handle both dict and FunctionDefinition
                if func is None:
                    name = "?"
                elif isinstance(func, dict):
                    name = func.get("name", "?")
                else:
                    name = getattr(func, "name", "?") or "?"
                
                tool_names.append(name)
            except Exception as e:
                logger.warning("[%s] Failed to extract tool name: %s", 
                              self._request_id, e)
                tool_names.append("?")
                
        logger.info("[%s] Initialized %d tools: %s", self._request_id,
                    len(self._all_mcp_tools_meta), tool_names)
        
        return self._all_mcp_tools_meta

    def _init_conversation(self, chat_history_messages: Optional[ChatHistoryMessages]) -> None:
        """Initialize conversation history.

        Args:
            chat_history_messages: Chat history messages.
        """
        self._chat_history_messages = (
            chat_history_messages if chat_history_messages is not None
            else ChatHistoryMessages())
        if not self._chat_history_messages.has_initialized():
            system_prompt = self._build_enhanced_system_prompt()
            self._chat_history_messages.add_content("system", system_prompt)

    def _build_enhanced_system_prompt(self) -> str:
        """Build enhanced system prompt using template engine"""
        # Build prompt context
        available_tools = []
        for tool in self._all_mcp_tools_meta:
            try:
                # Get function object - could be dict or FunctionDefinition
                func = None
                if isinstance(tool, dict):
                    func = tool.get("function")
                else:
                    # Handle ChatCompletionToolParam / Pydantic models
                    func = getattr(tool, "function", None)
                
                # Extract name and description - handle both dict and FunctionDefinition
                if func is None:
                    tool_name = ""
                    tool_desc = ""
                elif isinstance(func, dict):
                    tool_name = func.get("name", "")
                    tool_desc = func.get("description", "")
                else:
                    tool_name = getattr(func, "name", "") or ""
                    tool_desc = getattr(func, "description", "") or ""
                
                if tool_name:
                    available_tools.append({"name": tool_name, "description": tool_desc})
            except Exception as e:
                logger.debug("[%s] Failed to extract tool info: %s", self._request_id, e)
        
        # Build role-specific variables
        role_description = ""
        capabilities = []
        preferred_tools = []
        if self._active_role:
            role_description = self._active_role.config.description or ""
            capabilities = [c.name for c in self._active_role.config.capabilities] if self._active_role.config.capabilities else []
            preferred_tools = self._active_role.config.preferred_tools or []
        
        prompt_context = PromptContext(
            user_query="",
            available_tools=available_tools,
            custom_variables={
                "current_time": datetime.now().isoformat(),
                "user_language": self._language,
                "role_description": role_description,
                "capabilities": capabilities,
                "preferred_tools": preferred_tools,
            }
        )
        
        # Compose prompt from templates
        base_prompt = template_engine.compose_prompt(prompt_context)
        
        # Add Persona Settings (Highest Priority)
        persona_additions = self._build_persona_prompt()
        if persona_additions:
            base_prompt = persona_additions + "\n\n" + base_prompt
        
        # Add ReAct workflow instructions
        env_section = self._build_env_context_section()
        react_instructions = f"""
{env_section}
# ReAct工作流 (必须严格遵守)
思考（Think）：首先分析当前的用户需求和已知信息，进行逻辑推理。**这是最重要的一步**。你需要判断：
1. 用户的问题是什么？
2. 是否需要调用工具？为什么？
3. 如果需要调用工具，应该调用哪个工具？
4. 如果不需要工具，应该直接回答什么？

**🔴 无需使用工具的典型场景（必须直接回复，禁止调用工具）：**
- 用户告知/陈述个人信息：如"我的车牌号是...""我住在...""我的手机号是..."
- 简单确认/应答：如"知道了""好的""嗯"
- 闲聊/问候/天气/知识问答等

行动 (Action)：如果思考后确定需要与外部世界交互（查询状态、控制设备等），则生成一个或多个符合OpenAI Tool Calling格式的工具调用。

观察 (Observation)：你会接收到调用工具后返回的结果。你必须基于这个新的信息，回到第1步（思考（Think）），判断是需要继续调用其他工具，还是已经可以提供最终答案。

**⚡ 关键效率规则：如果工具返回的结果已经包含回答用户问题所需的全部信息，必须立即使用 <final_answer> 给出最终答案，不要继续调用任何工具！**

# 设备查询标准流程 (重要 - 严格按此执行)

**查询设备状态（如温度、湿度、亮度等）：**
1. 第1步：调用 `get_devices` 获取目标设备（可带 device_class 或 area_id 过滤）
2. 第2步：用返回的 did 调用 `get_device_spec` 获取设备SPEC定义
3. 第3步：从SPEC定义中找到要查询的属性 iid，调用 `send_get_rpc(did, iid)` 查询具体属性值
4. 第4步：**直接用 <final_answer> 回答用户，不要再调用任何工具**

**控制设备（如开灯、关空调）：**
1. 第1步：调用 `get_devices` 找到目标设备的 did
2. 第2步：用 did 调用 `get_device_spec` 获取设备SPEC定义
3. 第3步：从SPEC定义中找到要控制的属性 iid，调用 `send_ctrl_rpc(did, iid, value)` 执行控制
4. 第4步：**直接用 <final_answer> 告知操作结果**

**示例：用户问"机柜温度"**
- Step 1: 调用 `get_devices(area_id="机柜", device_class="sensor_ht")` → 返回温湿度计 did
- Step 2: 调用 `get_device_spec(did=返回的did)` → 返回SPEC定义，找到温度属性的iid
- Step 3: 调用 `send_get_rpc(did=返回的did, iid=从SPEC获取的iid)` → 返回温度值 24.5
- Step 4: **立即回答**："机柜当前温度为 24.5°C" → <final_answer>结束

**示例：用户问"打开玄关灯"**
- Step 1: 调用 `get_devices(area_id="玄关", device_class="light")` → 返回灯的 did
- Step 2: 调用 `get_device_spec(did=返回的did)` → 返回SPEC定义，找到开关属性的iid
- Step 3: 调用 `send_ctrl_rpc(did=返回的did, iid=从SPEC获取的iid, value=控制值)` → 执行开灯
- Step 4: **立即回答**："已为您打开玄关灯" → <final_answer>结束

**禁止：**
- ❌ 已经拿到温度/湿度等数值后还继续调用 `get_devices`
- ❌ 同一个工具用相同参数重复调用
- ❌ 查询到设备 did 后又重新查询设备列表
- ❌ **跳过 get_device_spec 直接调用 send_get_rpc 或 send_ctrl_rpc（必须先获取SPEC定义才能知道正确的iid）**

# 智能工具选择策略 (Important - AI自主决策)
**工具选择原则：**
- 根据用户意图和对话上下文智能选择工具
- 不要预设只能使用某些工具，所有可用工具都可以根据需要使用
- 优先考虑最直接、最高效的工具

**何时使用工具：**
- 天气信息已在系统提示中提供（见"当前家庭环境上下文"），询问天气/下雨/温度等**直接回答**，不需要调用任何工具
- 环境数据已在系统提示中，**不需要**调用 `get_environment_context`。仅在用户明确要求"最新数据"或需要刷新时才调用，且每轮最多调用1次
- 用户明确要求控制设备（开/关/调节）→ 使用 `send_ctrl_rpc`
- 用户查询设备状态 → 使用 `send_get_rpc`
- 用户需要创建自动化规则 → 使用 `create_rule`
- 涉及图像分析 → 使用 `vision_understand`
- 闲聊、设定角色、日常对话 → **不使用任何工具**

**何时不使用工具：**
- 闲聊、问候、日常对话
- 设定AI角色或用户偏好
- 询问AI的身份或能力
- 用户只是表达情感或想法
- 记忆相关操作（"记住XXX"、"我叫什么"、"我的XXX"等）→ 已由记忆系统自动处理，**绝不调用任何工具**
- 任何可以用已有信息（记忆上下文、对话历史）直接回答的问题 → **绝不调用任何工具**

**关键原则：不必要的情况绝不要调用工具！** 以下情况绝对不要调工具：
- 闲聊、记忆、日常对话
- 已经有足够信息可以回答的问题
- 用户没有明确需要外部数据或设备操作

# 多平台设备查询策略 (Important - 备选方案)
**系统支持两个设备平台：**
- 米家设备控制 (MIoT Device Control) - 前缀: `miot_devices___`
- Home Assistant 设备控制 (HA Devices) - 前缀: `ha_devices___`

**查询设备时的备选策略：**
1. **优先尝试米家平台**：使用 `miot_devices___get_devices` 查询
2. **米家失败时自动切换到HA**：如果米家返回空或错误，立即使用 `ha_devices___get_devices` 查询
3. **控制设备时同样适用**：米家控制失败时，尝试使用HA控制

**示例流程：**
- 用户问"客厅人在状态"
- 第1步：调用 `miot_devices___get_devices` 查询米家设备
- 第2步：如果米家返回"没有找到设备"，立即调用 `ha_devices___get_devices` 查询HA设备
- 第3步：根据HA返回结果查询具体状态

# 错误处理与终止条件 (Critical)
当工具调用返回错误时：
1. **尝试备选平台**：如果是设备查询/控制，先尝试另一个平台（米家↔HA）
2. **不要**盲目尝试其他可能的实体名称
3. **立即停止**：如果所有平台都失败，使用 <final_answer> 标签告知用户无法完成操作
4. **提供建议**：告知用户可能的解决方案

# 禁止行为 (Strictly Forbidden)
- ❌ 闲聊时调用任何工具
- ❌ 设定角色时调用任何工具
- ❌ 用户告知个人信息（如"我的车牌号是..."）时调用任何工具 —— 直接确认即可
- ❌ 用户说"打开灯"时先查询状态再打开
- ❌ 连续多次尝试不同实体名称
- ❌ 一个平台失败后不尝试备选平台就直接放弃
- ❌ 工具返回了完整结果后，继续调用相同工具（vision_understand、get_devices 等单次调用即可完成的工具）

# 输出格式与严格约束 (Strictly Enforced)
- Markdown格式: 所有输出必须使用Markdown格式。
- 思考标签: 思考过程必须且只能被包裹在 <reflect> 和 </reflect> 标签内。
- 最终答案标签: 当你确信已收集到所有必要信息，能够完整回答用户问题时，在最后的 <reflect> </reflect> 之后，必须使用 <final_answer> 和 </final_answer> 标签包裹最终的、面向用户的回复。
- 工具调用格式: 工具调用必须严格遵循OpenAI的Tool Calling格式，并且不能出现在<reflect> 和 </reflect> 标签内部。
- 禁止捏造: 绝对禁止编造任何工具的返回结果或设备状态。
- 禁止无限重试: 当工具返回错误或实体不存在时，禁止连续尝试不同的实体名称，必须先使用搜索工具或结束对话。
"""
        
        return base_prompt + "\n\n" + react_instructions

    def _build_env_context_section(self) -> str:
        """Build environment context section for system prompt with highest priority."""
        try:
            from miloco_server.service.context_provider import ContextProvider
            provider = ContextProvider.get_instance()
            if not provider:
                return "# 当前家庭环境上下文\n环境上下文服务暂未启用。\n"
            ctx = provider.get_context()
            parts = ["# 当前家庭环境上下文 (Highest Priority - 必须优先参考)"]
            parts.append("以下是当前实时的家庭环境数据，在回答与环境、设备控制相关的问题时必须优先参考：")
            if ctx.temperature is not None:
                parts.append(f"- 室内温度: {ctx.temperature}°C")
            else:
                parts.append("- 室内温度: 未获取")
            if ctx.weather_temperature is not None:
                parts.append(f"- 室外温度: {ctx.weather_temperature}°C")
            else:
                parts.append("- 室外温度: 未获取")
            if ctx.humidity is not None:
                parts.append(f"- 湿度: {ctx.humidity}%")
            else:
                parts.append("- 湿度: 未获取")
            if ctx.light_level is not None:
                parts.append(f"- 光照强度: {ctx.light_level} lux")
            parts.append(f"- 有人在家: {'是' if ctx.is_home else '否'}")
            parts.append(f"- 有人在场: {'是' if ctx.is_anyone_present else '否'}")
            if ctx.weather:
                parts.append(f"- 天气: {ctx.weather}")
            if ctx.wind_speed is not None:
                parts.append(f"- 风速: {ctx.wind_speed}")
            if ctx.air_quality is not None:
                parts.append(f"- 空气质量指数(AQI): {ctx.air_quality}")
                if ctx.air_quality <= 50:
                    parts.append("  (优)")
                elif ctx.air_quality <= 100:
                    parts.append("  (良)")
                elif ctx.air_quality <= 150:
                    parts.append("  (轻度污染)")
                else:
                    parts.append("  (中度及以上污染)")
            if ctx.time_period:
                parts.append(f"- 当前时段: {ctx.time_period}")
            parts.append(f"- 水浸检测: {'检测到漏水' if ctx.water_leak_detected else '正常'}")
            if ctx.traffic_restricted:
                parts.append(f"- 限行状态: {ctx.traffic_restricted}")
            else:
                parts.append("- 限行状态: 无限行")
            parts.append("")
            parts.append("基于环境数据的决策参考：")
            parts.append("- 温度 > 28°C → 建议开空调制冷 | 温度 < 10°C → 建议开暖气")
            parts.append("- 湿度 < 30% → 建议开加湿器 | 湿度 > 70% → 建议开除湿")
            parts.append("- 有人在家 = 否 → 不应开灯、放音乐等 | 有人在场 = 否 → 可关灯节能")
            parts.append("- AQI > 100 → 不建议开窗 | 下雨 → 不建议开窗")
            parts.append("- 水浸检测 = 检测到漏水 → 立即通知用户并建议关闭水阀")
            parts.append("- 有限行 → 建议使用其他出行方式或提醒注意限行尾号")
            parts.append("- 如需获取**最新**环境数据（而非上方快照），可调用 get_environment_context 工具（每轮最多1次）")
            return "\n".join(parts)
        except Exception as e:
            logger.debug("Failed to build env context section: %s", e)
            return "# 当前家庭环境上下文\n环境上下文获取失败。\n"

    def receiveMessage(self, msg, sender):
        """Actor message receiving method."""
        if isinstance(msg, Event):
            self._handle_event(msg)
        elif isinstance(msg, ActorExitRequest):
            logger.info("[%s] EnhancedChatAgent ActorExitRequest received",
                        self._request_id)
            self._handle_exit_request()
        else:
            logger.warning("[%s] Unsupported message: %s", self._request_id, msg)

    def _handle_event(self, event: Event) -> None:
        """Handle event."""
        logger.debug("[%s] handle_event: header=%s payload='%s'", self._request_id, event.header, event.payload)
        try:
            self._parse_and_handle_event(event)
        except Exception as e:
            logger.error("[%s] Unexpected error handling event: %s",
                         self._request_id, e)
            self._send_instruction(
                Dialog.Exception(message=f"EnhancedChatAgent handle_event Unexpected Error: {e}"))
            self._send_dialog_finish(False)

    def _parse_and_handle_event(self, event: Event) -> None:
        """Parse and handle event - to be overridden."""
        pass

    def _build_persona_prompt(self) -> str:
        """
        Build persona prompt additions (Highest Priority)
        
        Returns:
            Persona prompt string or empty string if no active persona
        """
        try:
            # Get active persona from global persona manager
            active_persona = persona_manager.get_active_persona()
            
            if not active_persona:
                logger.debug("[%s] No active persona, skipping persona prompt", self._request_id)
                return ""
            
            # Build persona prompt with highest priority marker
            prompt_parts = []
            prompt_parts.append("=" * 60)
            prompt_parts.append("【主角色设定 - 最高优先级，必须严格遵守】")
            prompt_parts.append("=" * 60)
            
            # AI Identity
            if active_persona.ai_name:
                prompt_parts.append(f"\n🤖 AI身份:")
                prompt_parts.append(f"  - 你的名字：{active_persona.ai_name}")
                if active_persona.ai_title:
                    prompt_parts.append(f"  - 你的身份：{active_persona.ai_title}")
            
            # User Identity
            if active_persona.user_name or active_persona.user_title:
                prompt_parts.append(f"\n👤 用户身份:")
                if active_persona.user_name:
                    prompt_parts.append(f"  - 用户名字：{active_persona.user_name}")
                    prompt_parts.append(f"  - 称呼方式：你必须用「{active_persona.user_name}」来称呼用户")
                if active_persona.user_title:
                    prompt_parts.append(f"  - 尊称：你应该用「{active_persona.user_title}」来尊称用户")
            
            # Speaking Style
            if active_persona.speaking_style or active_persona.tone or active_persona.language_style:
                prompt_parts.append(f"\n💬 说话风格:")
                if active_persona.speaking_style:
                    prompt_parts.append(f"  - 风格：{active_persona.speaking_style}")
                if active_persona.tone:
                    prompt_parts.append(f"  - 语气：{active_persona.tone}")
                if active_persona.language_style:
                    prompt_parts.append(f"  - 语言：{active_persona.language_style}")
                if active_persona.response_length:
                    prompt_parts.append(f"  - 回复长度：{active_persona.response_length}")
            
            # Personality
            if active_persona.personality:
                prompt_parts.append(f"\n🎭 性格特点：")
                prompt_parts.append(f"  - {active_persona.personality}")
                prompt_parts.append(f"  - 幽默程度：{active_persona.humor_level}/5")
                prompt_parts.append(f"  - 共情程度：{active_persona.empathy_level}/5")
                prompt_parts.append(f"  - 正式程度：{active_persona.formality_level}/5")
            
            # Greetings
            if active_persona.custom_greeting or active_persona.custom_farewell:
                prompt_parts.append(f"\n👋 固定用语:")
                if active_persona.custom_greeting:
                    prompt_parts.append(f"  - 问候语：{active_persona.custom_greeting}")
                if active_persona.custom_farewell:
                    prompt_parts.append(f"  - 结束语：{active_persona.custom_farewell}")
            
            # Special Instructions
            if active_persona.special_instructions:
                prompt_parts.append(f"\n📋 特殊指令：")
                prompt_parts.append(f"  {active_persona.special_instructions}")
            
            # Topics
            if active_persona.forbidden_topics or active_persona.preferred_topics:
                prompt_parts.append(f"\n🚫 话题限制:")
                if active_persona.forbidden_topics:
                    prompt_parts.append(f"  - 禁止话题：{', '.join(active_persona.forbidden_topics)}")
                if active_persona.preferred_topics:
                    prompt_parts.append(f"  - 偏好话题：{', '.join(active_persona.preferred_topics)}")
            
            # Priority enforcement
            prompt_parts.append("\n" + "=" * 60)
            prompt_parts.append("⚠️  以上设定具有最高优先级，覆盖所有其他设定")
            prompt_parts.append("⚠️  如果以上设定与其他指令冲突，必须优先遵守以上设定")
            prompt_parts.append("=" * 60)
            
            persona_prompt = "\n".join(prompt_parts)
            logger.info("[%s] Applied persona settings: AI=%s, User=%s",
                       self._request_id, active_persona.ai_name, active_persona.user_name)
            
            return persona_prompt
            
        except Exception as e:
            logger.error("[%s] Failed to build persona prompt: %s", self._request_id, e)
            return ""

    async def _run_chat(self, query: str) -> None:
        """Run agent to process user query with enhanced capabilities.

        Args:
            query: The user query to process.
        """
        logger.info("[%s] Starting enhanced processing: %s", self._request_id, query)
        
        self._current_query = query
        
        # Auto-select role if needed
        if not self._active_role or self._active_role.config.name == "smart_home_assistant":
            self._active_role = self._role_manager.auto_select_role(query)
            logger.info("[%s] Auto-selected role: %s", self._request_id, self._active_role.config.name)
        
        # Update context
        self._context_manager.update_state(self._request_id, ContextState.LISTENING)
        self._context_manager.add_message(self._request_id, "user", query)
        
        success = False
        error_message = None
        
        try:
            tool_context = ToolContext(
                query=query,
                conversation_history=[m.to_dict() for m in self._conversation_context.messages],
            )

            memory_task = self._retrieve_memory_context(query)
            tool_task = self._tool_selector.async_select_tools(tool_context, top_k=5) if self._tool_selector else None

            gather_tasks = [memory_task]
            if tool_task is not None:
                gather_tasks.append(tool_task)
            results = await asyncio.gather(*gather_tasks, return_exceptions=True)

            memory_context = results[0] if not isinstance(results[0], Exception) else None
            if isinstance(results[0], Exception):
                logger.warning("[%s] Memory retrieval failed: %s", self._request_id, results[0])

            if memory_context:
                self._chat_history_messages.replace_or_add_content(
                    "system",
                    "[长期记忆上下文]",
                    f"[长期记忆上下文] 以下是与当前对话相关的记忆信息，请在回答时参考：\n{memory_context}")

            self._memory_extraction_start_idx = len(self._chat_history_messages._messages)

            self._chat_history_messages.add_content(
                "user", f"request_id: {self._request_id}, query: {query}")

            if tool_task is not None:
                tool_result = results[1] if len(results) > 1 and not isinstance(results[1], Exception) else ([], False)
                if isinstance(results[1], Exception):
                    logger.warning("[%s] Tool selection failed: %s", self._request_id, results[1])
                selected_tools, is_no_tool = tool_result
                logger.info("[%s] Tool selector recommendations: %s", 
                           self._request_id, 
                           [t.tool_name for t in selected_tools])

                if is_no_tool:
                    self._selected_tool_names = []
                    logger.info("[%s] No-tool query detected, skipping all tools", self._request_id)
                elif self._tool_selector._tools and selected_tools:
                    self._selected_tool_names = [t.tool_name for t in selected_tools]
                else:
                    self._selected_tool_names = self._get_default_tool_names(query)
                    logger.info("[%s] Using default tool set: %s", self._request_id, self._selected_tool_names)

            self._context_manager.update_state(self._request_id, ContextState.THINKING)
            success, error_message = await self._cyclic_execute()

        except Exception as e:
            logger.error("[%s] Unexpected error: %s", self._request_id, str(e), exc_info=True)
            
            # Use error handler for recovery
            recovery_result = await self._error_handler.handle_error(
                e,
                context={"request_id": self._request_id, "query": query},
                recovery_context={
                    "original_func": self._cyclic_execute,
                    "llm_proxy": self._llm_proxy,
                    "messages": self._chat_history_messages.get_messages(),
                }
            )
            
            if recovery_result.get("success"):
                success = True
                if "response" in recovery_result:
                    self._send_instruction(
                        Template.ToastStream(stream=recovery_result["response"]))
            else:
                success = False
                error_message = recovery_result.get("error", str(e))

        finally:
            logger.info("[%s] Finalizing chat, success: %s", self._request_id, success)
            
            # Record learning data
            if hasattr(self, '_current_intent'):
                learning_record = LearningRecord(
                    session_id=self._request_id,
                    query=query,
                    intent=self._current_intent,
                    selected_tools=[t.tool_name for t in selected_tools] if 'selected_tools' in locals() else [],
                    success=success,
                )
                self._adaptive_learner.record_interaction(learning_record)
            
            await self._run_finally_do(success, error_message)

    async def _cyclic_execute(self) -> tuple[bool, str | None]:
        """Cyclic execute agent steps with context tracking and optimization."""
        step_number = 0
        for step in range(self._max_steps):
            step_number = step + 1
            logger.info("[%s] Executing step %d/%d (tools: %d/%d)",
                        self._request_id, step_number, self._max_steps,
                        self._tool_execution_count, self._max_tool_executions)

            # Check if we've exceeded tool execution limit
            if self._tool_execution_count >= self._max_tool_executions:
                logger.warning("[%s] Tool execution limit reached (%d), forcing completion",
                              self._request_id, self._max_tool_executions)
                # Add system message to guide AI to complete
                self._chat_history_messages.add_content(
                    "system",
                    "系统提示：已达到工具调用上限，请基于已有信息直接回答用户，"
                    "使用 <final_answer> 标签结束对话。"
                )
                # Give AI one more step to generate final answer
                if step < self._max_steps - 1:
                    finish_reason = await self._execute_step(step_number)
                    if self._is_completion_step(finish_reason):
                        return True, None
                return False, "工具调用次数过多，请简化您的请求"

            self._context_manager.update_state(self._request_id, ContextState.EXECUTING)
            finish_reason = await self._execute_step(step_number)

            # Early termination: detect repeated-tool-call loop and force completion
            if self._consecutive_skipped_calls >= self._max_consecutive_skips:
                logger.warning(
                    "[%s] Consecutive repeated tool calls (%d) reached limit, forcing final_answer",
                    self._request_id, self._consecutive_skipped_calls,
                )
                self._chat_history_messages.add_content(
                    "system",
                    "系统提示：你已经连续多次尝试调用相同的工具且均被拦截。"
                    "该工具之前的结果已经在对话历史中，请立即回顾历史消息找到结果，"
                    "直接使用 <final_answer> 标签给出最终答案。不要再调用任何工具。"
                )
                self._consecutive_skipped_calls = 0
                # Give one more step to output final_answer.
                # If the LLM makes a *different* (non-repeated) tool call, allow it
                # to proceed — the loop will continue naturally on the next iteration.
                if step < self._max_steps - 1:
                    finish_reason = await self._execute_step(step_number + 1)
                    if self._is_completion_step(finish_reason):
                        logger.info("[%s] Agent completed after force-completion", self._request_id)
                        self._context_manager.update_state(self._request_id, ContextState.COMPLETED)
                        return True, None
                    # If the LLM made a new (non-repeated) tool call or is still going,
                    # let the main loop handle it — don't fail immediately.
                    if finish_reason in ("tool_calls",):
                        logger.info("[%s] Force-completion gave a non-repeated tool call, "
                                    "letting main loop continue", self._request_id)
                        continue
                return False, "多次尝试重复调用相同工具，请简化您的请求"

            if self._is_completion_step(finish_reason):
                logger.info("[%s] Agent has completed the task", self._request_id)
                self._context_manager.update_state(self._request_id, ContextState.COMPLETED)
                return True, None

        logger.warning("[%s] Reached maximum number of steps %d",
                       self._request_id, self._max_steps)
        return False, "Maximum operation steps reached"

    async def _run_finally_do(self, success: bool, error_message: str | None) -> None:
        """Run finally do."""
        if not success:
            msg = (error_message or "").strip() or "处理未完成或已中断"
            self._send_instruction(Dialog.Exception(message=msg))
            self._context_manager.update_state(self._request_id, ContextState.ERROR)

        self._send_dialog_finish(success)

        if self._active_role:
            self._active_role.record_interaction(success)

        if success:
            self._start_background_memory_extraction()

    async def _execute_step(self, step_number: int) -> Optional[str]:
        """Execute single agent step with enhanced error handling."""
        try:
            llm_response: AsyncGenerator[dict, None] = await self._call_llm_stream()

            chunk_content_cache: list[str] = []
            chunk_reasoning_cache: list[str] = []
            delta_tool_call_list: list[list[ChoiceDeltaToolCall]] = []
            finish_reason = None

            async for chunk in llm_response:
                current_finish_reason, current_tool_calls, content_stream, reasoning_stream = await self._process_llm_chunk(
                    chunk)
                
                if content_stream is not None and content_stream != "":
                    chunk_content_cache.append(content_stream)
                    self._send_instruction(
                        Template.ToastStream(stream=content_stream))

                if reasoning_stream is not None and reasoning_stream != "":
                    chunk_reasoning_cache.append(reasoning_stream)

                if current_tool_calls is not None:
                    delta_tool_call_list.append(current_tool_calls)

                if current_finish_reason is not None and current_finish_reason != "":
                    finish_reason = current_finish_reason
                    break

            finalized_content = "".join(chunk_content_cache)
            finalized_reasoning_content = "".join(chunk_reasoning_cache) if chunk_reasoning_cache else None

            # Check for final answer tag and force finish
            if "<final_answer>" in finalized_content:
                finish_reason = "stop"
                logger.info("[%s] Detected <final_answer> tag, forcing completion",
                           self._request_id)

            finalized_tool_calls: list[
                ChatCompletionMessageToolCall] = self._merge_delta_tool_calls(
                    delta_tool_call_list)

            # Enhanced fallback handling
            if not finalized_content and not finalized_tool_calls and finish_reason == "stop":
                logger.info("[%s] LLM returned empty, trying intelligent fallback",
                           self._request_id)
                fallback = self._get_intelligent_fallback()
                if fallback:
                    finalized_content = fallback
                    self._send_instruction(Template.ToastStream(stream=fallback))

            logger.info("[%s] Step %d finalized: content_len=%d, tools=%d, finish=%s",
                       self._request_id, step_number, len(finalized_content),
                       len(finalized_tool_calls), finish_reason)

            self._chat_history_messages.add_assistant_message(
                finalized_content, finalized_tool_calls, finalized_reasoning_content)
            
            # Add to context manager
            self._context_manager.add_message(
                self._request_id, "assistant", finalized_content,
                tool_calls=[{"id": tc.id, "name": tc.function.name} for tc in finalized_tool_calls] if finalized_tool_calls else None
            )

            if self._has_tool_calls(finalized_tool_calls):
                await self._execute_tools(finalized_tool_calls)

            if self._has_query_result and step_number >= 2:
                guide_msg = (
                    "系统提示：已获取到用户所需的查询数据，"
                    "请立即使用 <final_answer> 标签给出最终答案，不要再调用任何工具。"
                )
                self._chat_history_messages.add_content("system", guide_msg)
                logger.info("[%s] Injected completion hint: query result available", self._request_id)
            
            # Check if we've reached max consecutive errors
            if self._consecutive_tool_errors >= self._max_consecutive_errors:
                logger.warning("[%s] Max consecutive errors reached (%d), forcing completion",
                              self._request_id, self._consecutive_tool_errors)
                # Add system message to guide AI to end the conversation
                error_message = (
                    "系统提示：已连续多次尝试获取数据但未成功。"
                    "请立即停止工具调用，使用 <final_answer> 标签告知用户"
                    "无法找到相关设备或数据，并提供可能的建议（如检查设备名称、确认设备是否已配置等）。"
                )
                self._chat_history_messages.add_content("system", error_message)
                self._context_manager.add_message(
                    self._request_id, "system", error_message
                )
                # Reset counter
                self._consecutive_tool_errors = 0

            return finish_reason

        except Exception as e:
            logger.error("[%s] Error in step execution: %s", self._request_id, str(e))
            
            # Attempt recovery
            recovery = await self._error_handler.handle_error(
                e,
                context={"step": step_number, "request_id": self._request_id},
            )
            
            if recovery.get("success"):
                return "stop"  # Force completion after recovery
            
            raise LLMServiceException(f"Error in agent step: {str(e)}") from e

    async def _call_llm_stream(self) -> AsyncGenerator[dict, None]:
        """Call large language model with error handling."""
        try:
            if not self._llm_proxy:
                raise ResourceNotFoundException(
                    "Planning model not configured. Please configure on the Model Settings Page")
            
            chat_messages = self._chat_history_messages.get_messages()
            tools_to_use = self._filter_tools_for_llm()
            logger.info("[%s] Calling LLM with %d messages, %d tools",
                       self._request_id, len(chat_messages), len(tools_to_use))
            
            return self._llm_proxy.async_call_llm_stream(chat_messages, tools_to_use)
            
        except Exception as e:
            logger.error("[%s] Error calling LLM: %s", self._request_id, str(e))
            raise

    def _get_default_tool_names(self, query: str) -> list[str]:
        """Return a minimal default tool set based on query intent instead of all 21 tools."""
        query_lower = query.lower()

        chat_intents = [
            "greeting", "farewell", "thanks", "joke", "small_talk", "chat", "memory", "knowledge", "weather"
        ]
        chat_patterns = [
            r"^(你好|hello|hi|hey|早上好|下午好|晚上好|早安|晚安|早|嗨)(\b.*)?$",
            r"^(bye|再见|拜拜|晚安)(\b.*)?$",
            r"^(谢谢|thanks|thank)(\b.*)?$",
            r"^(我的|我)(手机|生日|年龄|名字|性别|信息|地址|密码|车牌号)(是)?(\b.*)?$",
            r"^(明天|今天|后天|最近).*(有雨|天气|下雨|晴天|气温|冷|热)(吗)?(\b.*)?$",
            r"^(室内|环境|房间|客厅|卧室).*(环境|情况|状态)(吗)?(\b.*)?$",
            r"^.*农历.*$",
            r"^.*几点了.*$",
            r"^.*现在(时间|几点|几点).*$",
            r"^(知道了|好的|嗯|哦|行|OK|ok).*$",
            r"^(备注|说明|补充).*一下.*$",
        ]
        for pattern in chat_patterns:
            if re.match(pattern, query_lower):
                logger.info("Detected chat-intent query, returning empty tool set: %s", query[:50])
                return []

        core_tools = ["get_devices", "get_device_spec"]

        control_keywords = ["开", "关", "打开", "关闭", "调", "设置", "亮", "暗"]
        query_keywords = ["温度", "湿度", "状态", "多少", "几度", "查询", "查看", "环境", "亮度"]
        camera_keywords = ["摄像头", "画面", "监控", "看"]
        scene_keywords = ["场景", "模式", "自动化", "规则"]

        if any(kw in query_lower for kw in control_keywords):
            core_tools.append("send_ctrl_rpc")
        if any(kw in query_lower for kw in query_keywords):
            core_tools.append("send_get_rpc")
        if any(kw in query_lower for kw in camera_keywords):
            core_tools.extend(["vision_understand", "who_am_i"])
        if any(kw in query_lower for kw in scene_keywords):
            core_tools.extend(["trigger_manual_scene", "trigger_automation", "create_rule"])

        # When no device-related keywords matched, don't force tools —
        # the query is likely a statement/chat that needs no tools
        if len(core_tools) == 2:
            logger.info(
                "No device-related keywords matched, returning empty tool set for query: %s",
                query[:50],
            )
            return []

        seen = set()
        unique_tools = []
        for t in core_tools:
            if t not in seen:
                seen.add(t)
                unique_tools.append(t)
        return unique_tools

    def _filter_tools_for_llm(self) -> list:
        """Filter tools based on pre-flight check and tool selector recommendations."""
        if self._selected_tool_names is not None and not self._selected_tool_names:
            logger.info("[%s] Pre-flight: query needs no tools, passing empty list", self._request_id)
            return []

        if not self._selected_tool_names:
            logger.info("[%s] No tool selection available, using minimal default set", self._request_id)
            self._selected_tool_names = self._get_default_tool_names("")

        if not self._selected_tool_names:
            return []

        query_lower = (self._current_query or "").lower()
        needs_env_context = any(kw in query_lower for kw in [
            "环境", "温度", "湿度", "空气质量", "pm2.5", "甲醛", "co2"
        ])
        if not needs_env_context:
            logger.info("[%s] Query does not need environment context, filtering out get_environment_context",
                       self._request_id)

        selected_set = set(self._selected_tool_names)
        filtered = []
        for tool in self._all_mcp_tools_meta:
            try:
                func = None
                if isinstance(tool, dict):
                    func = tool.get("function")
                else:
                    func = getattr(tool, "function", None)

                if func is None:
                    filtered.append(tool)
                    continue

                if isinstance(func, dict):
                    name = func.get("name", "")
                else:
                    name = getattr(func, "name", "") or ""

                if name.endswith("get_environment_context") and not needs_env_context:
                    continue

                for selected_name in selected_set:
                    if name.endswith(selected_name) or selected_name in name:
                        filtered.append(tool)
                        break
            except Exception:
                filtered.append(tool)

        if not filtered:
            return self._all_mcp_tools_meta

        return filtered

    async def _process_llm_chunk(
        self, chunk: dict
    ) -> tuple[Optional[str], Optional[list[ChoiceDeltaToolCall]], Optional[str], Optional[str]]:
        """Process LLM streaming response chunk."""
        if not chunk.get("success", False):
            error_msg = chunk.get("error", "Unknown error")
            raise RuntimeError(f"LLM stream error: {error_msg}")

        chat_chunk: ChatCompletionChunk = chunk["chunk"]
        if not chat_chunk.choices:
            raise RuntimeError("No choices in LLM response")

        choice = chat_chunk.choices[0]
        delta = choice.delta
        finish_reason = choice.finish_reason

        content_stream = delta.content
        tool_calls = delta.tool_calls
        reasoning_content = getattr(delta, "reasoning_content", None)

        return finish_reason, tool_calls, content_stream, reasoning_content

    def _send_instruction(self, instruction_payload: InstructionPayload):
        """Send instruction to transceiver actor."""
        actor_system.tell(self._out_actor_address, instruction_payload)

    def _send_dialog_finish(self, success: bool):
        """Send dialog finish instruction."""
        logger.info("[%s] send_dialog_finish: %s", self._request_id, success)
        self._send_instruction(Dialog.Finish(success=success))

    def _has_tool_calls(self, tool_calls: list[ChatCompletionMessageToolCall]) -> bool:
        """Check if there are tool calls."""
        return tool_calls is not None and len(tool_calls) > 0

    def _merge_delta_tool_calls(
        self, delta_tool_call_list: list[list[ChoiceDeltaToolCall]]
    ) -> list[ChatCompletionMessageToolCall]:
        """Merge delta tool call information."""
        if not delta_tool_call_list:
            return []

        aggregated_calls: dict[int, dict[str, Any]] = {}

        for chunk_tool_calls in delta_tool_call_list:
            if not chunk_tool_calls:
                continue
            for delta_tool_call in chunk_tool_calls:
                call_index = getattr(delta_tool_call, "index", None) or 0

                if call_index not in aggregated_calls:
                    aggregated_calls[call_index] = {
                        "id": None,
                        "type": "function",
                        "function": {"name": None, "arguments": ""},
                    }

                current = aggregated_calls[call_index]

                delta_id = getattr(delta_tool_call, "id", None)
                if delta_id:
                    current["id"] = delta_id

                delta_function = getattr(delta_tool_call, "function", None)
                if delta_function:
                    delta_name = getattr(delta_function, "name", None)
                    if delta_name:
                        current["function"]["name"] = delta_name

                    delta_arguments = getattr(delta_function, "arguments", None)
                    if delta_arguments:
                        current["function"]["arguments"] += delta_arguments

        finalized_calls: list[ChatCompletionMessageToolCall] = []
        for call_index in sorted(aggregated_calls.keys()):
            agg = aggregated_calls[call_index]
            call_id = agg.get("id") or f"call_{call_index}"
            function_obj = {
                "name": agg["function"].get("name") or "",
                "arguments": agg["function"].get("arguments") or "",
            }
            finalized_calls.append(
                ChatCompletionMessageToolCall(
                    id=call_id,
                    type="function",
                    function=function_obj,
                ))

        return finalized_calls

    async def _execute_tools(
            self, tool_calls: list[ChatCompletionMessageToolCall]) -> None:
        """Execute tool calls in parallel for better performance."""
        if not tool_calls:
            return
        if len(tool_calls) == 1:
            await self._execute_single_tool(tool_calls[0])
            return

        results = await asyncio.gather(
            *(self._execute_single_tool(tc) for tc in tool_calls),
            return_exceptions=True,
        )
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error("[%s] Tool %s failed with exception: %s",
                            self._request_id, tool_calls[i].function.name, result)
                self._consecutive_tool_errors += 1
                self._chat_history_messages.add_tool_call_res_content(
                    tool_calls[i].id, tool_calls[i].function.name, f"Error: {result}")

    async def _execute_single_tool(
            self, tool_call: ChatCompletionMessageToolCall) -> None:
        """Execute single tool call with enhanced error handling."""
        original_tool_name = tool_call.function.name
        tool_id = tool_call.id
        tool_call_content = ""

        # Increment tool execution counter
        self._tool_execution_count += 1

        # ── No-retry guard: interactive tools (create_rule etc.) can only
        #     be called ONCE.  Any subsequent attempt (even with different
        #     arguments) must be blocked — retrying opens another UI dialog.
        is_no_retry = (
            original_tool_name in self._no_retry_tools
            or any(original_tool_name.endswith(name)
                   for name in self._no_retry_tools)
        )
        if is_no_retry and any(key.startswith(original_tool_name)
                               for key in self._called_tool_keys):
            logger.warning("[%s] No-retry tool %s already called — skipping",
                          self._request_id, original_tool_name)
            self._chat_history_messages.add_tool_call_res_content(
                tool_id, original_tool_name,
                '{"error":"此交互工具不可重复调用，请直接使用之前的结果告知用户。"}'
            )
            self._chat_history_messages.add_content(
                "system",
                "🔴 系统强制指令：{} 是交互式工具，已经调用过一次，不可重复调用。"
                "请立即使用 <final_answer> 标签输出最终答案，不要再调用任何工具。"
                .format(original_tool_name),
            )
            self._consecutive_skipped_calls = self._max_consecutive_skips  # trigger force-completion
            return

        # Check for repeated tool call with same parameters
        tool_key = f"{original_tool_name}:{tool_call.function.arguments}"
        if tool_key in self._called_tool_keys:
            logger.warning("[%s] Detected repeated tool call: %s, skipping",
                          self._request_id, original_tool_name)

            # 1) Inject a tool-level response so the conversation flow is maintained
            self._chat_history_messages.add_tool_call_res_content(
                tool_id, original_tool_name,
                '{"info":"此工具刚刚已被调用过，本次调用被拦截。"}'
            )

            # 2) Retrieve the previous *real* result for this tool and inject it
            #    as a SYSTEM message so the LLM sees both the command to stop
            #    AND the actual data it should use.
            prev_result = self._find_previous_tool_result(original_tool_name)
            if prev_result:
                sys_msg = (
                    "🔴 系统强制指令：你刚刚重复调用了同一个工具（{}），本次调用已被拦截。"
                    "下面是该工具上一次调用时返回的真实结果，请直接使用这些数据，"
                    "立即输出 <final_answer> 标签给出最终答案，不要再调用任何工具。\n\n"
                    "—— 之前的结果 ——\n{}"
                ).format(original_tool_name, prev_result[:1500])
            else:
                sys_msg = (
                    "🔴 系统强制指令：你刚刚重复调用了同一个工具（{}），本次调用已被拦截。"
                    "该工具之前的结果已经存在于对话历史中，请回顾历史消息找到它，"
                    "立即输出 <final_answer> 标签给出最终答案，不要再调用任何工具。"
                ).format(original_tool_name)

            self._chat_history_messages.add_content("system", sys_msg)
            self._consecutive_skipped_calls += 1
            return
        self._called_tool_keys.add(tool_key)
        # Reset skipped counter when a new (non-repeated) tool is executed
        self._consecutive_skipped_calls = 0

        try:
            logger.info("[%s] Executing tool: %s (count: %d/%d)", 
                       self._request_id, original_tool_name,
                       self._tool_execution_count, self._max_tool_executions)

            client_id, tool_name, parameters = self._tool_executor.parse_tool_call(tool_call)

            # Try to resolve the tool across all clients when client_id is unknown
            if client_id == "unknown":
                resolved = await self._tool_executor.resolve_unknown_tool(tool_call)
                if resolved:
                    client_id, tool_name, parameters = resolved
                    logger.info("[%s] Resolved unprefixed tool '%s' to client '%s'",
                               self._request_id, original_tool_name, client_id)
                else:
                    # Tool could not be resolved — likely a hallucinated tool (e.g., "reflect")
                    logger.error("[%s] Could not resolve tool '%s' in any MCP client",
                                self._request_id, original_tool_name)
                    self._chat_history_messages.add_tool_call_res_content(
                        tool_id, original_tool_name,
                        '{"error":"工具 \\"%s\\" 不存在。请使用已注册的工具，'
                        '或直接使用 <final_answer> 标签输出最终答案。"}' % original_tool_name
                    )
                    self._chat_history_messages.add_content(
                        "system",
                        "🔴 系统强制指令：你尝试调用了不存在的工具 \"%s\"。\n"
                        "- <reflect> 和 </reflect> 是思考标签，不是工具，不要尝试调用它们。\n"
                        "- 如果你已经收集到足够信息，请立即使用 <final_answer> 标签给出最终答案。\n"
                        "- 如果还需要调用工具，请使用列表中已注册的工具名称。" % original_tool_name,
                    )
                    self._consecutive_skipped_calls += 1
                    return

            # ── Enforce device spec flow: get_device_spec must be called before send_ctrl_rpc/send_get_rpc ──
            if tool_name in self._spec_required_tools:
                did = parameters.get("did") or parameters.get("device_id") or ""
                if did and did not in self._device_spec_retrieved:
                    logger.warning("[%s] Tool %s called for device %s without prior get_device_spec — blocking",
                                  self._request_id, tool_name, did)
                    self._chat_history_messages.add_tool_call_res_content(
                        tool_id, tool_name,
                        '{"error":"设备 %s 的SPEC定义尚未获取。你必须先调用 get_device_spec(did=\\"%s\\") '
                        '获取设备SPEC定义，然后从SPEC中找到正确的 iid，才能调用 %s。'
                        '请立即调用 get_device_spec。"}' % (did, did, tool_name)
                    )
                    self._chat_history_messages.add_content(
                        "system",
                        "🔴 系统强制指令：你跳过了关键步骤！调用 %s 之前必须先调用 get_device_spec。\n"
                        "正确流程：get_devices → get_device_spec(did=\"%s\") → %s(did, iid从SPEC获取)\n"
                        "请立即调用 get_device_spec(did=\"%s\") 获取设备SPEC定义。"
                        % (tool_name, did, tool_name, did),
                    )
                    self._consecutive_skipped_calls += 1
                    return

            service_name = self._tool_executor.get_server_name(client_id)

            self._send_instruction(
                Template.CallTool(id=tool_id,
                                    service_name=service_name,
                                    tool_name=tool_name,
                                    tool_params=tool_call.function.arguments))

            # Track execution start
            import time
            start_time = time.time()
            
            result = await self._tool_executor.execute_tool_by_params(
                client_id=client_id, tool_name=tool_name, parameters=parameters)
            
            response_time = time.time() - start_time

            logger.info("[%s] Tool call %s returned: %s", self._request_id,
                        tool_name, result)

            response_json = json.dumps(result.response, ensure_ascii=False)

            self._send_instruction(
                Template.CallToolResult(id=tool_id,
                                        success=result.success,
                                        tool_response=response_json,
                                        error_message=result.error_message))

            # Check if tool returned error (even if result.success is True)
            is_actual_error = False
            if result.success:
                tool_call_content = response_json
                # Check if response contains error information
                try:
                    response_data = json.loads(response_json) if isinstance(response_json, str) else response_json
                    if isinstance(response_data, dict) and ("error" in response_data or response_data.get("device_count") == 0):
                        is_actual_error = True
                        logger.warning("[%s] Tool %s returned error or empty data: %s", 
                                      self._request_id, tool_name, response_data)
                except:
                    pass
            else:
                tool_call_content = result.error_message
                is_actual_error = True

            # ── No-retry guard for interactive tools (create_rule etc.) ──
            #    These tools pop a UI dialog; once errored the result is final —
            #    retrying would open another dialog, which is terrible UX.
            if is_actual_error and (tool_name in self._no_retry_tools
                                    or any(tool_name.endswith(name)
                                           for name in self._no_retry_tools)):
                logger.warning(
                    "[%s] Interactive tool %s errored — forcing immediate completion (no retry)",
                    self._request_id, tool_name,
                )
                self._chat_history_messages.add_content(
                    "system",
                    "系统提示：create_rule 工具返回了错误，创建规则流程已结束。"
                    "请立即使用 <final_answer> 标签告知用户发生了什么，"
                    "并建议用户重新发起规则创建。不要再调用任何工具。"
                )
                # Push consecutive errors to the limit so the existing
                # force-completion block in _execute_step triggers immediately.
                self._consecutive_tool_errors = self._max_consecutive_errors

            # Update consecutive error counter
            if is_actual_error:
                self._consecutive_tool_errors += 1
                logger.warning("[%s] Consecutive tool errors: %d/%d", 
                              self._request_id, self._consecutive_tool_errors, self._max_consecutive_errors)
            else:
                self._consecutive_tool_errors = 0
                # Track successful get_device_spec calls to enforce correct flow
                if tool_name == "get_device_spec" and result.success:
                    spec_did = parameters.get("did") or parameters.get("device_id") or ""
                    if spec_did:
                        self._device_spec_retrieved.add(spec_did)
                        logger.info("[%s] Device spec retrieved for DID %s", self._request_id, spec_did)

                if tool_name == "send_get_rpc" and result.response:
                    self._has_query_result = True
                    self._last_tool_result_type = "query_value"
                    logger.info("[%s] Marked query result available from send_get_rpc", self._request_id)
                elif tool_name == "send_ctrl_rpc" and result.success:
                    self._has_query_result = True
                    self._last_tool_result_type = "control_result"
                    logger.info("[%s] Marked control result available from send_ctrl_rpc", self._request_id)

            self._chat_history_messages.add_tool_call_res_content(
                    tool_id, tool_name, tool_call_content)
            
            # Add to context manager
            self._context_manager.add_message(
                self._request_id, "tool", tool_call_content,
                metadata={"tool_name": tool_name, "success": result.success}
            )

            # Record for adaptive learning
            self._tool_selector.record_result(
                f"{client_id}___{tool_name}",
                not is_actual_error,  # Record as failure if actual error
                response_time
            )

            self._post_process_tool_call(client_id, service_name, tool_name, parameters, result)

        except Exception as e:
            logger.error("[%s] Error executing tool %s: %s",
                        self._request_id, original_tool_name, str(e))
            
            # Record failure
            self._tool_selector.record_result(original_tool_name, False, 0)
            
            self._send_instruction(Dialog.Exception(message=str(e)))

    def _post_process_tool_call(
            self, client_id: str, mcp_server_name: str,
            tool_name: str, parameters: dict, result: CallToolResult) -> None:
        """Post process tool call."""
        pass

    def _find_previous_tool_result(self, tool_name: str) -> Optional[str]:
        """Look up the most recent *real* tool result for ``tool_name`` in
        the conversation history, skipping injected skip-placeholders.
        Returns the content string or None if not found."""
        messages = self._chat_history_messages.get_messages()
        # Walk backwards; the most recent real result is usually the first hit.
        for msg in reversed(messages):
            if not isinstance(msg, dict):
                continue
            if msg.get("role") != "tool":
                continue
            if not (tool_name in msg.get("name", "")
                    or msg.get("name", "").endswith(tool_name)):
                continue
            content = msg.get("content", "")
            if not content:
                continue
            # Skip the artificial "被拦截" placeholder we inject on repeats
            if "被拦截" in content:
                continue
            # Try to extract the most useful piece from JSON-wrapped results
            try:
                parsed = json.loads(content)
                if isinstance(parsed, dict):
                    # Common patterns for vision_understand / get_devices, etc.
                    for key in ("content", "message", "tool_response", "data"):
                        val = parsed.get(key)
                        if isinstance(val, str) and val.strip():
                            return val
                        if isinstance(val, dict):
                            inner = val.get("content") or val.get("message")
                            if isinstance(inner, str) and inner.strip():
                                return inner
            except (json.JSONDecodeError, TypeError):
                pass
            return content
        return None

    def _is_completion_step(self, finish_reason: Optional[str]) -> bool:
        """Check if this is a completion step."""
        return finish_reason == "stop"

    def _get_intelligent_fallback(self) -> Optional[str]:
        """Get intelligent fallback content based on context."""
        messages = self._chat_history_messages.get_messages()

        tool_results = []
        for msg in messages:
            if isinstance(msg, dict) and msg.get("role") == "tool":
                tool_name = msg.get("name", "")
                content = msg.get("content", "")
                try:
                    parsed = json.loads(content)
                except (json.JSONDecodeError, TypeError):
                    parsed = content
                tool_results.append({"tool_name": tool_name, "data": parsed})

        if tool_results:
            return self._generate_result_summary(tool_results)

        return None

    def _generate_result_summary(self, results: List[dict]) -> str:
        """Generate natural language summary from tool results."""
        if not results:
            return "处理完成。"

        for entry in results:
            tool_name = entry.get("tool_name", "")
            data = entry.get("data")

            if not isinstance(data, dict):
                continue

            if data.get("success") is False:
                error_msg = data.get("error", data.get("error_message", ""))
                return f"操作遇到问题: {error_msg}" if error_msg else "操作遇到问题，未能获取到数据。"

            inner = data.get("content") or data.get("message") or data.get("tool_response")
            if isinstance(inner, str):
                try:
                    inner = json.loads(inner)
                except (json.JSONDecodeError, TypeError):
                    pass

            if isinstance(inner, dict):
                data = inner

            if "get_environment_context" in tool_name and isinstance(data, dict):
                return self._format_environment_summary(data)

            if "vision_understand" in tool_name:
                if isinstance(data, dict):
                    vision_content = data.get("content", "")
                    if vision_content:
                        return vision_content
                elif isinstance(data, str) and data:
                    return data

        numeric_values = []
        descriptive_parts = []
        for entry in results:
            tool_name = entry.get("tool_name", "")
            data = entry.get("data")

            if isinstance(data, dict):
                inner = data.get("content") or data.get("message") or data.get("tool_response")
                if isinstance(inner, str):
                    try:
                        inner = json.loads(inner)
                    except (json.JSONDecodeError, TypeError):
                        pass
                if isinstance(inner, dict):
                    data = inner

                if isinstance(data, dict):
                    for k, v in data.items():
                        if k.startswith("_") or k in ("success",):
                            continue
                        if isinstance(v, (int, float)):
                            label = self._infer_label(k, tool_name)
                            numeric_values.append((label, v, k))
                        elif isinstance(v, dict):
                            for sub_k, sub_v in v.items():
                                if isinstance(sub_v, (int, float)):
                                    label = self._infer_label(sub_k, tool_name)
                                    numeric_values.append((label, sub_v, sub_k))
                                elif isinstance(sub_v, dict) and "description" in sub_v:
                                    descriptive_parts.append(sub_v["description"])
                        elif isinstance(v, str):
                            descriptive_parts.append(f"{k}: {v}" if len(v) < 500 else v)
            elif isinstance(data, str) and data:
                descriptive_parts.append(data)

        parts = []
        if descriptive_parts:
            parts.append(descriptive_parts[-1])
        for label, value, _ in numeric_values:
            parts.append(f"{label}: {value}")

        if parts:
            return "；".join(parts) + "。"

        return "操作已完成，但未能解析出有效数据。"

    @staticmethod
    def _format_environment_summary(data: dict) -> str:
        """Format environment context data into natural language."""
        time_period = data.get("time_period", "")
        period_map = {
            "morning": "早上好", "forenoon": "上午好",
            "afternoon": "下午好", "evening": "晚上好", "night": "晚上好",
        }
        greeting = period_map.get(time_period, "你好")

        parts = [f"{greeting}，当前室内环境如下："]

        indoor_temp = data.get("indoor_temperature")
        if indoor_temp is not None:
            temp_feel = "比较舒适" if 18 <= indoor_temp <= 26 else ("偏热" if indoor_temp > 26 else "偏冷")
            parts.append(f"- **室内温度**: {indoor_temp}°C（{temp_feel}）")

        outdoor_temp = data.get("outdoor_temperature")
        if outdoor_temp is not None:
            parts.append(f"- **室外温度**: {outdoor_temp}°C")

        humidity = data.get("humidity")
        if humidity is not None:
            hum_feel = "适宜" if 40 <= humidity <= 60 else ("偏潮湿" if humidity > 60 else "偏干燥")
            parts.append(f"- **湿度**: {humidity}%（{hum_feel}）")

        weather = data.get("weather")
        if weather:
            weather_map = {
                "sunny": "晴天", "cloudy": "多云", "partlycloudy": "多云",
                "overcast": "阴天", "rainy": "雨天", "snowy": "雪天",
                "foggy": "雾天", "stormy": "暴风雨",
            }
            parts.append(f"- **天气**: {weather_map.get(weather, weather)}")

        wind_speed = data.get("wind_speed")
        if wind_speed is not None:
            parts.append(f"- **风速**: {wind_speed} m/s")

        light_level = data.get("light_level")
        if light_level is not None:
            light_desc = "光线充足" if light_level > 300 else ("光线一般" if light_level > 50 else "光线较暗")
            parts.append(f"- **光照**: {light_level} lux（{light_desc}）")

        air_quality = data.get("air_quality")
        if air_quality is not None:
            if air_quality <= 50:
                aq_desc = "优"
            elif air_quality <= 100:
                aq_desc = "良"
            elif air_quality <= 150:
                aq_desc = "轻度污染"
            else:
                aq_desc = "污染"
            parts.append(f"- **空气质量**: AQI {air_quality}（{aq_desc}）")

        is_home = data.get("is_home")
        is_anyone = data.get("is_anyone_present")
        if is_home is not None or is_anyone is not None:
            if is_anyone:
                parts.append("- **家中有人**: 是")
            elif is_home:
                parts.append("- **家中有人**: 主人在家，但未检测到其他人在场")
            else:
                parts.append("- **家中无人**: 当前无人在家")

        water_leak = data.get("water_leak_detected")
        if water_leak is not None:
            parts.append(f"- **水浸检测**: {'⚠️ 检测到漏水！' if water_leak else '正常，未检测到漏水'}")

        traffic = data.get("traffic_restricted")
        if traffic:
            parts.append(f"- **今日限行尾号**: {traffic}")

        return "\n".join(parts)

    @staticmethod
    def _infer_label(key: str, tool_name: str) -> str:
        key_lower = key.lower()
        exact_map = {
            "indoor_temperature": "室内温度",
            "outdoor_temperature": "室外温度",
            "temperature": "温度",
            "humidity": "湿度",
            "light_level": "光照",
            "brightness": "亮度",
            "battery": "电池电量",
            "power": "功率",
            "energy": "能耗",
            "state": "状态",
            "value": "数值",
            "prop.0.2.1": "温度",
            "prop.0.2.2": "湿度",
            "prop.0.3.1": "电池电量",
            "is_home": "是否在家",
            "is_anyone_present": "是否有人在场",
            "weather": "天气",
            "wind_speed": "风速",
            "air_quality": "空气质量",
            "time_period": "时段",
            "water_leak_detected": "水浸检测",
            "traffic_restricted": "限行状态",
        }
        if key in exact_map:
            return exact_map[key]
        for pattern, label in exact_map.items():
            if pattern in key_lower:
                return label
        if "send_get_rpc" in tool_name:
            return "查询结果"
        if "get_devices" in tool_name:
            return "设备信息"
        return key

    async def _retrieve_memory_context(self, query: str) -> Optional[str]:
        """Retrieve relevant memories for the current query."""
        try:
            from miloco_server.service.memory_service import get_memory_service
            service = get_memory_service()
            if service is None:
                return None
            context = await service.get_context_for_query(
                query=query, limit=5)
            if context and context.memories:
                logger.info("[%s] Retrieved %d relevant memories for query", self._request_id, len(context.memories))
                return context.context_text or context.to_prompt_text()
            return None
        except Exception as e:
            logger.warning("[%s] Failed to retrieve memory context: %s", self._request_id, e)
            return None

    def _start_background_memory_extraction(self) -> None:
        """Start memory extraction as a background task without blocking the dialog."""
        import asyncio

        async def _bg_task():
            try:
                await self._extract_and_store_memory()
            except Exception as e:
                logger.warning("[%s] Background memory extraction failed: %s", self._request_id, e)

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_bg_task())
        except RuntimeError:
            pass

    async def _extract_and_store_memory(self) -> None:
        """Extract memories from the current conversation and store them."""
        try:
            from miloco_server.service.memory_service import get_memory_service
            service = get_memory_service()
            if service is None:
                return
            all_msgs = self._chat_history_messages.get_messages()
            start_idx = getattr(self, "_memory_extraction_start_idx", 0)
            new_msgs = all_msgs[start_idx:]
            user_msg = None
            for msg in new_msgs:
                role = msg.get("role") if isinstance(msg, dict) else getattr(msg, "role", None)
                content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", None)
                if not role or not content:
                    continue
                if role == "user":
                    user_msg = content
                elif role == "assistant" and user_msg:
                    await service.process_conversation(
                        user_message=user_msg,
                        assistant_response=content,
                        user_id="default",
                    )
                    user_msg = None
            logger.info("[%s] Memory extraction completed for session", self._request_id)
        except Exception as e:
            logger.warning("[%s] Failed to extract and store memory: %s", self._request_id, e)

    def _handle_exit_request(self):
        """Handle Actor exit request."""
        logger.info("[%s] EnhancedChatAgent handling exit request", self._request_id)
        self._chat_companion.clear_chat_data(self._request_id)
        self._context_manager.clear_context(self._request_id)
