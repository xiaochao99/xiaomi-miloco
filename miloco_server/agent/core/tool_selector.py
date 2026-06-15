# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Tool Selector Module

Provides intelligent tool selection based on context, intent, and historical performance.
Supports multiple selection strategies and adaptive learning.
"""

import json
import logging
from typing import Dict, List, Optional, Any, Callable, Tuple, TYPE_CHECKING
from dataclasses import dataclass, field
from enum import Enum, auto
from collections import defaultdict
import re

if TYPE_CHECKING:
    from miloco_server.proxy.llm_proxy import LLMProxy

logger = logging.getLogger(__name__)


class ToolSelectionStrategy(Enum):
    """Tool selection strategies"""
    RULE_BASED = auto()      # Rule-based selection
    SEMANTIC = auto()        # Semantic matching
    INTENT_BASED = auto()    # Intent-based selection
    HYBRID = auto()          # Combined approach
    ADAPTIVE = auto()        # Learning-based selection
    LLM_BASED = auto()       # LLM-based pre-selection


@dataclass
class ToolMetadata:
    """Tool metadata"""
    name: str
    description: str
    category: str = "general"
    keywords: List[str] = field(default_factory=list)
    required_params: List[str] = field(default_factory=list)
    optional_params: List[str] = field(default_factory=list)
    success_rate: float = 1.0
    avg_response_time: float = 0.0
    usage_count: int = 0
    last_used: Optional[str] = None
    capabilities: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "keywords": self.keywords,
            "required_params": self.required_params,
            "optional_params": self.optional_params,
            "success_rate": self.success_rate,
            "avg_response_time": self.avg_response_time,
            "usage_count": self.usage_count,
            "capabilities": self.capabilities,
        }


@dataclass
class ToolContext:
    """Context for tool selection"""
    query: str = ""
    intent: str = ""
    entities: Dict[str, Any] = field(default_factory=dict)
    conversation_history: List[Dict] = field(default_factory=list)
    available_devices: List[str] = field(default_factory=list)
    user_preferences: Dict[str, Any] = field(default_factory=dict)
    session_state: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "intent": self.intent,
            "entities": self.entities,
            "conversation_history": self.conversation_history,
            "available_devices": self.available_devices,
            "user_preferences": self.user_preferences,
        }


@dataclass
class ToolSelection:
    """Tool selection result"""
    tool_name: str
    confidence: float
    parameters: Dict[str, Any] = field(default_factory=dict)
    reasoning: str = ""
    alternatives: List[str] = field(default_factory=list)
    strategy_used: ToolSelectionStrategy = ToolSelectionStrategy.RULE_BASED


class ToolSelector:
    """
    Intelligent Tool Selector
    
    Selects appropriate tools based on context using multiple strategies.
    Supports adaptive learning from historical performance.
    """
    
    # Intent to tool mapping
    # Note: All cached tools removed to prevent unnecessary calls
    # Note: Use correct MIoT tool names (send_ctrl_rpc for control, send_get_rpc for query)
    NO_TOOL_INTENTS = {"chat", "memory", "statement"}

    INTENT_TOOL_MAP = {
        "turn_on": ["send_ctrl_rpc"],
        "turn_off": ["send_ctrl_rpc"],
        "adjust": ["send_ctrl_rpc"],
        "activate_scene": ["trigger_manual_scene", "trigger_automation"],
        "create_rule": ["create_rule"],
        "modify_rule": ["create_rule"],
        "view_camera": ["vision_understand"],
        "recognize_face": ["who_am_i"],
        "monitor_security": ["vision_understand"],
        "get_time": ["get_current_time"],
        "query_state": ["send_get_rpc", "get_devices"],
        "query_environment": ["send_get_rpc", "get_devices"],
        "chat": [],
        "memory": [],
        "unknown": [],
    }
    
    KEYWORD_TOOL_MAP = {
        "开": ["send_ctrl_rpc"],
        "关": ["send_ctrl_rpc"],
        "打开": ["send_ctrl_rpc"],
        "关闭": ["send_ctrl_rpc"],
        "调": ["send_ctrl_rpc"],
        "设置": ["send_ctrl_rpc"],
        "摄像头": ["vision_understand"],
        "画面": ["vision_understand"],
        "看": ["vision_understand"],
        "监控": ["vision_understand"],
        "谁": ["who_am_i"],
        "身份": ["who_am_i"],
        "认识": ["who_am_i"],
        "规则": ["create_rule"],
        "自动化": ["create_rule"],
        "场景": ["trigger_manual_scene", "trigger_automation"],
        "温度": ["send_get_rpc", "get_devices", "get_environment_context"],
        "湿度": ["send_get_rpc", "get_devices", "get_environment_context"],
        "光照": ["send_get_rpc", "get_devices"],
        "亮度": ["send_get_rpc", "get_devices"],
        "查询": ["send_get_rpc", "get_devices"],
        "查看": ["send_get_rpc", "get_devices"],
        "状态": ["send_get_rpc", "get_devices"],
        "环境": ["send_get_rpc", "get_devices", "get_environment_context"],
        "空气质量": ["send_get_rpc", "get_devices", "get_environment_context"],
        "机柜": ["send_get_rpc", "get_devices"],
        "能耗": ["send_get_rpc", "get_devices"],
        "电量": ["send_get_rpc", "get_devices"],
        "功耗": ["send_get_rpc", "get_devices"],
        "记住": [],
        "忘记": [],
        "记得": [],
        "我叫": [],
        "我的名字": [],
        "记住我": [],
    }
    
    def __init__(self, strategy: ToolSelectionStrategy = ToolSelectionStrategy.HYBRID):
        """
        Initialize tool selector
        
        Args:
            strategy: Default selection strategy
        """
        self.strategy = strategy
        self._tools: Dict[str, ToolMetadata] = {}
        self._selection_history: List[ToolSelection] = []
        self._performance_stats: Dict[str, Dict] = defaultdict(lambda: {
            "success_count": 0,
            "failure_count": 0,
            "total_time": 0.0,
            "usage_count": 0,
        })
        self._intent_classifier: Optional[Callable[[str], str]] = None
        self._llm_proxy: Optional["LLMProxy"] = None
        
        logger.info(f"ToolSelector initialized with strategy: {strategy.name}")
    
    def register_tool(self, metadata: ToolMetadata) -> None:
        """
        Register a tool
        
        Args:
            metadata: Tool metadata
        """
        self._tools[metadata.name] = metadata
        logger.debug(f"Registered tool: {metadata.name}")
    
    def register_tools_from_openai_format(self, tools: List[Any]) -> None:
        """
        Register tools from OpenAI format
        
        Args:
            tools: OpenAI format tool definitions (dict or ChatCompletionToolParam)
        """
        for tool in tools:
            try:
                # Get function object - could be dict or FunctionDefinition
                func = None
                if isinstance(tool, dict):
                    func = tool.get("function")
                else:
                    # Handle ChatCompletionToolParam / Pydantic models
                    func = getattr(tool, "function", None)
                
                if func is None:
                    logger.warning(f"Tool {tool} has no function attribute")
                    continue
                
                # Extract name and description - handle both dict and FunctionDefinition
                if isinstance(func, dict):
                    name = func.get("name", "")
                    description = func.get("description", "")
                    params = func.get("parameters", {})
                else:
                    # FunctionDefinition or similar Pydantic model
                    name = getattr(func, "name", "") or ""
                    description = getattr(func, "description", "") or ""
                    params = getattr(func, "parameters", None)
                
                # Extract parameters
                required_params = []
                optional_params = []
                if params:
                    if isinstance(params, dict):
                        required_params = list(params.get("required", []))
                        properties = params.get("properties", {})
                        optional_params = [k for k in properties.keys() if k not in required_params]
                    else:
                        # Pydantic model
                        required_params = list(getattr(params, "required", []) or [])
                        properties = getattr(params, "properties", {}) or {}
                        optional_params = [k for k in properties.keys() if k not in required_params]
                
                if not name:
                    logger.warning(f"Tool has no name, skipping: {tool}")
                    continue
                
                metadata = ToolMetadata(
                    name=name,
                    description=description,
                    required_params=required_params,
                    optional_params=optional_params,
                )
                self.register_tool(metadata)
                logger.debug(f"Successfully registered tool: {name}")
            except Exception as e:
                logger.warning(f"Failed to register tool {tool}: {e}")
    
    def select_tools(
        self,
        context: ToolContext,
        strategy: Optional[ToolSelectionStrategy] = None,
        top_k: int = 3,
    ) -> List[ToolSelection]:
        """
        Select appropriate tools for the context
        
        Args:
            context: Tool selection context
            strategy: Selection strategy (default: instance strategy)
            top_k: Number of top results to return
            
        Returns:
            List of tool selections
        """
        strategy = strategy or self.strategy
        
        if strategy == ToolSelectionStrategy.RULE_BASED:
            selections = self._rule_based_selection(context)
        elif strategy == ToolSelectionStrategy.SEMANTIC:
            selections = self._semantic_selection(context)
        elif strategy == ToolSelectionStrategy.INTENT_BASED:
            selections = self._intent_based_selection(context)
        elif strategy == ToolSelectionStrategy.ADAPTIVE:
            selections = self._adaptive_selection(context)
        else:  # HYBRID
            selections = self._hybrid_selection(context)
        
        # Sort by confidence and return top_k
        selections.sort(key=lambda x: x.confidence, reverse=True)
        return selections[:top_k]
    
    def _rule_based_selection(self, context: ToolContext) -> List[ToolSelection]:
        """Rule-based tool selection"""
        selections = []
        query = context.query.lower()
        
        # Check keyword mappings
        for keyword, tools in self.KEYWORD_TOOL_MAP.items():
            if keyword in query:
                for tool_name in tools:
                    # Match both unprefixed and prefixed tool names
                    matched = False
                    if tool_name in self._tools:
                        selections.append(ToolSelection(
                            tool_name=tool_name,
                            confidence=0.8,
                            reasoning=f"Matched keyword: {keyword}",
                            strategy_used=ToolSelectionStrategy.RULE_BASED,
                        ))
                        matched = True
                    if not matched:
                        for registered_name in self._tools:
                            if registered_name.endswith("___" + tool_name):
                                selections.append(ToolSelection(
                                    tool_name=registered_name,
                                    confidence=0.8,
                                    reasoning=f"Matched keyword: {keyword}",
                                    strategy_used=ToolSelectionStrategy.RULE_BASED,
                                ))
        
        # Remove duplicates while keeping highest confidence
        seen = {}
        for sel in selections:
            if sel.tool_name not in seen or seen[sel.tool_name].confidence < sel.confidence:
                seen[sel.tool_name] = sel
        
        return list(seen.values())
    
    @staticmethod
    def _extract_tokens(text: str) -> set:
        tokens = set(re.findall(r'[\u4e00-\u9fff]', text))
        tokens.update(re.findall(r'[a-z]+', text.lower()))
        for match in re.finditer(r'[\u4e00-\u9fff]{2,}', text):
            tokens.add(match.group())
        return tokens

    def _semantic_selection(self, context: ToolContext) -> List[ToolSelection]:
        selections = []
        query = context.query.lower()
        query_tokens = self._extract_tokens(query)

        for tool_name, metadata in self._tools.items():
            score = 0.0

            desc_tokens = self._extract_tokens(metadata.description.lower())
            overlap = query_tokens & desc_tokens
            if overlap:
                score += 0.3 * len(overlap) / max(len(desc_tokens), 1)

            for keyword in metadata.keywords:
                if keyword.lower() in query or keyword.lower() in query.replace(" ", ""):
                    score += 0.4

            desc_lower = metadata.description.lower()
            for token in query_tokens:
                if len(token) >= 2 and token in desc_lower:
                    score += 0.15

            for entity in context.entities.values():
                if isinstance(entity, str) and entity.lower() in desc_lower:
                    score += 0.2

            if score > 0.3:
                selections.append(ToolSelection(
                    tool_name=tool_name,
                    confidence=min(score, 1.0),
                    reasoning=f"Semantic similarity score: {score:.2f}",
                    strategy_used=ToolSelectionStrategy.SEMANTIC,
                ))

        return selections
    
    def _intent_based_selection(self, context: ToolContext) -> List[ToolSelection]:
        """Intent-based tool selection"""
        selections = []
        
        intent = context.intent or self._classify_intent(context.query)
        
        if intent in self.INTENT_TOOL_MAP:
            for tool_name in self.INTENT_TOOL_MAP[intent]:
                # Match both unprefixed and prefixed tool names
                if tool_name in self._tools:
                    selections.append(ToolSelection(
                        tool_name=tool_name,
                        confidence=0.85,
                        reasoning=f"Matched intent: {intent}",
                        strategy_used=ToolSelectionStrategy.INTENT_BASED,
                    ))
                else:
                    for registered_name in self._tools:
                        if registered_name.endswith("___" + tool_name):
                            selections.append(ToolSelection(
                                tool_name=registered_name,
                                confidence=0.85,
                                reasoning=f"Matched intent: {intent}",
                                strategy_used=ToolSelectionStrategy.INTENT_BASED,
                            ))
        
        return selections
    
    def _adaptive_selection(self, context: ToolContext) -> List[ToolSelection]:
        """Adaptive learning-based selection"""
        selections = []
        
        # Get base selections from hybrid approach
        base_selections = self._hybrid_selection(context)
        
        # Adjust confidence based on historical performance
        for sel in base_selections:
            stats = self._performance_stats[sel.tool_name]
            total_usage = stats["success_count"] + stats["failure_count"]
            
            if total_usage > 0:
                historical_success = stats["success_count"] / total_usage
                # Blend current confidence with historical performance
                adjusted_confidence = 0.6 * sel.confidence + 0.4 * historical_success
                sel.confidence = adjusted_confidence
                sel.strategy_used = ToolSelectionStrategy.ADAPTIVE
                sel.reasoning += f" (adjusted by historical performance: {historical_success:.2f})"
            
            selections.append(sel)
        
        return selections
    
    def _hybrid_selection(self, context: ToolContext) -> List[ToolSelection]:
        """Hybrid selection combining multiple strategies"""
        all_selections = []
        
        # Collect from all strategies
        rule_selections = self._rule_based_selection(context)
        semantic_selections = self._semantic_selection(context)
        intent_selections = self._intent_based_selection(context)
        
        all_selections.extend(rule_selections)
        all_selections.extend(semantic_selections)
        all_selections.extend(intent_selections)
        
        # Merge and boost confidence for tools selected by multiple strategies
        tool_scores: Dict[str, List[ToolSelection]] = defaultdict(list)
        for sel in all_selections:
            tool_scores[sel.tool_name].append(sel)
        
        merged = []
        for tool_name, sels in tool_scores.items():
            if len(sels) == 1:
                merged.append(sels[0])
            else:
                # Boost confidence for consensus
                avg_confidence = sum(s.confidence for s in sels) / len(sels)
                boost = 0.1 * (len(sels) - 1)  # 10% boost per additional strategy
                merged.append(ToolSelection(
                    tool_name=tool_name,
                    confidence=min(avg_confidence + boost, 1.0),
                    reasoning=f"Consensus from {len(sels)} strategies: " + 
                             "; ".join(s.reasoning for s in sels),
                    strategy_used=ToolSelectionStrategy.HYBRID,
                ))
        
        return merged
    
    def _classify_intent(self, query: str) -> str:
        """
        Classify query intent
        
        Args:
            query: User query
            
        Returns:
            Intent classification
        """
        query_lower = query.lower()
        
        # Simple rule-based classification
        patterns = {
            "statement": [
                r"我(的|家|家里|家里面).*(是|叫|有|住|在|号码|电话|车牌|地址)",
                r"我.*(手机号|生日|年龄|车牌号|地址|门牌)",
                r"(告诉|跟).*你.*(说|一下|个事)",
                r"^(备注|说明|补充).*一下",
                r"^(知道了|好的|嗯|哦|行|OK|ok)",
            ],
            "turn_on": [r"打开|开.*灯|开.*空调|开.*电视"],
            "turn_off": [r"关闭|关掉|关.*灯|关.*空调|关.*电视"],
            "adjust": [r"调.*温度|调.*亮度|调.*音量|设置"],
            "query_state": [r"状态|开了吗|关了吗|怎么样"],
            "query_environment": [r"温度|湿度|环境|空气质量"],
            "view_camera": [r"摄像头|画面|看看|监控"],
            "recognize_face": [r"谁|身份|认识|我是谁"],
            "create_rule": [r"规则|自动化|创建|设置.*当"],
            "activate_scene": [r"场景|模式|执行"],
            "get_time": [r"时间|几点|日期"],
            "memory": [r"记住|忘记|记得|我叫|我的名字|记一下|帮我记"],
        }
        
        for intent, patterns_list in patterns.items():
            for pattern in patterns_list:
                if re.search(pattern, query_lower):
                    return intent
        
        return "unknown"
    
    def is_no_tool_query(self, query: str) -> bool:
        intent = self._classify_intent(query)
        return intent in self.NO_TOOL_INTENTS
    
    def set_llm_proxy(self, llm_proxy: "LLMProxy") -> None:
        self._llm_proxy = llm_proxy

    # ──────────────────────────────────────────────────────────
    #  LLM-based classification prompt (generic, keyword-free)
    # ──────────────────────────────────────────────────────────
    _LLM_CLASSIFY_PROMPT = """You are a query classifier for a smart home AI agent. Your ONLY job is to decide whether the user's query requires calling any tools (device control, camera, face recognition, environment data, etc.), or whether it can be answered directly.

## Available tools and their purposes:
{tool_list}

## Classification rules:
- If the user is just **chatting, greeting, making small talk, or sharing personal information** (e.g. "my license plate is...", "I live at...", "my phone number is...", "I'm XX years old") → **NO tools needed**.
- If the user is **telling you something without asking for any action or query** → **NO tools needed**.
- If the user is **confirming or acknowledging** (e.g. "OK", "got it", "I see") → **NO tools needed**.
- If the user asks about **general knowledge, advice, explanations** → **NO tools needed**.
- If the user asks about **camera footage, what's happening in a room** → vision_understand.
- If the user wants to **control a device** (turn on/off, adjust) → send_ctrl_rpc, get_devices.
- If the user wants to **query device status** (temperature, humidity, is something on?) → send_get_rpc, get_devices.
- If the user asks about **face identity, who someone is** → who_am_i.
- If the user wants to **create/delete/modify automation rules** → create_rule.
- If the user wants to **trigger a scene/mode** → trigger_manual_scene.

## User query:
{query}

Think carefully: does this query truly require calling any tool? Only answer YES if a tool call is strictly necessary to fulfill the user's request.

Respond with ONLY a JSON object, nothing else:
{{"needs_tools": true, "tools": ["tool_name1"], "reason": "brief explanation in English"}}
If no tools are needed:
{{"needs_tools": false, "tools": [], "reason": "brief explanation in English"}}"""

    async def _llm_classify_query(
        self, query: str, tool_names: List[str]
    ) -> Tuple[Optional[List[str]], bool, str]:
        """Use LLM to semantically classify whether the query needs tools.

        Args:
            query: User query text.
            tool_names: Registered tool full-names (may include prefixes like
                        ``local_default___vision_understand``).

        Returns:
            (short_tool_names or None, is_no_tool, reason):
            - short_tool_names: list of *short* tool names (e.g. ``vision_understand``),
              suitable for ``_filter_tools_for_llm`` suffix-matching.  None if LLM
              unavailable.
            - is_no_tool: True if LLM determined no tools needed.
            - reason: human-readable classification reason.
        """
        if self._llm_proxy is None:
            logger.debug("No LLM proxy available for query classification")
            return None, False, "LLM proxy not available"

        # Build short-name → full-name mapping and a human-readable tool list.
        # Strip common prefixes so the LLM sees clean names like "vision_understand".
        _KNOWN_PREFIXES = ("local_default___", "miot_devices___", "miot_manual_scenes___")
        short_to_full: dict[str, str] = {}
        tool_lines: list[str] = []

        for full_name in tool_names:
            short_name = full_name
            for prefix in _KNOWN_PREFIXES:
                if full_name.startswith(prefix):
                    short_name = full_name[len(prefix):]
                    break
            short_to_full[short_name] = full_name

            tool_meta = self._tools.get(full_name)
            if tool_meta:
                tool_lines.append(f"- {short_name}: {tool_meta.description[:120]}")
            else:
                tool_lines.append(f"- {short_name}")

        tool_list_str = "\n".join(tool_lines) if tool_lines else "(no tools registered)"

        prompt = self._LLM_CLASSIFY_PROMPT.format(
            tool_list=tool_list_str, query=query,
        )

        messages: list[dict[str, str]] = [
            {"role": "user", "content": prompt},
        ]

        try:
            result = await self._llm_proxy.async_call_llm(messages, tools=None)
        except Exception as e:
            logger.warning("LLM classification call failed: %s, falling back to keywords", e)
            return None, False, f"LLM call error: {e}"

        if not result.get("success"):
            logger.warning("LLM classification returned failure: %s", result.get("error", "unknown"))
            return None, False, "LLM call failed"

        content = (result.get("content") or "").strip()
        # Strip markdown code fences if present
        if content.startswith("```"):
            content = content.split("\n", 1)[-1]
            if content.endswith("```"):
                content = content[: content.rfind("```")].strip()

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            logger.warning("LLM classification returned invalid JSON: %s", content[:200])
            return None, False, f"Invalid JSON: {content[:100]}"

        needs_tools = parsed.get("needs_tools", True)
        llm_tool_names: list[str] = parsed.get("tools", [])
        reason: str = parsed.get("reason", "") or ""

        if not needs_tools:
            return [], True, reason

        # Validate: accept tool names that are either an exact short-name match
        # or a suffix match against registered full-names.
        valid_short_names: list[str] = []
        for name in llm_tool_names:
            # 1) exact short-name match
            if name in short_to_full:
                valid_short_names.append(name)
                continue
            # 2) suffix match against any registered full-name
            for reg_full_name in self._tools:
                if reg_full_name.endswith(name):
                    # derive the short name for consistency
                    short = name
                    for prefix in _KNOWN_PREFIXES:
                        if reg_full_name.startswith(prefix):
                            short = reg_full_name[len(prefix):]
                            break
                    if short not in valid_short_names:
                        valid_short_names.append(short)
                    break

        if not valid_short_names:
            logger.info(
                "LLM suggested tools %s, but none matched registered tools — treating as no-tool",
                llm_tool_names,
            )
            return [], True, reason

        return valid_short_names, False, reason

    async def async_select_tools(
        self,
        context: ToolContext,
        top_k: int = 5,
        use_llm: bool = True,
    ) -> Tuple[List[ToolSelection], bool]:
        """
        Tool pre-selection — keyword-first, LLM only when keywords are inconclusive.

        Strategy (ordered):
        1. Keyword fast-path — ~0 ms.  Returns immediately when clear.
        2. Keyword HYBRID — ~0 ms.  Returns immediately when tools are matched.
        3. LLM classification — only reached when both keyword layers produce no
           clear answer.  This avoids 20-second LLM latency for >90% of queries.

        Returns:
            (selections, is_no_tool_query)
        """
        query = context.query

        # ── Layer 1: Fast-path no-tool intents (keyword patterns, ~0 ms) ──
        if self.is_no_tool_query(query):
            logger.info("No-tool query detected (intent: chat/memory/statement), skipping all tools")
            return [], True

        # ── Layer 2: Keyword-based HYBRID selection (~0 ms) ──
        keyword_selections = self.select_tools(context, top_k=top_k)
        if keyword_selections:
            logger.info("Keyword HYBRID tool selection: %s",
                         [s.tool_name for s in keyword_selections])
            return keyword_selections, False

        # ── Layer 3: LLM-based classification (slow, only when needed) ──
        if use_llm and self._llm_proxy is not None:
            registered_names = list(self._tools.keys())
            llm_tools, is_no_tool, reason = await self._llm_classify_query(
                query, registered_names,
            )

            if is_no_tool:
                logger.info(
                    "LLM classification: NO tools needed for query '%s' — %s",
                    query[:60], reason,
                )
                return [], True

            if llm_tools is not None:
                logger.info(
                    "LLM classification: tools=%s for query '%s' — %s",
                    llm_tools, query[:60], reason,
                )
                selections = [
                    ToolSelection(
                        tool_name=name,
                        confidence=0.90,
                        reasoning=f"LLM: {reason}",
                        strategy_used=ToolSelectionStrategy.LLM_BASED,
                    )
                    for name in llm_tools
                ]
                return selections[:top_k], False

            # LLM call failed, treat as inconclusive
            logger.info("LLM classification unavailable, treating as no-tool")

        # No tools matched by any strategy — safe to return no tools
        return [], self.is_no_tool_query(query)
    
    def extract_parameters(
        self,
        tool_name: str,
        context: ToolContext,
    ) -> Dict[str, Any]:
        """
        Extract parameters for tool from context
        
        Args:
            tool_name: Tool name
            context: Tool context
            
        Returns:
            Extracted parameters
        """
        metadata = self._tools.get(tool_name)
        if not metadata:
            return {}
        
        params = {}
        
        # Extract from entities
        for param_name in metadata.required_params + metadata.optional_params:
            if param_name in context.entities:
                params[param_name] = context.entities[param_name]
        
        # Extract from query using simple patterns
        if tool_name == "cached_get_device_state":
            # Try to extract device name/entity_id
            device_patterns = [
                r"(?:客厅|卧室|厨房|卫生间|书房)(?:的)?([^\s]+(?:灯|空调|电视|窗帘))",
                r"([^\s]+(?:灯|空调|电视|窗帘))(?:的)?状态",
            ]
            for pattern in device_patterns:
                match = re.search(pattern, context.query)
                if match:
                    params["entity_id"] = match.group(1)
                    break
        
        return params
    
    def record_result(
        self,
        tool_name: str,
        success: bool,
        response_time: float = 0.0,
    ) -> None:
        """
        Record tool execution result for learning
        
        Args:
            tool_name: Tool name
            success: Whether execution was successful
            response_time: Response time in seconds
        """
        stats = self._performance_stats[tool_name]
        
        if success:
            stats["success_count"] += 1
        else:
            stats["failure_count"] += 1
        
        stats["total_time"] += response_time
        stats["usage_count"] += 1
        
        # Update metadata
        if tool_name in self._tools:
            metadata = self._tools[tool_name]
            total = stats["success_count"] + stats["failure_count"]
            metadata.success_rate = stats["success_count"] / total if total > 0 else 1.0
            metadata.avg_response_time = stats["total_time"] / stats["usage_count"] if stats["usage_count"] > 0 else 0.0
            metadata.usage_count = stats["usage_count"]
        
        logger.debug(f"Recorded result for {tool_name}: success={success}")
    
    def get_tool_stats(self, tool_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Get tool performance statistics
        
        Args:
            tool_name: Specific tool (None for all)
            
        Returns:
            Statistics dictionary
        """
        if tool_name:
            return dict(self._performance_stats[tool_name])
        
        return {name: dict(stats) for name, stats in self._performance_stats.items()}
    
    def set_intent_classifier(self, classifier: Callable[[str], str]) -> None:
        """
        Set custom intent classifier
        
        Args:
            classifier: Function that takes query and returns intent
        """
        self._intent_classifier = classifier
