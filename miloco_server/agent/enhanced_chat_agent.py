# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Enhanced Chat Agent

Advanced chat agent with OpenClaw integration.
Features intelligent role management, context-aware responses,
adaptive learning, and robust error handling.
"""

import json
import logging
from typing import AsyncGenerator, Any, Optional, Dict, List
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
    Enhanced Chat Agent with OpenClaw Integration
    
    Features:
    - Dynamic role management with capability-based tool assignment
    - Context-aware prompt generation
    - Intelligent tool selection with adaptive learning
    - Comprehensive error handling with fallback strategies
    - Multi-turn conversation support with state tracking
    """

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
        
        # Track consecutive tool errors to prevent infinite loops
        self._consecutive_tool_errors = 0
        self._max_consecutive_errors = 3
        
        # Track tool execution patterns for step optimization
        self._tool_execution_count = 0
        self._max_tool_executions = 8  # Limit tool calls to prevent step exhaustion
        self._completed_tool_chains = 0

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
        # Will be populated when tools are set
        pass

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

        self._local_default_mcp_tools_meta = self._tool_executor.get_mcp_chat_completion_tools(
            mcp_client_ids=[LocalMcpClientId.LOCAL_DEFAULT],
            exclude_tool_names=exclude_tool_names,
        )

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

行动 (Action)：如果思考后确定需要与外部世界交互（查询状态、控制设备等），则生成一个或多个符合OpenAI Tool Calling格式的工具调用。

观察 (Observation)：你会接收到调用工具后返回的结果。你必须基于这个新的信息，回到第1步（思考（Think）），判断是需要继续调用其他工具，还是已经可以提供最终答案。

# 智能工具选择策略 (Important - AI自主决策)
**工具选择原则：**
- 根据用户意图和对话上下文智能选择工具
- 不要预设只能使用某些工具，所有可用工具都可以根据需要使用
- 优先考虑最直接、最高效的工具

**何时使用工具：**
- 用户询问环境相关信息（温度/湿度/天气/有人吗/空气质量等）→ 使用 `get_environment_context`（**最高优先级**）
- 需要基于环境数据决定是否控制设备（天热开空调、没人关灯等）→ 先使用 `get_environment_context`
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
- ❌ 用户说"打开灯"时先查询状态再打开
- ❌ 连续多次尝试不同实体名称
- ❌ 一个平台失败后不尝试备选平台就直接放弃

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
            parts.append("")
            parts.append("基于环境数据的决策参考：")
            parts.append("- 温度 > 28°C → 建议开空调制冷 | 温度 < 10°C → 建议开暖气")
            parts.append("- 湿度 < 30% → 建议开加湿器 | 湿度 > 70% → 建议开除湿")
            parts.append("- 有人在家 = 否 → 不应开灯、放音乐等 | 有人在场 = 否 → 可关灯节能")
            parts.append("- AQI > 100 → 不建议开窗 | 下雨 → 不建议开窗")
            parts.append("- 如需最新数据，可调用 get_environment_context 工具刷新")
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
        logger.info("[%s] handle_event: %s", self._request_id, event)
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
            memory_context = await self._retrieve_memory_context(query)
            if memory_context:
                self._chat_history_messages.add_content(
                    "system",
                    f"[长期记忆上下文] 以下是与当前对话相关的记忆信息，请在回答时参考：\n{memory_context}")

            self._chat_history_messages.add_content(
                "user", f"request_id: {self._request_id}, query: {query}")

            # Use intelligent tool selection
            tool_context = ToolContext(
                query=query,
                conversation_history=[m.to_dict() for m in self._conversation_context.messages],
            )
            
            selected_tools = self._tool_selector.select_tools(tool_context, top_k=5)
            logger.info("[%s] Tool selector recommendations: %s", 
                       self._request_id, 
                       [t.tool_name for t in selected_tools])

            if self._tool_selector._tools:
                self._selected_tool_names = [t.tool_name for t in selected_tools]
            else:
                self._selected_tool_names = None

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
        
        # Record interaction for role learning
        if self._active_role:
            self._active_role.record_interaction(success)

        if success:
            await self._extract_and_store_memory()

    async def _execute_step(self, step_number: int) -> Optional[str]:
        """Execute single agent step with enhanced error handling."""
        try:
            llm_response: AsyncGenerator[dict, None] = await self._call_llm_stream()

            chunk_content_cache: list[str] = []
            delta_tool_call_list: list[list[ChoiceDeltaToolCall]] = []
            finish_reason = None

            async for chunk in llm_response:
                current_finish_reason, current_tool_calls, content_stream = await self._process_llm_chunk(
                    chunk)
                
                if content_stream is not None and content_stream != "":
                    chunk_content_cache.append(content_stream)
                    self._send_instruction(
                        Template.ToastStream(stream=content_stream))

                if current_tool_calls is not None:
                    delta_tool_call_list.append(current_tool_calls)

                if current_finish_reason is not None and current_finish_reason != "":
                    finish_reason = current_finish_reason
                    break

            finalized_content = "".join(chunk_content_cache)

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
                finalized_content, finalized_tool_calls)
            
            # Add to context manager
            self._context_manager.add_message(
                self._request_id, "assistant", finalized_content,
                tool_calls=[{"id": tc.id, "name": tc.function.name} for tc in finalized_tool_calls] if finalized_tool_calls else None
            )

            if self._has_tool_calls(finalized_tool_calls):
                await self._execute_tools(finalized_tool_calls)
            
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

    def _filter_tools_for_llm(self) -> list:
        """Filter tools based on pre-flight check and tool selector recommendations."""
        if self._selected_tool_names is not None and not self._selected_tool_names:
            logger.info("[%s] Pre-flight: query needs no tools, passing empty list", self._request_id)
            return []

        if not self._selected_tool_names:
            return self._all_mcp_tools_meta

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

                for selected_name in selected_set:
                    if selected_name.endswith(name) or name in selected_name:
                        filtered.append(tool)
                        break
            except Exception:
                filtered.append(tool)

        if not filtered:
            return self._all_mcp_tools_meta

        return filtered

    async def _process_llm_chunk(
        self, chunk: dict
    ) -> tuple[Optional[str], Optional[list[ChoiceDeltaToolCall]], Optional[str]]:
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

        return finish_reason, tool_calls, content_stream

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
        """Execute tool calls with error handling."""
        for tool_call in tool_calls:
            await self._execute_single_tool(tool_call)

    async def _execute_single_tool(
            self, tool_call: ChatCompletionMessageToolCall) -> None:
        """Execute single tool call with enhanced error handling."""
        original_tool_name = tool_call.function.name
        tool_id = tool_call.id
        tool_call_content = ""

        # Increment tool execution counter
        self._tool_execution_count += 1

        try:
            logger.info("[%s] Executing tool: %s (count: %d/%d)", 
                       self._request_id, original_tool_name,
                       self._tool_execution_count, self._max_tool_executions)

            client_id, tool_name, parameters = self._tool_executor.parse_tool_call(tool_call)
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

            # Update consecutive error counter
            if is_actual_error:
                self._consecutive_tool_errors += 1
                logger.warning("[%s] Consecutive tool errors: %d/%d", 
                              self._request_id, self._consecutive_tool_errors, self._max_consecutive_errors)
            else:
                self._consecutive_tool_errors = 0

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

    def _is_completion_step(self, finish_reason: Optional[str]) -> bool:
        """Check if this is a completion step."""
        return finish_reason == "stop"

    def _get_intelligent_fallback(self) -> Optional[str]:
        """Get intelligent fallback content based on context."""
        messages = self._chat_history_messages.get_messages()
        
        # Extract recent tool results
        recent_results = []
        for msg in reversed(messages[-5:]):
            if isinstance(msg, dict) and msg.get("role") == "tool":
                content = msg.get("content", "")
                try:
                    parsed = json.loads(content)
                    recent_results.append(parsed)
                except:
                    recent_results.append(content)
        
        if recent_results:
            # Generate summary based on results
            return self._generate_result_summary(recent_results)
        
        return None

    def _generate_result_summary(self, results: List[Any]) -> str:
        """Generate natural language summary from tool results."""
        if not results:
            return "处理完成。"
        
        # Find the most recent successful result
        # Iterate in reverse to find the last successful result first
        for result in reversed(results):
            if isinstance(result, dict):
                # Check if result has explicit success field
                if "success" in result:
                    if result.get("success"):
                        # Successful result - return immediately
                        if "content" in result:
                            return str(result["content"])
                        elif "message" in result:
                            return str(result["message"])
                        elif "tool_response" in result:
                            # Parse tool_response if it's JSON
                            try:
                                tr = json.loads(result["tool_response"])
                                if isinstance(tr, dict):
                                    if "state" in tr:
                                        return f"设备状态: {tr['state']}"
                                    elif "result" in tr:
                                        return f"查询结果: {tr['result']}"
                                    else:
                                        return str(tr)
                                return str(tr)
                            except:
                                return str(result["tool_response"])
                        else:
                            return "操作成功完成。"
                    else:
                        # Failed result - continue to check if there's a later success
                        continue
                else:
                    # No success field - treat as successful result
                    if "result" in result:
                        return f"查询结果: {result['result']}"
                    elif "state" in result:
                        return f"设备状态: {result['state']}"
                    elif "content" in result:
                        return str(result["content"])
                    else:
                        # Show all non-metadata fields
                        display_data = {k: v for k, v in result.items() if not k.startswith('_')}
                        if display_data:
                            return str(display_data)
            else:
                # Non-dict result
                return str(result)
        
        # If no successful result found, show the last error
        last_result = results[-1]
        if isinstance(last_result, dict) and "success" in last_result and not last_result.get("success"):
            error = last_result.get("error", "未知错误")
            return f"操作遇到问题: {error}"
        
        return "处理完成。"

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

    async def _extract_and_store_memory(self) -> None:
        """Extract memories from the current conversation and store them."""
        try:
            from miloco_server.service.memory_service import get_memory_service
            service = get_memory_service()
            if service is None:
                return
            all_msgs = self._chat_history_messages.get_messages()
            user_msg = None
            for msg in all_msgs:
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
