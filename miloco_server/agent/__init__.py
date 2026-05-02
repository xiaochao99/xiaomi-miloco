# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Agent Module

AHAA (Adaptive Hybrid Agent Architecture) based agent implementations.
"""

# AHAA Agent core components
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

# AHAA Agent implementation
from .enhanced_chat_agent import EnhancedChatAgent

# Integration facade
from .ahaa_agent_integration import (
    AhaaAgentIntegration,
    ahaa_agent,
    get_ahaa_agent,
    switch_role,
    auto_select_role,
    select_tools,
    generate_prompt,
    get_stats,
)

# NLP Request Agent (AHAA-based)
from .nlp_request_agent_enhanced import NlpRequestAgent

# WakeUp Chat Agent (AHAA-based)
from .wakeup_chat_agent import WakeUpChatAgent

# Dynamic Execute Agent
from .dynamic_execute_agent import ActionDescriptionDynamicExecuteAgent

__all__ = [
    # AHAA Agent Core Components
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
    
    # AHAA Agent Implementation
    "EnhancedChatAgent",
    
    # NLP Request Agent
    "NlpRequestAgent",
    
    # WakeUp Chat Agent
    "WakeUpChatAgent",
    
    # Dynamic Execute Agent
    "ActionDescriptionDynamicExecuteAgent",
    
    # Integration
    "AhaaAgentIntegration",
    "ahaa_agent",
    "get_ahaa_agent",
    "switch_role",
    "auto_select_role",
    "select_tools",
    "generate_prompt",
    "get_stats",
]
