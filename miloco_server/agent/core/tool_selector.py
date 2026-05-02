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
    NO_TOOL_INTENTS = {"chat", "memory"}

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
                    if tool_name in self._tools:
                        selections.append(ToolSelection(
                            tool_name=tool_name,
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
                if tool_name in self._tools:
                    selections.append(ToolSelection(
                        tool_name=tool_name,
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
    
    _TOOL_SELECT_PROMPT = """你是一个查询分类器。根据用户查询，判断需要调用哪些工具。

## 可用工具
{tool_list}

## 分类规则
- 闲聊/问候/情感表达/角色设定 → 不需要工具
- 记忆操作(记住/忘记/记得/我叫什么/我的名字) → 不需要工具
- 已有足够信息可直接回答 → 不需要工具
- 设备控制(开/关/调节) → send_ctrl_rpc
- 设备状态查询 → send_get_rpc, get_devices
- 环境数据(温度/湿度/天气/空气质量/有人吗) → 系统提示中已有，直接回答（除非用户要求最新数据）
- 摄像头/图像/看画面 → vision_understand
- 人脸识别/谁在 → who_am_i
- 自动化规则创建 → create_rule
- 场景触发 → trigger_manual_scene, trigger_automation
- 时间查询 → get_current_time

## 用户查询
{query}

只返回JSON，不要其他内容：{{"tools": ["tool_name"], "reason": "简要原因"}}
不需要工具时：{{"tools": [], "reason": "简要原因"}}"""

    async def async_select_tools(
        self,
        context: ToolContext,
        top_k: int = 5,
    ) -> Tuple[List[ToolSelection], bool]:
        """
        Tool pre-selection using local HYBRID strategy (no LLM call).
        Uses rule-based + semantic + intent matching for fast selection.

        Returns:
            (selections, is_no_tool_query): selections is the list of tool selections,
            is_no_tool_query indicates whether the query definitively needs no tools.
        """
        query = context.query

        if self.is_no_tool_query(query):
            logger.info("No-tool query detected (intent: chat/memory), skipping tool selection")
            return [], True

        selections = self.select_tools(context, top_k=top_k)

        if not selections:
            return [], self.is_no_tool_query(query)

        logger.info("Local HYBRID tool selection: %s",
                     [s.tool_name for s in selections])
        return selections, False
    
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
