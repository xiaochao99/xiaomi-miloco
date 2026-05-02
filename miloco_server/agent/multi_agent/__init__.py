# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Adaptive Hybrid Agent Architecture (AHAA) Module

自适应混合智能体架构 - 根据任务复杂度动态选择执行策略
"""

from .shared_blackboard import SharedBlackboard, BlackboardEntry, BlackboardNamespace
from .complexity_analyzer import ComplexityAnalyzer, TaskComplexity, ComplexityFactors, AnalysisResult
from .rule_engine import RuleEngine, Rule, RuleAction, RuleMatchResult
from .capability_registry import CapabilityRegistry, Capability, AgentCapability
from .adaptive_orchestrator import AdaptiveOrchestrator, ExecutionMode, ExecutionResult, ExecutionPlan
from .ahaa_dispatcher import AHAADispatcher

__all__ = [
    "SharedBlackboard",
    "BlackboardEntry",
    "BlackboardNamespace",
    "ComplexityAnalyzer",
    "TaskComplexity",
    "ComplexityFactors",
    "AnalysisResult",
    "RuleEngine",
    "Rule",
    "RuleAction",
    "RuleMatchResult",
    "CapabilityRegistry",
    "Capability",
    "AgentCapability",
    "AdaptiveOrchestrator",
    "ExecutionMode",
    "ExecutionResult",
    "ExecutionPlan",
    "AHAADispatcher",
]
