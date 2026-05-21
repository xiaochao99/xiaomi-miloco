# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
AHAA Dispatcher Module

AHAA调度器 - 将自适应混合智能体架构集成到现有系统

集成策略:
1. 包装现有Dispatcher，添加AHAA处理层
2. 根据配置开关决定是否启用AHAA
3. 支持优雅降级到单Agent模式
"""

import asyncio
import logging
import time
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, Callable, Awaitable
from dataclasses import dataclass

from .adaptive_orchestrator import AdaptiveOrchestrator, ExecutionResult
from .rule_engine import RuleEngine
from .complexity_analyzer import ComplexityAnalyzer
from .shared_blackboard import SharedBlackboard, BlackboardNamespace
from .capability_registry import CapabilityRegistry, Capability

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent.parent.parent.parent / "config" / "ahaa_config.yaml"


@dataclass
class AHAAMetrics:
    """AHAA性能指标"""
    total_requests: int = 0
    ahaa_handled: int = 0
    fallback_handled: int = 0
    rule_direct_count: int = 0
    single_agent_count: int = 0
    parallel_count: int = 0
    pipeline_count: int = 0
    avg_response_time_ms: float = 0.0
    total_llm_calls_saved: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_requests": self.total_requests,
            "ahaa_handled": self.ahaa_handled,
            "fallback_handled": self.fallback_handled,
            "rule_direct_count": self.rule_direct_count,
            "single_agent_count": self.single_agent_count,
            "parallel_count": self.parallel_count,
            "pipeline_count": self.pipeline_count,
            "avg_response_time_ms": self.avg_response_time_ms,
            "total_llm_calls_saved": self.total_llm_calls_saved,
        }


class AHAADispatcher:
    """
    AHAA调度器 - 将自适应混合智能体架构集成到现有系统

    用法:
        dispatcher = AHAADispatcher()

        # 注册Agent执行函数
        dispatcher.register_agent_executor("device_agent", device_execute_func)
        dispatcher.register_agent_executor("vision_agent", vision_execute_func)

        # 注册默认执行函数（降级时使用）
        dispatcher.register_default_executor(default_execute_func)

        # 处理请求
        result = await dispatcher.dispatch(query, session_id, context)
    """

    def __init__(self, config_path: Optional[str] = None):
        self._config = self._load_config(config_path or CONFIG_PATH)
        self._enable_fallback = self._config.get("ahaa", {}).get("enable_fallback", True)

        self._blackboard = SharedBlackboard(
            max_entries=self._config.get("blackboard", {}).get("max_entries", 10000),
        )
        self._rule_engine = RuleEngine()
        self._complexity_analyzer = ComplexityAnalyzer()
        self._capability_registry = CapabilityRegistry()

        self._orchestrator = AdaptiveOrchestrator(
            blackboard=self._blackboard,
            rule_engine=self._rule_engine,
            complexity_analyzer=self._complexity_analyzer,
            capability_registry=self._capability_registry,
        )

        self._default_executor: Optional[Callable[[str, str, Dict[str, Any]], Awaitable[str]]] = None
        self._metrics = AHAAMetrics()

        self._register_default_agents()

        logger.info("AHAADispatcher initialized")

    def _load_config(self, config_path) -> Dict[str, Any]:
        try:
            path = Path(config_path)
            if path.exists():
                with open(path, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f) or {}
            else:
                logger.warning(f"AHAA config not found: {config_path}, using defaults")
                return {}
        except Exception as e:
            logger.error(f"Failed to load AHAA config: {e}")
            return {}

    def _register_default_agents(self) -> None:
        agent_configs = self._config.get("capability_registry", {}).get("default_agents", {})

        for agent_id, config in agent_configs.items():
            capabilities = set()
            for cap_name in config.get("capabilities", []):
                try:
                    capabilities.add(Capability[cap_name])
                except KeyError:
                    logger.warning(f"Unknown capability: {cap_name}")

            self._capability_registry.register(
                agent_id=agent_id,
                capabilities=capabilities,
                tools=config.get("tools", []),
                priority=config.get("priority", 0),
            )

        logger.info(f"Registered {len(agent_configs)} default agents")

    def register_agent_executor(
        self,
        agent_id: str,
        executor: Callable[[str, str, Dict[str, Any]], Awaitable[str]],
    ) -> None:
        self._orchestrator.register_agent(agent_id, executor)
        logger.info(f"Registered agent executor: {agent_id}")

    def register_default_executor(
        self,
        executor: Callable[[str, str, Dict[str, Any]], Awaitable[str]],
    ) -> None:
        self._default_executor = executor
        self._orchestrator.register_agent("default", executor)
        logger.info("Registered default executor")

    def register_synthesizer(
        self,
        synthesizer: Callable[[str, list], Awaitable[str]],
    ) -> None:
        self._orchestrator.register_synthesizer(synthesizer)
        logger.info("Registered synthesizer")

    def register_tool_executor(
        self,
        executor: Callable[[str, str, Dict[str, Any]], Awaitable[Any]],
    ) -> None:
        self._orchestrator.register_agent("tool_executor", executor)
        logger.info("Registered tool executor")

    async def dispatch(
        self,
        query: str,
        session_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> ExecutionResult:
        self._metrics.total_requests += 1

        try:
            await self._blackboard.write(
                key=f"session_{session_id}",
                value=context or {},
                source="dispatcher",
                namespace=BlackboardNamespace.SESSION,
            )

            result = await self._orchestrator.execute(query, session_id, context)

            self._update_metrics(result)

            logger.info(
                f"AHAA dispatch completed: mode={result.mode.name}, "
                f"success={result.success}, time={result.total_time_ms:.1f}ms, "
                f"llm_calls={result.llm_calls}"
            )

            return result

        except Exception as e:
            logger.error(f"AHAA dispatch error: {e}", exc_info=True)

            if self._enable_fallback:
                logger.info("Falling back to default executor")
                return await self._fallback_execute(query, session_id, context)

            return ExecutionResult(
                success=False,
                response="抱歉，处理您的请求时遇到了问题",
                mode=self._orchestrator.ExecutionMode.FALLBACK if hasattr(self._orchestrator, 'ExecutionMode') else None,
                steps_executed=0,
                total_time_ms=0,
                llm_calls=0,
                metadata={"error": str(e)},
            )

    async def _fallback_execute(
        self,
        query: str,
        session_id: str,
        context: Optional[Dict[str, Any]],
    ) -> ExecutionResult:
        self._metrics.fallback_handled += 1

        if self._default_executor:
            start_time = time.time()
            try:
                response = await self._default_executor(query, session_id, context or {})
                elapsed_ms = (time.time() - start_time) * 1000

                return ExecutionResult(
                    success=True,
                    response=response,
                    mode=None,
                    steps_executed=1,
                    total_time_ms=elapsed_ms,
                    llm_calls=1,
                    metadata={"fallback": True},
                )
            except Exception as e:
                logger.error(f"Fallback execution error: {e}", exc_info=True)
                return ExecutionResult(
                    success=False,
                    response=f"抱歉，处理失败: {str(e)}",
                    mode=None,
                    steps_executed=0,
                    total_time_ms=0,
                    llm_calls=0,
                    metadata={"fallback_error": str(e)},
                )

        return ExecutionResult(
            success=False,
            response="系统暂时无法处理您的请求",
            mode=None,
            steps_executed=0,
            total_time_ms=0,
            llm_calls=0,
            metadata={"no_executor": True},
        )

    def _update_metrics(self, result: ExecutionResult) -> None:
        self._metrics.ahaa_handled += 1

        if result.rule_matched:
            self._metrics.rule_direct_count += 1
            self._metrics.total_llm_calls_saved += 1
        elif result.mode and result.mode.name == "SINGLE_AGENT":
            self._metrics.single_agent_count += 1
        elif result.mode and result.mode.name == "PARALLEL":
            self._metrics.parallel_count += 1
        elif result.mode and result.mode.name == "PIPELINE":
            self._metrics.pipeline_count += 1

        total = self._metrics.total_requests
        self._metrics.avg_response_time_ms = (
            (self._metrics.avg_response_time_ms * (total - 1) + result.total_time_ms) / total
            if total > 0
            else result.total_time_ms
        )

    def get_metrics(self) -> Dict[str, Any]:
        return self._metrics.to_dict()

    def get_orchestrator_stats(self) -> Dict[str, Any]:
        return self._orchestrator.get_stats()

    def get_blackboard_stats(self) -> Dict[str, Any]:
        return self._blackboard.get_stats()

    def get_registry_stats(self) -> Dict[str, Any]:
        return self._capability_registry.get_registry_stats()

    def get_all_stats(self) -> Dict[str, Any]:
        return {
            "dispatcher": self.get_metrics(),
            "orchestrator": self.get_orchestrator_stats(),
            "blackboard": self.get_blackboard_stats(),
            "registry": self.get_registry_stats(),
        }

    @property
    def rule_engine(self) -> RuleEngine:
        return self._rule_engine

    @property
    def complexity_analyzer(self) -> ComplexityAnalyzer:
        return self._complexity_analyzer

    @property
    def capability_registry(self) -> CapabilityRegistry:
        return self._capability_registry

    @property
    def blackboard(self) -> SharedBlackboard:
        return self._blackboard
