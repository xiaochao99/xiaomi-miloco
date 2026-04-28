# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
OpenClaw Agent Core Framework

A comprehensive framework for intelligent agent role configuration, prompt management,
and context-aware tool invocation.

Key Components:
- Role: Defines agent personality, capabilities, and behavior patterns
- PromptTemplate: Manages dynamic prompt generation with context awareness
- ToolSelector: Intelligent tool selection based on context and intent
- ContextManager: Maintains conversation context and state
- AdaptiveLearner: Learns from interactions to improve responses
"""

from .role import Role, RoleConfig, RoleCapability, RoleManager
from .prompt_template import PromptTemplate, PromptContext, TemplateEngine, PromptSection, TemplateVariable, template_engine
from .tool_selector import ToolSelector, ToolSelectionStrategy, ToolContext, ToolMetadata, ToolSelection
from .context_manager import ContextManager, ConversationContext, ContextState, context_manager
from .adaptive_learner import AdaptiveLearner, LearningRecord, OptimizationStrategy, adaptive_learner
from .error_handler import ErrorHandler, ErrorCategory, ErrorSeverity, FallbackStrategy, RecoveryAction, error_handler
from .persona_manager import PersonaSettings, PersonaManager, persona_manager

__all__ = [
    # Role Management
    'Role',
    'RoleConfig', 
    'RoleCapability',
    'RoleManager',
    
    # Persona Management (Highest Priority)
    'PersonaSettings',
    'PersonaManager',
    'persona_manager',
    
    # Prompt System
    'PromptTemplate',
    'PromptContext',
    'TemplateEngine',
    'PromptSection',
    'TemplateVariable',
    'template_engine',
    
    # Tool Selection
    'ToolSelector',
    'ToolSelectionStrategy',
    'ToolContext',
    'ToolMetadata',
    'ToolSelection',
    
    # Context Management
    'ContextManager',
    'ConversationContext',
    'ContextState',
    'context_manager',
    
    # Adaptive Learning
    'AdaptiveLearner',
    'LearningRecord',
    'OptimizationStrategy',
    'adaptive_learner',
    
    # Error Handling
    'ErrorHandler',
    'ErrorCategory',
    'ErrorSeverity',
    'FallbackStrategy',
    'RecoveryAction',
    'error_handler',
]
