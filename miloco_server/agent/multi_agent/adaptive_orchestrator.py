# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Adaptive Orchestrator Module

自适应编排器 - AHAA架构的核心组件

根据复杂度分析结果，动态选择最优执行模式:
- TRIVIAL: 规则引擎直接响应，0次LLM调用
- SIMPLE: 单Agent处理，1次LLM调用
- MODERATE: 单Agent + 工具，1-2次LLM调用
- COMPLEX: 多Agent协作，2-3次LLM调用
"""

import asyncio
import logging
import time
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Callable, Awaitable
from datetime import datetime

from .complexity_analyzer import ComplexityAnalyzer, TaskComplexity, AnalysisResult
from .rule_engine import RuleEngine, RuleMatchResult
from .shared_blackboard import SharedBlackboard, BlackboardNamespace
from .capability_registry import CapabilityRegistry, Capability

logger = logging.getLogger(__name__)


class ExecutionMode(Enum):
    """执行模式"""
    RULE_DIRECT = auto()      # 规则直接响应
    SINGLE_AGENT = auto()     # 单Agent处理
    PARALLEL = auto()         # 并行多Agent
    PIPELINE = auto()         # 流水线多Agent
    FALLBACK = auto()         # 降级模式


@dataclass
class ExecutionStep:
    """执行步骤"""
    step_id: int
    agent_id: str
    query: str
    depends_on: List[int] = field(default_factory=list)
    timeout_seconds: int = 30
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionPlan:
    """执行计划"""
    mode: ExecutionMode
    steps: List[ExecutionStep]
    analysis: AnalysisResult
    max_parallel: int = 3
    total_timeout_seconds: int = 60

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode.name,
            "steps": [
                {
                    "step_id": s.step_id,
                    "agent_id": s.agent_id,
                    "query": s.query[:100],
                    "depends_on": s.depends_on,
                }
                for s in self.steps
            ],
            "analysis": self.analysis.to_dict(),
        }


@dataclass
class ExecutionResult:
    """执行结果"""
    success: bool
    response: str
    mode: ExecutionMode
    steps_executed: int
    total_time_ms: float
    llm_calls: int
    rule_matched: bool = False
    agent_results: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "response": self.response[:200],
            "mode": self.mode.name,
            "steps_executed": self.steps_executed,
            "total_time_ms": self.total_time_ms,
            "llm_calls": self.llm_calls,
            "rule_matched": self.rule_matched,
            "agent_results": {k: str(v)[:100] for k, v in self.agent_results.items()},
            "metadata": self.metadata,
        }


AgentExecuteFunc = Callable[[str, str, Dict[str, Any]], Awaitable[str]]


class AdaptiveOrchestrator:
    """
    自适应编排器 - AHAA架构的核心

    根据任务复杂度动态选择最优执行策略，实现资源的最优利用。

    用法:
        orchestrator = AdaptiveOrchestrator(
            blackboard=blackboard,
            rule_engine=rule_engine,
            complexity_analyzer=analyzer,
            capability_registry=registry,
        )

        # 注册Agent执行函数
        orchestrator.register_agent("device_agent", device_agent_execute)

        # 执行任务
        result = await orchestrator.execute("开灯", "session_123")
    """

    def __init__(
        self,
        blackboard: Optional[SharedBlackboard] = None,
        rule_engine: Optional[RuleEngine] = None,
        complexity_analyzer: Optional[ComplexityAnalyzer] = None,
        capability_registry: Optional[CapabilityRegistry] = None,
    ):
        self._blackboard = blackboard or SharedBlackboard()
        self._rule_engine = rule_engine or RuleEngine()
        self._complexity_analyzer = complexity_analyzer or ComplexityAnalyzer()
        self._capability_registry = capability_registry or CapabilityRegistry()

        self._agent_executors: Dict[str, AgentExecuteFunc] = {}
        self._synthesizer: Optional[Callable[[str, List[str]], Awaitable[str]]] = None

        self._stats = {
            "total_requests": 0,
            "rule_direct_count": 0,
            "single_agent_count": 0,
            "parallel_count": 0,
            "pipeline_count": 0,
            "fallback_count": 0,
            "total_llm_calls": 0,
            "avg_response_time_ms": 0.0,
        }

        logger.info("AdaptiveOrchestrator initialized")

    def register_agent(self, agent_id: str, executor: AgentExecuteFunc) -> None:
        self._agent_executors[agent_id] = executor
        logger.info(f"Registered agent executor: {agent_id}")

    def register_synthesizer(self, synthesizer: Callable[[str, List[str]], Awaitable[str]]) -> None:
        self._synthesizer = synthesizer
        logger.info("Registered synthesizer")

    async def execute(
        self,
        query: str,
        session_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> ExecutionResult:
        start_time = time.time()
        self._stats["total_requests"] += 1

        try:
            analysis = await self._complexity_analyzer.analyze(query, context)
            logger.info(f"Complexity analysis: {self._complexity_analyzer.get_analysis_summary(analysis)}")

            plan = await self._create_plan(query, session_id, analysis)

            if plan.mode == ExecutionMode.RULE_DIRECT:
                result = await self._execute_rule_direct(query, plan)
            elif plan.mode == ExecutionMode.SINGLE_AGENT:
                result = await self._execute_single_agent(query, session_id, plan)
            elif plan.mode == ExecutionMode.PARALLEL:
                result = await self._execute_parallel(query, session_id, plan)
            elif plan.mode == ExecutionMode.PIPELINE:
                result = await self._execute_pipeline(query, session_id, plan)
            else:
                result = await self._execute_fallback(query, session_id, plan)

            elapsed_ms = (time.time() - start_time) * 1000
            result.total_time_ms = elapsed_ms

            self._update_stats(plan.mode, result)
            self._capability_registry.record_performance(
                agent_id="orchestrator",
                response_time_ms=elapsed_ms,
                success=result.success,
                task_type=analysis.complexity.name,
            )

            await self._blackboard.write(
                key=f"last_result_{session_id}",
                value=result.to_dict(),
                source="orchestrator",
                namespace=BlackboardNamespace.RESULT,
            )

            return result

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            logger.error(f"Orchestrator error: {e}", exc_info=True)
            return ExecutionResult(
                success=False,
                response=f"抱歉，处理您的请求时遇到了问题: {str(e)}",
                mode=ExecutionMode.FALLBACK,
                steps_executed=0,
                total_time_ms=elapsed_ms,
                llm_calls=0,
                metadata={"error": str(e)},
            )

    async def _create_plan(
        self,
        query: str,
        session_id: str,
        analysis: AnalysisResult,
    ) -> ExecutionPlan:
        rule_result = await self._rule_engine.match(query)

        if rule_result and analysis.complexity == TaskComplexity.TRIVIAL:
            return ExecutionPlan(
                mode=ExecutionMode.RULE_DIRECT,
                steps=[ExecutionStep(step_id=0, agent_id="rule_engine", query=query)],
                analysis=analysis,
            )

        if analysis.complexity <= TaskComplexity.SIMPLE:
            agent_id = self._select_agent_for_simple(analysis, rule_result)
            return ExecutionPlan(
                mode=ExecutionMode.SINGLE_AGENT,
                steps=[ExecutionStep(step_id=0, agent_id=agent_id, query=query)],
                analysis=analysis,
            )

        if analysis.complexity == TaskComplexity.MODERATE:
            agent_id = self._select_agent_for_moderate(analysis)
            return ExecutionPlan(
                mode=ExecutionMode.SINGLE_AGENT,
                steps=[ExecutionStep(step_id=0, agent_id=agent_id, query=query)],
                analysis=analysis,
            )

        if analysis.factors.is_multi_step:
            steps = self._plan_pipeline_steps(query, analysis)
            return ExecutionPlan(
                mode=ExecutionMode.PIPELINE,
                steps=steps,
                analysis=analysis,
            )

        if analysis.factors.intent_count > 1:
            steps = self._plan_parallel_steps(query, analysis)
            return ExecutionPlan(
                mode=ExecutionMode.PARALLEL,
                steps=steps,
                analysis=analysis,
                max_parallel=3,
            )

        agent_id = self._select_agent_for_complex(analysis)
        return ExecutionPlan(
            mode=ExecutionMode.SINGLE_AGENT,
            steps=[ExecutionStep(step_id=0, agent_id=agent_id, query=query)],
            analysis=analysis,
        )

    def _select_agent_for_simple(
        self,
        analysis: AnalysisResult,
        rule_result: Optional[RuleMatchResult],
    ) -> str:
        if rule_result:
            if rule_result.action.value == 1:
                agent = self._capability_registry.get_optimal_agent(Capability.DEVICE_CONTROL)
            elif rule_result.action.value == 2:
                agent = self._capability_registry.get_optimal_agent(Capability.DEVICE_QUERY)
            elif rule_result.action.value == 4:
                agent = self._capability_registry.get_optimal_agent(Capability.VISION_ANALYSIS)
            else:
                agent = self._capability_registry.get_optimal_agent(Capability.CHAT)

            if agent:
                return agent.agent_id

        if "device" in str(analysis.factors.detected_intents):
            agent = self._capability_registry.get_optimal_agent(Capability.DEVICE_CONTROL)
        else:
            agent = self._capability_registry.get_optimal_agent(Capability.CHAT)

        return agent.agent_id if agent else "default"

    def _select_agent_for_moderate(self, analysis: AnalysisResult) -> str:
        if analysis.factors.detected_entities.get("device_type"):
            agent = self._capability_registry.get_optimal_agent(Capability.DEVICE_CONTROL)
        elif analysis.factors.has_condition:
            agent = self._capability_registry.get_optimal_agent(Capability.AUTOMATION)
        else:
            agent = self._capability_registry.get_optimal_agent(Capability.CHAT)

        return agent.agent_id if agent else "default"

    def _select_agent_for_complex(self, analysis: AnalysisResult) -> str:
        if analysis.factors.has_condition:
            agent = self._capability_registry.get_optimal_agent(Capability.AUTOMATION)
        elif analysis.factors.detected_entities.get("device_type"):
            agent = self._capability_registry.get_optimal_agent(Capability.DEVICE_CONTROL)
        else:
            agent = self._capability_registry.get_optimal_agent(Capability.CHAT)

        return agent.agent_id if agent else "default"

    def _plan_pipeline_steps(
        self,
        query: str,
        analysis: AnalysisResult,
    ) -> List[ExecutionStep]:
        steps = []

        if analysis.factors.detected_entities.get("device_type"):
            steps.append(ExecutionStep(
                step_id=0,
                agent_id=self._get_agent_id(Capability.DEVICE_QUERY),
                query=f"查询设备状态: {query}",
            ))

        if analysis.factors.has_condition:
            steps.append(ExecutionStep(
                step_id=1,
                agent_id=self._get_agent_id(Capability.AUTOMATION),
                query=f"创建自动化规则: {query}",
                depends_on=[0] if steps else [],
            ))
        elif analysis.factors.detected_entities.get("device_type"):
            steps.append(ExecutionStep(
                step_id=1,
                agent_id=self._get_agent_id(Capability.DEVICE_CONTROL),
                query=f"执行设备控制: {query}",
                depends_on=[0] if steps else [],
            ))

        if not steps:
            steps.append(ExecutionStep(
                step_id=0,
                agent_id="default",
                query=query,
            ))

        return steps

    def _plan_parallel_steps(
        self,
        query: str,
        analysis: AnalysisResult,
    ) -> List[ExecutionStep]:
        steps = []

        if analysis.factors.detected_entities.get("device_type"):
            steps.append(ExecutionStep(
                step_id=0,
                agent_id=self._get_agent_id(Capability.DEVICE_QUERY),
                query=f"查询设备: {query}",
            ))

        if "看看" in query or "查看" in query or "监控" in query:
            steps.append(ExecutionStep(
                step_id=len(steps),
                agent_id=self._get_agent_id(Capability.VISION_ANALYSIS),
                query=f"视觉分析: {query}",
            ))

        if not steps:
            steps.append(ExecutionStep(
                step_id=0,
                agent_id="default",
                query=query,
            ))

        return steps

    def _get_agent_id(self, capability: Capability) -> str:
        agent = self._capability_registry.get_optimal_agent(capability)
        return agent.agent_id if agent else "default"

    async def _execute_rule_direct(
        self,
        query: str,
        plan: ExecutionPlan,
    ) -> ExecutionResult:
        self._stats["rule_direct_count"] += 1

        rule_result = await self._rule_engine.match(query)
        if not rule_result:
            return ExecutionResult(
                success=False,
                response="规则匹配失败",
                mode=ExecutionMode.RULE_DIRECT,
                steps_executed=0,
                total_time_ms=0,
                llm_calls=0,
            )

        response = rule_result.response_template or "好的，已为您处理"

        if rule_result.tool_name and rule_result.tool_params:
            try:
                tool_executor = self._agent_executors.get("tool_executor")
                if tool_executor:
                    tool_response = await tool_executor(
                        rule_result.tool_name,
                        "",
                        rule_result.tool_params,
                    )
                    if tool_response:
                        response = tool_response
            except Exception as e:
                logger.warning(f"Tool execution failed in rule_direct mode: {e}")

        return ExecutionResult(
            success=True,
            response=response,
            mode=ExecutionMode.RULE_DIRECT,
            steps_executed=1,
            total_time_ms=0,
            llm_calls=0,
            rule_matched=True,
            agent_results={"rule_engine": rule_result.to_dict() if hasattr(rule_result, 'to_dict') else str(rule_result)},
        )

    async def _execute_single_agent(
        self,
        query: str,
        session_id: str,
        plan: ExecutionPlan,
    ) -> ExecutionResult:
        self._stats["single_agent_count"] += 1

        step = plan.steps[0]
        executor = self._agent_executors.get(step.agent_id)

        if not executor:
            executor = self._agent_executors.get("default")
            if not executor:
                return ExecutionResult(
                    success=False,
                    response=f"未找到Agent: {step.agent_id}",
                    mode=ExecutionMode.SINGLE_AGENT,
                    steps_executed=0,
                    total_time_ms=0,
                    llm_calls=0,
                )

        try:
            context = await self._blackboard.read(f"session_{session_id}") or {}
            response = await asyncio.wait_for(
                executor(query, session_id, context),
                timeout=plan.total_timeout_seconds,
            )

            return ExecutionResult(
                success=True,
                response=response,
                mode=ExecutionMode.SINGLE_AGENT,
                steps_executed=1,
                total_time_ms=0,
                llm_calls=1,
                agent_results={step.agent_id: response[:200]},
            )

        except asyncio.TimeoutError:
            return ExecutionResult(
                success=False,
                response="请求超时，请稍后重试",
                mode=ExecutionMode.SINGLE_AGENT,
                steps_executed=1,
                total_time_ms=0,
                llm_calls=1,
                metadata={"timeout": True},
            )

        except Exception as e:
            logger.error(f"Single agent execution error: {e}", exc_info=True)
            return ExecutionResult(
                success=False,
                response=f"执行失败: {str(e)}",
                mode=ExecutionMode.SINGLE_AGENT,
                steps_executed=1,
                total_time_ms=0,
                llm_calls=1,
                metadata={"error": str(e)},
            )

    async def _execute_parallel(
        self,
        query: str,
        session_id: str,
        plan: ExecutionPlan,
    ) -> ExecutionResult:
        self._stats["parallel_count"] += 1

        tasks = []
        step_map = {}

        for step in plan.steps:
            executor = self._agent_executors.get(step.agent_id)
            if not executor:
                executor = self._agent_executors.get("default")
            if executor:
                context = await self._blackboard.read(f"session_{session_id}") or {}
                task = asyncio.wait_for(
                    executor(step.query, session_id, context),
                    timeout=step.timeout_seconds,
                )
                tasks.append(task)
                step_map[len(tasks) - 1] = step

        if not tasks:
            return ExecutionResult(
                success=False,
                response="未找到可用的Agent",
                mode=ExecutionMode.PARALLEL,
                steps_executed=0,
                total_time_ms=0,
                llm_calls=0,
            )

        results = await asyncio.gather(*tasks, return_exceptions=True)

        successful_results = []
        agent_results = {}

        for i, result in enumerate(results):
            step = step_map[i]
            if isinstance(result, Exception):
                logger.warning(f"Parallel step {step.step_id} failed: {result}")
                agent_results[step.agent_id] = f"失败: {str(result)}"
            else:
                successful_results.append(result)
                agent_results[step.agent_id] = result[:200] if isinstance(result, str) else str(result)[:200]

        if self._synthesizer and successful_results:
            response = await self._synthesizer(query, successful_results)
        elif successful_results:
            response = successful_results[0]
        else:
            response = "抱歉，处理失败了"

        return ExecutionResult(
            success=len(successful_results) > 0,
            response=response,
            mode=ExecutionMode.PARALLEL,
            steps_executed=len(results),
            total_time_ms=0,
            llm_calls=len(tasks),
            agent_results=agent_results,
        )

    async def _execute_pipeline(
        self,
        query: str,
        session_id: str,
        plan: ExecutionPlan,
    ) -> ExecutionResult:
        self._stats["pipeline_count"] += 1

        completed_steps: Dict[int, str] = {}
        agent_results = {}

        for step in plan.steps:
            for dep_id in step.depends_on:
                if dep_id not in completed_steps:
                    return ExecutionResult(
                        success=False,
                        response=f"依赖步骤 {dep_id} 未完成",
                        mode=ExecutionMode.PIPELINE,
                        steps_executed=len(completed_steps),
                        total_time_ms=0,
                        llm_calls=len(completed_steps),
                    )

            executor = self._agent_executors.get(step.agent_id)
            if not executor:
                executor = self._agent_executors.get("default")
            if not executor:
                return ExecutionResult(
                    success=False,
                    response=f"未找到Agent: {step.agent_id}",
                    mode=ExecutionMode.PIPELINE,
                    steps_executed=len(completed_steps),
                    total_time_ms=0,
                    llm_calls=len(completed_steps),
                )

            try:
                context = await self._blackboard.read(f"session_{session_id}") or {}
                if completed_steps:
                    context["previous_results"] = completed_steps

                response = await asyncio.wait_for(
                    executor(step.query, session_id, context),
                    timeout=step.timeout_seconds,
                )

                completed_steps[step.step_id] = response
                agent_results[step.agent_id] = response[:200] if isinstance(response, str) else str(response)[:200]

                await self._blackboard.write(
                    key=f"pipeline_step_{session_id}_{step.step_id}",
                    value=response,
                    source=step.agent_id,
                    namespace=BlackboardNamespace.RESULT,
                )

            except asyncio.TimeoutError:
                return ExecutionResult(
                    success=False,
                    response=f"步骤 {step.step_id} 超时",
                    mode=ExecutionMode.PIPELINE,
                    steps_executed=len(completed_steps),
                    total_time_ms=0,
                    llm_calls=len(completed_steps),
                )

            except Exception as e:
                logger.error(f"Pipeline step {step.step_id} error: {e}", exc_info=True)
                return ExecutionResult(
                    success=False,
                    response=f"步骤 {step.step_id} 失败: {str(e)}",
                    mode=ExecutionMode.PIPELINE,
                    steps_executed=len(completed_steps),
                    total_time_ms=0,
                    llm_calls=len(completed_steps),
                )

        final_response = list(completed_steps.values())[-1] if completed_steps else "处理完成"

        return ExecutionResult(
            success=True,
            response=final_response,
            mode=ExecutionMode.PIPELINE,
            steps_executed=len(completed_steps),
            total_time_ms=0,
            llm_calls=len(completed_steps),
            agent_results=agent_results,
        )

    async def _execute_fallback(
        self,
        query: str,
        session_id: str,
        plan: ExecutionPlan,
    ) -> ExecutionResult:
        self._stats["fallback_count"] += 1

        default_executor = self._agent_executors.get("default")
        if default_executor:
            try:
                context = await self._blackboard.read(f"session_{session_id}") or {}
                response = await default_executor(query, session_id, context)
                return ExecutionResult(
                    success=True,
                    response=response,
                    mode=ExecutionMode.FALLBACK,
                    steps_executed=1,
                    total_time_ms=0,
                    llm_calls=1,
                )
            except Exception as e:
                logger.error(f"Fallback execution error: {e}", exc_info=True)

        return ExecutionResult(
            success=False,
            response="抱歉，暂时无法处理您的请求",
            mode=ExecutionMode.FALLBACK,
            steps_executed=0,
            total_time_ms=0,
            llm_calls=0,
        )

    def _update_stats(self, mode: ExecutionMode, result: ExecutionResult) -> None:
        self._stats["total_llm_calls"] += result.llm_calls

        count = self._stats["total_requests"]
        self._stats["avg_response_time_ms"] = (
            (self._stats["avg_response_time_ms"] * (count - 1) + result.total_time_ms) / count
            if count > 0
            else result.total_time_ms
        )

    def get_stats(self) -> Dict[str, Any]:
        stats = dict(self._stats)
        stats["mode_distribution"] = {
            "rule_direct": stats.pop("rule_direct_count"),
            "single_agent": stats.pop("single_agent_count"),
            "parallel": stats.pop("parallel_count"),
            "pipeline": stats.pop("pipeline_count"),
            "fallback": stats.pop("fallback_count"),
        }
        total = stats["total_requests"]
        if total > 0:
            stats["mode_distribution_pct"] = {
                k: f"{v/total*100:.1f}%" for k, v in stats["mode_distribution"].items()
            }
            stats["avg_llm_calls_per_request"] = stats["total_llm_calls"] / total
        return stats
