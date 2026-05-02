# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Complexity Analyzer Module

任务复杂度分析器 - 在执行前预判任务复杂度，选择最优执行策略

分析维度:
1. 意图数量
2. 实体数量
3. 是否需要上下文
4. 是否需要工具调用
5. 是否有条件逻辑
6. 是否有时间逻辑
7. 是否多步骤
"""

import re
import logging
from enum import IntEnum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Tuple

logger = logging.getLogger(__name__)


class TaskComplexity(IntEnum):
    """任务复杂度等级"""
    TRIVIAL = 1     # 规则可直接处理 (开灯、关灯)
    SIMPLE = 2      # 单Agent可处理 (查询温度)
    MODERATE = 3    # 需要工具调用 (创建规则)
    COMPLEX = 4     # 需要多Agent协作 (条件联动)


@dataclass
class ComplexityFactors:
    """复杂度因子"""
    intent_count: int = 1
    entity_count: int = 0
    requires_context: bool = False
    requires_tools: bool = False
    tool_count: int = 0
    has_condition: bool = False
    has_temporal: bool = False
    is_multi_step: bool = False
    has_negation: bool = False
    has_comparison: bool = False
    detected_intents: List[str] = field(default_factory=list)
    detected_entities: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent_count": self.intent_count,
            "entity_count": self.entity_count,
            "requires_context": self.requires_context,
            "requires_tools": self.requires_tools,
            "tool_count": self.tool_count,
            "has_condition": self.has_condition,
            "has_temporal": self.has_temporal,
            "is_multi_step": self.is_multi_step,
            "has_negation": self.has_negation,
            "has_comparison": self.has_comparison,
            "detected_intents": self.detected_intents,
            "detected_entities": self.detected_entities,
        }


@dataclass
class AnalysisResult:
    """分析结果"""
    complexity: TaskComplexity
    factors: ComplexityFactors
    confidence: float
    suggested_mode: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "complexity": self.complexity.name,
            "complexity_value": self.complexity.value,
            "factors": self.factors.to_dict(),
            "confidence": self.confidence,
            "suggested_mode": self.suggested_mode,
        }


class ComplexityAnalyzer:
    """
    任务复杂度分析器 - AHAA架构的智能决策层

    使用规则引擎快速判断任务复杂度，毫秒级响应。

    用法:
        analyzer = ComplexityAnalyzer()
        result = await analyzer.analyze("开灯")
        print(result.complexity)  # TaskComplexity.TRIVIAL
    """

    TRIVIAL_PATTERNS = [
        (r"^(?:打开|开|开启|关闭|关|关掉)\s*(?:.*?)(?:灯|空调|窗帘|风扇|净化器|电视|音箱)", TaskComplexity.TRIVIAL),
        (r"^(?:打开|开|开启|关闭|关|关掉)\s*(?:.*?)(?:的)?\s*(?:灯|照明|灯光)", TaskComplexity.TRIVIAL),
    ]

    SIMPLE_PATTERNS = [
        (r"(?:温度|湿度|气压|亮度|状态)\s*(?:是多少|多少|几度|几|什么)", TaskComplexity.SIMPLE),
        (r"(?:看看|查看|看一下)\s*(?:.*?)(?:的)?\s*(?:摄像头|监控|画面|情况)", TaskComplexity.SIMPLE),
        (r"^(?:你好|hi|hello|嗨|哈喽|谢谢|感谢)", TaskComplexity.SIMPLE),
    ]

    MODERATE_PATTERNS = [
        (r"(?:创建|设置|添加|新建)\s*(?:一个)?\s*(?:规则|自动化|场景|定时)", TaskComplexity.MODERATE),
        (r"(?:把|将)\s*(?:.*?)(?:调|设置|设定)\s*(?:到|成|为)\s*\d+", TaskComplexity.MODERATE),
    ]

    COMPLEX_PATTERNS = [
        (r"(?:如果|当|假如|若是|要是).*?(?:就|则|那么|那就|就自动)", TaskComplexity.COMPLEX),
        (r"(?:并且|然后|同时|并且|而且)", TaskComplexity.COMPLEX),
        (r"(?:每天|每周|定时|几点|之后|以后)", TaskComplexity.COMPLEX),
    ]

    CONDITION_KEYWORDS = ["如果", "当", "假如", "若是", "要是", "就", "则", "那么"]
    TEMPORAL_KEYWORDS = ["每天", "每周", "每月", "定时", "几点", "之后", "以后", "的时候", "时"]
    MULTI_STEP_KEYWORDS = ["然后", "接着", "再", "同时", "并且", "而且"]
    NEGATION_KEYWORDS = ["不", "没", "别", "勿", "不要", "禁止"]
    COMPARISON_KEYWORDS = ["大于", "小于", "等于", "超过", "低于", "高于", "以上", "以下"]

    def __init__(self):
        self._custom_patterns: List[Tuple[str, TaskComplexity]] = []
        logger.info("ComplexityAnalyzer initialized")

    def register_pattern(self, pattern: str, complexity: TaskComplexity) -> None:
        self._custom_patterns.append((pattern, complexity))
        logger.info(f"Registered custom pattern: {pattern} -> {complexity.name}")

    async def analyze(self, query: str, context: Optional[Dict[str, Any]] = None) -> AnalysisResult:
        factors = ComplexityFactors()
        confidence = 0.8

        for pattern, complexity in self.TRIVIAL_PATTERNS:
            if re.search(pattern, query, re.IGNORECASE):
                factors.intent_count = 1
                factors.detected_intents.append("device_control")
                self._extract_entities(query, factors)
                return AnalysisResult(
                    complexity=complexity,
                    factors=factors,
                    confidence=0.95,
                    suggested_mode="rule_direct",
                )

        for pattern, complexity in self.SIMPLE_PATTERNS:
            if re.search(pattern, query, re.IGNORECASE):
                factors.intent_count = 1
                self._extract_entities(query, factors)
                if complexity == TaskComplexity.SIMPLE:
                    factors.requires_tools = True
                    factors.tool_count = 1
                return AnalysisResult(
                    complexity=complexity,
                    factors=factors,
                    confidence=0.9,
                    suggested_mode="single_agent",
                )

        for pattern, complexity in self.COMPLEX_PATTERNS:
            if re.search(pattern, query, re.IGNORECASE):
                factors.has_condition = any(kw in query for kw in self.CONDITION_KEYWORDS)
                factors.has_temporal = any(kw in query for kw in self.TEMPORAL_KEYWORDS)
                factors.is_multi_step = any(kw in query for kw in self.MULTI_STEP_KEYWORDS)
                factors.requires_tools = True
                factors.requires_context = True
                factors.tool_count = 2 if factors.is_multi_step else 1
                factors.intent_count = 2 if factors.is_multi_step else 1
                self._extract_entities(query, factors)

                suggested = "pipeline" if factors.is_multi_step else "single_agent"
                return AnalysisResult(
                    complexity=complexity,
                    factors=factors,
                    confidence=0.85,
                    suggested_mode=suggested,
                )

        for pattern, complexity in self._custom_patterns:
            if re.search(pattern, query, re.IGNORECASE):
                factors.intent_count = 1
                self._extract_entities(query, factors)
                return AnalysisResult(
                    complexity=complexity,
                    factors=factors,
                    confidence=0.8,
                    suggested_mode="single_agent",
                )

        for pattern, complexity in self.MODERATE_PATTERNS:
            if re.search(pattern, query, re.IGNORECASE):
                factors.requires_tools = True
                factors.tool_count = 1
                factors.intent_count = 1
                self._extract_entities(query, factors)
                return AnalysisResult(
                    complexity=complexity,
                    factors=factors,
                    confidence=0.75,
                    suggested_mode="single_agent",
                )

        factors.requires_tools = True
        factors.tool_count = 1
        factors.intent_count = 1
        self._extract_entities(query, factors)
        return AnalysisResult(
            complexity=TaskComplexity.MODERATE,
            factors=factors,
            confidence=0.6,
            suggested_mode="single_agent",
        )

    def _extract_entities(self, query: str, factors: ComplexityFactors) -> None:
        location_match = re.search(r"(客厅|卧室|厨房|书房|卫生间|浴室|阳台|门口|餐厅|主卧|次卧|儿童房)", query)
        if location_match:
            factors.detected_entities["location"] = location_match.group(1)
            factors.entity_count += 1

        device_match = re.search(r"(灯|空调|窗帘|风扇|净化器|电视|音箱|加湿器|热水器|地暖)", query)
        if device_match:
            factors.detected_entities["device_type"] = device_match.group(1)
            factors.entity_count += 1

        temp_match = re.search(r"(\d+)\s*(?:度|℃|°)", query)
        if temp_match:
            factors.detected_entities["temperature"] = int(temp_match.group(1))
            factors.entity_count += 1

        factors.has_negation = any(kw in query for kw in self.NEGATION_KEYWORDS)
        factors.has_comparison = any(kw in query for kw in self.COMPARISON_KEYWORDS)

    def get_analysis_summary(self, result: AnalysisResult) -> str:
        return (
            f"Complexity: {result.complexity.name} | "
            f"Confidence: {result.confidence:.0%} | "
            f"Mode: {result.suggested_mode} | "
            f"Intents: {result.factors.intent_count} | "
            f"Tools: {result.factors.tool_count}"
        )
