# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
AHAA Agent Integration Module

Provides easy integration of AHAA Agent framework components with existing system.
Simplifies the transition from legacy ChatAgent to EnhancedChatAgent.
"""

import logging
from typing import Optional, Dict, Any, List
from pathlib import Path

from miloco_server.config.config_loader import load_yaml_config, get_project_root

# Import AHAA Agent core components
from miloco_server.agent.core import (
    Role, RoleManager, RoleCapability,
    PromptTemplate, PromptContext, template_engine,
    ToolSelector, ToolContext, ToolSelectionStrategy,
    context_manager, ContextState,
    adaptive_learner, LearningRecord,
    error_handler, ErrorCategory,
)

logger = logging.getLogger(__name__)


class AhaaAgentIntegration:
    """
    AHAA Agent Integration Facade
    
    Provides a unified interface for accessing all AHAA Agent framework features.
    Handles configuration loading and component initialization.
    """
    
    _instance: Optional["AhaaAgentIntegration"] = None
    
    def __new__(cls):
        """Singleton pattern"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._config: Dict[str, Any] = {}
        self._role_manager: Optional[RoleManager] = None
        self._tool_selector: Optional[ToolSelector] = None
        
        self._load_config()
        self._initialize_components()
        
        self._initialized = True
        logger.info("AhaaAgentIntegration initialized successfully")
    
    def _load_config(self) -> None:
        """Load AHAA Agent configuration"""
        config_path = get_project_root().parent / "config" / "ahaa_config.yaml"
        
        if config_path.exists():
            self._config = load_yaml_config(config_path)
            logger.info(f"Loaded AHAA Agent config from {config_path}")
        else:
            logger.warning(f"AHAA Agent config not found at {config_path}, using defaults")
            self._config = self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration"""
        return {
            "roles": {"default_role": "smart_home_assistant"},
            "tool_selector": {"default_strategy": "HYBRID"},
            "context_manager": {"max_contexts": 100, "context_ttl_seconds": 3600},
            "adaptive_learner": {"learning_rate": 0.1, "min_samples_for_suggestions": 10},
            "error_handler": {"max_retries": 3, "enable_detailed_logging": True},
        }
    
    def _initialize_components(self) -> None:
        """Initialize all framework components"""
        # Initialize Role Manager
        self._role_manager = RoleManager()
        self._role_manager.initialize_default_roles()
        
        # Load custom roles from config
        self._load_custom_roles()
        
        # Initialize Tool Selector
        strategy_name = self._config.get("tool_selector", {}).get("default_strategy", "HYBRID")
        strategy = ToolSelectionStrategy[strategy_name]
        self._tool_selector = ToolSelector(strategy=strategy)
        
        # Initialize Template Engine
        template_engine.initialize_default_templates()
        
        logger.info("All AHAA Agent components initialized")
    
    def _load_custom_roles(self) -> None:
        """Load custom roles from configuration"""
        roles_config = self._config.get("roles", {}).get("definitions", {})
        
        for role_key, role_data in roles_config.items():
            try:
                # Convert capabilities from strings to enums
                caps = set()
                for cap_name in role_data.get("capabilities", []):
                    try:
                        caps.add(RoleCapability[cap_name])
                    except KeyError:
                        logger.warning(f"Unknown capability: {cap_name}")
                
                # Create role config
                from miloco_server.agent.core.role import RoleConfig
                config = RoleConfig(
                    name=role_data.get("name", role_key),
                    description=role_data.get("description", ""),
                    personality=role_data.get("personality", ""),
                    tone=role_data.get("tone", ""),
                    language_style=role_data.get("language_style", ""),
                    capabilities=caps,
                    preferred_tools=role_data.get("preferred_tools", []),
                    max_steps=role_data.get("max_steps", 10),
                    temperature=role_data.get("temperature", 0.0),
                    context_window=role_data.get("context_window", 10),
                )
                
                role = Role(config)
                self._role_manager.register_role(role)
                logger.info(f"Loaded custom role: {config.name}")
                
            except Exception as e:
                logger.error(f"Failed to load role {role_key}: {e}")
    
    # ==================== Role Management ====================
    
    def get_role_manager(self) -> RoleManager:
        """Get role manager instance"""
        return self._role_manager
    
    def get_active_role(self) -> Optional[Role]:
        """Get currently active role"""
        return self._role_manager.get_active_role()
    
    def switch_role(self, role_name: str) -> Role:
        """Switch to a different role"""
        return self._role_manager.switch_role(role_name)
    
    def auto_select_role(self, query: str) -> Role:
        """Automatically select appropriate role"""
        return self._role_manager.auto_select_role(query)
    
    def list_roles(self) -> List[str]:
        """List all available roles"""
        return self._role_manager.list_roles()
    
    # ==================== Tool Selection ====================
    
    def get_tool_selector(self) -> ToolSelector:
        """Get tool selector instance"""
        return self._tool_selector
    
    def select_tools(self, query: str, context: Optional[Dict] = None, top_k: int = 3) -> List[Any]:
        """
        Select appropriate tools for query
        
        Args:
            query: User query
            context: Optional additional context
            top_k: Number of recommendations
            
        Returns:
            List of tool selections
        """
        tool_context = ToolContext(
            query=query,
            **(context or {})
        )
        return self._tool_selector.select_tools(tool_context, top_k=top_k)
    
    def register_tools(self, tools: List[Dict[str, Any]]) -> None:
        """Register tools with selector"""
        self._tool_selector.register_tools_from_openai_format(tools)
    
    # ==================== Context Management ====================
    
    def get_context_manager(self):
        """Get context manager instance"""
        return context_manager
    
    def create_context(self, session_id: str, **metadata) -> Any:
        """Create new conversation context"""
        return context_manager.create_context(session_id, **metadata)
    
    def get_context(self, session_id: str) -> Optional[Any]:
        """Get existing context"""
        return context_manager.get_context(session_id)
    
    # ==================== Prompt Generation ====================
    
    def generate_system_prompt(
        self,
        role: Optional[Role] = None,
        context: Optional[Dict] = None,
    ) -> str:
        """
        Generate system prompt with role and context
        
        Args:
            role: Optional role (uses active role if not specified)
            context: Optional context data
            
        Returns:
            Generated system prompt
        """
        if role is None:
            role = self.get_active_role()
        
        prompt_context = PromptContext(
            custom_variables={
                "current_time": __import__("datetime").datetime.now().isoformat(),
                "role_description": role.config.description if role else "",
                "capabilities": [c.name for c in role.config.capabilities] if role else [],
                "preferred_tools": role.config.preferred_tools if role else [],
                **(context or {})
            }
        )
        
        return template_engine.compose_prompt(prompt_context)
    
    # ==================== Adaptive Learning ====================
    
    def record_interaction(self, record: LearningRecord) -> None:
        """Record interaction for learning"""
        adaptive_learner.record_interaction(record)
    
    def get_learning_stats(self) -> Dict[str, Any]:
        """Get learning statistics"""
        return adaptive_learner.get_learning_summary()
    
    def get_optimization_suggestions(self) -> List[Any]:
        """Get optimization suggestions"""
        return adaptive_learner.generate_optimization_suggestions()
    
    # ==================== Error Handling ====================
    
    async def handle_error(
        self,
        error: Exception,
        context: Optional[Dict] = None,
        recovery_context: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Handle error with recovery
        
        Args:
            error: Exception to handle
            context: Error context
            recovery_context: Recovery-specific context
            
        Returns:
            Recovery result
        """
        return await error_handler.handle_error(error, context, recovery_context)
    
    def get_error_stats(self) -> Dict[str, Any]:
        """Get error statistics"""
        return error_handler.get_error_statistics()
    
    # ==================== Utilities ====================
    
    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive statistics"""
        return {
            "roles": {
                "total": len(self._role_manager.list_roles()),
                "active": self.get_active_role().config.name if self.get_active_role() else None,
            },
            "contexts": context_manager.get_context_stats(),
            "learning": adaptive_learner.get_learning_summary(),
            "errors": error_handler.get_error_statistics(),
        }
    
    def reset_learning(self) -> None:
        """Reset all learning data"""
        adaptive_learner.reset()
        logger.info("Learning data reset")
    
    def clear_contexts(self) -> None:
        """Clear all contexts"""
        context_manager.clear_all_contexts()
        logger.info("All contexts cleared")


# Global integration instance
ahaa_agent = AhaaAgentIntegration()


def get_ahaa_agent() -> AhaaAgentIntegration:
    """Get AHAA Agent integration instance"""
    return ahaa_agent


# Convenience functions for quick access
def switch_role(role_name: str) -> Role:
    """Switch to a role"""
    return ahaa_agent.switch_role(role_name)


def auto_select_role(query: str) -> Role:
    """Auto-select role for query"""
    return ahaa_agent.auto_select_role(query)


def select_tools(query: str, top_k: int = 3) -> List[Any]:
    """Select tools for query"""
    return ahaa_agent.select_tools(query, top_k=top_k)


def generate_prompt(role: Optional[Role] = None, **context) -> str:
    """Generate system prompt"""
    return ahaa_agent.generate_system_prompt(role, context)


def get_stats() -> Dict[str, Any]:
    """Get system statistics"""
    return ahaa_agent.get_stats()
