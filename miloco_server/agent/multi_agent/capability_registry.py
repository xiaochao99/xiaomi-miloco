# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Capability Registry Module

能力注册表 - 解耦Agent与工具的绑定关系，支持动态能力发现和组合

核心设计:
1. Agent注册自己的能力，而非绑定工具
2. 编排器根据能力需求动态选择最优Agent
3. 支持能力评分和自适应选择
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Any, Callable
from enum import Enum, auto
from datetime import datetime

logger = logging.getLogger(__name__)


class Capability(Enum):
    """能力枚举 - 定义系统支持的所有能力"""
    DEVICE_CONTROL = auto()
    DEVICE_QUERY = auto()
    VISION_ANALYSIS = auto()
    FACE_RECOGNITION = auto()
    AUTOMATION = auto()
    RULE_CREATION = auto()
    CHAT = auto()
    MEMORY = auto()
    CONTEXT_AWARE = auto()
    MULTI_TURN = auto()
    PROACTIVE = auto()


@dataclass
class AgentCapability:
    """Agent能力描述"""
    agent_id: str
    capabilities: Set[Capability]
    tools: List[str]
    priority: int = 0
    max_concurrent: int = 1
    avg_response_time_ms: float = 0.0
    success_rate: float = 1.0
    total_calls: int = 0
    last_used: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "capabilities": [c.name for c in self.capabilities],
            "tools": self.tools,
            "priority": self.priority,
            "max_concurrent": self.max_concurrent,
            "avg_response_time_ms": self.avg_response_time_ms,
            "success_rate": self.success_rate,
            "total_calls": self.total_calls,
            "last_used": self.last_used.isoformat() if self.last_used else None,
            "metadata": self.metadata,
        }


@dataclass
class AgentPerformanceRecord:
    """Agent性能记录"""
    agent_id: str
    response_time_ms: float
    success: bool
    timestamp: datetime = field(default_factory=datetime.now)
    task_type: str = ""


class CapabilityRegistry:
    """
    能力注册表 - AHAA架构的Agent管理组件

    解耦Agent与工具的绑定关系，支持:
    1. 动态能力注册和发现
    2. 基于性能的选择优化
    3. 负载均衡和故障转移

    用法:
        registry = CapabilityRegistry()

        # 注册Agent能力
        registry.register(
            agent_id="device_agent",
            capabilities={Capability.DEVICE_CONTROL, Capability.DEVICE_QUERY},
            tools=["send_ctrl_rpc", "send_get_rpc"],
        )

        # 查找最优Agent
        agent = registry.get_optimal_agent(Capability.DEVICE_CONTROL)
    """

    def __init__(self):
        self._registry: Dict[str, AgentCapability] = {}
        self._performance_history: List[AgentPerformanceRecord] = []
        self._max_history_size = 1000
        logger.info("CapabilityRegistry initialized")

    def register(
        self,
        agent_id: str,
        capabilities: Set[Capability],
        tools: List[str],
        priority: int = 0,
        max_concurrent: int = 1,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._registry[agent_id] = AgentCapability(
            agent_id=agent_id,
            capabilities=capabilities,
            tools=tools,
            priority=priority,
            max_concurrent=max_concurrent,
            metadata=metadata or {},
        )
        logger.info(f"Registered agent: {agent_id} with capabilities: {[c.name for c in capabilities]}")

    def unregister(self, agent_id: str) -> bool:
        if agent_id in self._registry:
            del self._registry[agent_id]
            logger.info(f"Unregistered agent: {agent_id}")
            return True
        return False

    def get_agent(self, agent_id: str) -> Optional[AgentCapability]:
        return self._registry.get(agent_id)

    def find_agents_for_capability(self, capability: Capability) -> List[AgentCapability]:
        return [
            agent for agent in self._registry.values()
            if capability in agent.capabilities
        ]

    def find_agents_for_tool(self, tool_name: str) -> List[AgentCapability]:
        return [
            agent for agent in self._registry.values()
            if tool_name in agent.tools
        ]

    def find_agents_for_capabilities(self, capabilities: Set[Capability]) -> List[AgentCapability]:
        return [
            agent for agent in self._registry.values()
            if capabilities.issubset(agent.capabilities)
        ]

    def get_optimal_agent(self, capability: Capability) -> Optional[AgentCapability]:
        agents = self.find_agents_for_capability(capability)
        if not agents:
            return None

        def score(agent: AgentCapability) -> float:
            time_score = 1.0 / (1.0 + agent.avg_response_time_ms / 1000.0)
            return (
                0.4 * agent.success_rate
                + 0.3 * time_score
                + 0.2 * (1.0 / (1.0 + agent.priority))
                + 0.1 * (1.0 if agent.last_used is None else 0.5)
            )

        return max(agents, key=score)

    def get_optimal_agent_for_tools(self, tool_names: List[str]) -> Optional[AgentCapability]:
        candidates = []
        for agent in self._registry.values():
            matching_tools = set(tool_names) & set(agent.tools)
            if matching_tools:
                candidates.append((agent, len(matching_tools)))

        if not candidates:
            return None

        candidates.sort(key=lambda x: (-x[1], -x[0].success_rate))
        return candidates[0][0]

    def record_performance(
        self,
        agent_id: str,
        response_time_ms: float,
        success: bool,
        task_type: str = "",
    ) -> None:
        record = AgentPerformanceRecord(
            agent_id=agent_id,
            response_time_ms=response_time_ms,
            success=success,
            task_type=task_type,
        )
        self._performance_history.append(record)

        if len(self._performance_history) > self._max_history_size:
            self._performance_history = self._performance_history[-self._max_history_size:]

        agent = self._registry.get(agent_id)
        if agent:
            agent.total_calls += 1
            agent.last_used = datetime.now()

            alpha = 0.1
            agent.avg_response_time_ms = (
                (1 - alpha) * agent.avg_response_time_ms + alpha * response_time_ms
            )
            agent.success_rate = (
                (1 - alpha) * agent.success_rate + alpha * (1.0 if success else 0.0)
            )

    def get_all_agents(self) -> List[AgentCapability]:
        return list(self._registry.values())

    def get_registry_stats(self) -> Dict[str, Any]:
        total_agents = len(self._registry)
        total_capabilities = len(Capability)
        covered_capabilities = set()
        for agent in self._registry.values():
            covered_capabilities.update(agent.capabilities)

        return {
            "total_agents": total_agents,
            "total_capabilities": total_capabilities,
            "covered_capabilities": len(covered_capabilities),
            "coverage_rate": len(covered_capabilities) / total_capabilities if total_capabilities > 0 else 0,
            "total_performance_records": len(self._performance_history),
            "agents": {aid: a.to_dict() for aid, a in self._registry.items()},
        }

    def get_agent_performance_summary(self, agent_id: str) -> Dict[str, Any]:
        records = [r for r in self._performance_history if r.agent_id == agent_id]
        if not records:
            return {"agent_id": agent_id, "records": 0}

        success_count = sum(1 for r in records if r.success)
        avg_time = sum(r.response_time_ms for r in records) / len(records)

        return {
            "agent_id": agent_id,
            "records": len(records),
            "success_rate": success_count / len(records),
            "avg_response_time_ms": avg_time,
            "recent_records": [
                {
                    "response_time_ms": r.response_time_ms,
                    "success": r.success,
                    "task_type": r.task_type,
                    "timestamp": r.timestamp.isoformat(),
                }
                for r in records[-10:]
            ],
        }
