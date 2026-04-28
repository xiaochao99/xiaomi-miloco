# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Agent Module

Provides chat agent implementations for handling user interactions.
Includes both legacy and enhanced (OpenClaw) agent implementations.
"""

# Legacy agents (backward compatibility)
from .chat_agent import ChatAgent
from .nlp_request_agent import NlpRequestAgent
from .dynamic_execute_agent import ActionDescriptionDynamicExecuteAgent
from .wakeup_chat_agent import WakeUpChatAgent

# OpenClaw framework components
from .core import (
    # Role Management
    Role, RoleConfig, RoleCapability, RoleManager,
    # Prompt System
    PromptTemplate, PromptContext, TemplateEngine, template_engine,
    # Tool Selection
    ToolSelector, ToolSelectionStrategy, ToolContext, ToolSelection,
    # Context Management
    ContextManager, ConversationContext, ContextState, context_manager,
    # Adaptive Learning
    AdaptiveLearner, LearningRecord, OptimizationStrategy, adaptive_learner,
    # Error Handling
    ErrorHandler, FallbackStrategy, RecoveryAction, error_handler,
)

# Enhanced agent with OpenClaw integration
from .enhanced_chat_agent import EnhancedChatAgent

# Integration facade
from .openclaw_integration import (
    OpenClawIntegration,
    openclaw,
    get_openclaw,
    switch_role,
    auto_select_role,
    select_tools,
    generate_prompt,
    get_stats,
)

__all__ = [
    # Legacy Agents
    "ChatAgent",
    "NlpRequestAgent",
    "ActionDescriptionDynamicExecuteAgent",
    "WakeUpChatAgent",
    
    # OpenClaw Core Components
    "Role",
    "RoleConfig",
    "RoleCapability",
    "RoleManager",
    "PromptTemplate",
    "PromptContext",
    "TemplateEngine",
    "template_engine",
    "ToolSelector",
    "ToolSelectionStrategy",
    "ToolContext",
    "ToolSelection",
    "ContextManager",
    "ConversationContext",
    "ContextState",
    "context_manager",
    "AdaptiveLearner",
    "LearningRecord",
    "OptimizationStrategy",
    "adaptive_learner",
    "ErrorHandler",
    "FallbackStrategy",
    "RecoveryAction",
    "error_handler",
    
    # Enhanced Agent
    "EnhancedChatAgent",
    
    # Integration
    "OpenClawIntegration",
    "openclaw",
    "get_openclaw",
    "switch_role",
    "auto_select_role",
    "select_tools",
    "generate_prompt",
    "get_stats",
]
