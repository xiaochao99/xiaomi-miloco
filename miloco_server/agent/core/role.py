# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Role Management Module

Defines agent roles with personality, capabilities, and behavior patterns.
Supports dynamic role switching and capability-based tool assignment.
"""

import json
import logging
from enum import Enum, auto
from typing import Dict, List, Optional, Any, Callable, Set
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


class RoleCapability(Enum):
    """Agent capability enumeration"""
    CHAT = auto()              # General conversation
    DEVICE_CONTROL = auto()    # Smart home device control
    SCENE_MANAGEMENT = auto()  # Automation scene management
    VISION_ANALYSIS = auto()   # Image/video analysis
    FACE_RECOGNITION = auto()  # Face detection and recognition
    RULE_CREATION = auto()     # Automation rule creation
    CONDITION_EVAL = auto()    # Trigger condition evaluation
    CONTEXT_AWARE = auto()     # Context-aware responses
    MULTI_TURN = auto()        # Multi-turn conversation handling
    PROACTIVE = auto()         # Proactive interaction capability


@dataclass
class RoleConfig:
    """Role configuration data class"""
    name: str
    description: str
    personality: str = "helpful and friendly"
    tone: str = "professional yet approachable"
    language_style: str = "concise and clear"
    capabilities: Set[RoleCapability] = field(default_factory=set)
    preferred_tools: List[str] = field(default_factory=list)
    forbidden_tools: List[str] = field(default_factory=list)
    max_steps: int = 10
    temperature: float = 0.0
    context_window: int = 10
    response_format: str = "markdown"
    custom_settings: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "name": self.name,
            "description": self.description,
            "personality": self.personality,
            "tone": self.tone,
            "language_style": self.language_style,
            "capabilities": [c.name for c in self.capabilities],
            "preferred_tools": self.preferred_tools,
            "forbidden_tools": self.forbidden_tools,
            "max_steps": self.max_steps,
            "temperature": self.temperature,
            "context_window": self.context_window,
            "response_format": self.response_format,
            "custom_settings": self.custom_settings,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RoleConfig":
        """Create from dictionary"""
        config = cls(
            name=data["name"],
            description=data["description"],
            personality=data.get("personality", "helpful and friendly"),
            tone=data.get("tone", "professional yet approachable"),
            language_style=data.get("language_style", "concise and clear"),
            capabilities={RoleCapability[c] for c in data.get("capabilities", [])},
            preferred_tools=data.get("preferred_tools", []),
            forbidden_tools=data.get("forbidden_tools", []),
            max_steps=data.get("max_steps", 10),
            temperature=data.get("temperature", 0.0),
            context_window=data.get("context_window", 10),
            response_format=data.get("response_format", "markdown"),
            custom_settings=data.get("custom_settings", {}),
        )
        return config


class Role:
    """
    Agent Role Class
    
    Encapsulates agent personality, capabilities, and behavior patterns.
    Supports dynamic capability assignment and context-aware responses.
    """
    
    # Predefined role templates
    TEMPLATES = {
        "smart_home_assistant": RoleConfig(
            name="智能家居助手",
            description="专业的智能家居管理助手，擅长设备控制、场景管理和自动化规则创建",
            personality="专业、高效、贴心",
            tone="友好但有专业度",
            language_style="简洁明了，避免冗长",
            capabilities={
                RoleCapability.CHAT,
                RoleCapability.DEVICE_CONTROL,
                RoleCapability.SCENE_MANAGEMENT,
                RoleCapability.VISION_ANALYSIS,
                RoleCapability.RULE_CREATION,
                RoleCapability.CONTEXT_AWARE,
                RoleCapability.MULTI_TURN,
            },
            # preferred_tools removed - AI will intelligently select tools based on conversation context
            max_steps=10,
        ),
        "security_guardian": RoleConfig(
            name="家庭安全卫士",
            description="专注于家庭安全监控，擅长异常检测、人脸识别和安全预警",
            personality="警觉、可靠、保护性强",
            tone="严肃但不失礼貌",
            language_style="准确、及时、重要信息优先",
            capabilities={
                RoleCapability.VISION_ANALYSIS,
                RoleCapability.FACE_RECOGNITION,
                RoleCapability.CONDITION_EVAL,
                RoleCapability.PROACTIVE,
            },
            # preferred_tools removed - AI will intelligently select tools based on conversation context
            max_steps=5,
        ),
        "lifestyle_companion": RoleConfig(
            name="生活伴侣",
            description="贴心的生活助手，擅长日常对话、生活建议和环境优化",
            personality="温暖、幽默、善解人意",
            tone="轻松、亲切",
            language_style="口语化、自然、有温度",
            capabilities={
                RoleCapability.CHAT,
                RoleCapability.CONTEXT_AWARE,
                RoleCapability.MULTI_TURN,
                RoleCapability.PROACTIVE,
            },
            # preferred_tools removed - AI will intelligently select tools based on conversation context
            max_steps=5,
        ),
        "automation_expert": RoleConfig(
            name="自动化专家",
            description="专业的智能家居自动化顾问，擅长复杂规则设计和场景优化",
            personality="严谨、逻辑性强、注重细节",
            tone="专业、有条理",
            language_style="结构化、逻辑清晰",
            capabilities={
                RoleCapability.RULE_CREATION,
                RoleCapability.SCENE_MANAGEMENT,
                RoleCapability.CONDITION_EVAL,
                RoleCapability.CONTEXT_AWARE,
            },
            # preferred_tools removed - AI will intelligently select tools based on conversation context
            max_steps=15,
        ),
    }
    
    def __init__(self, config: RoleConfig):
        """
        Initialize role with configuration
        
        Args:
            config: Role configuration
        """
        self.config = config
        self.created_at = datetime.now()
        self.last_used = datetime.now()
        self.interaction_count = 0
        self.success_rate = 1.0
        self._capability_handlers: Dict[RoleCapability, Callable] = {}
        
        logger.info(f"Role '{config.name}' initialized with capabilities: "
                   f"{[c.name for c in config.capabilities]}")
    
    @classmethod
    def from_template(cls, template_name: str, **overrides) -> "Role":
        """
        Create role from predefined template
        
        Args:
            template_name: Template name
            **overrides: Configuration overrides
            
        Returns:
            Role instance
        """
        if template_name not in cls.TEMPLATES:
            raise ValueError(f"Unknown template: {template_name}. "
                           f"Available: {list(cls.TEMPLATES.keys())}")
        
        config = cls.TEMPLATES[template_name]
        
        # Apply overrides
        if overrides:
            config_dict = config.to_dict()
            config_dict.update(overrides)
            config = RoleConfig.from_dict(config_dict)
        
        return cls(config)
    
    @classmethod
    def create_custom(cls, **config_kwargs) -> "Role":
        """
        Create custom role
        
        Args:
            **config_kwargs: Configuration parameters
            
        Returns:
            Role instance
        """
        config = RoleConfig(**config_kwargs)
        return cls(config)
    
    def has_capability(self, capability: RoleCapability) -> bool:
        """Check if role has specific capability"""
        return capability in self.config.capabilities
    
    def add_capability(self, capability: RoleCapability, 
                      handler: Optional[Callable] = None) -> None:
        """
        Add capability to role
        
        Args:
            capability: Capability to add
            handler: Optional handler function
        """
        self.config.capabilities.add(capability)
        if handler:
            self._capability_handlers[capability] = handler
        logger.debug(f"Added capability {capability.name} to role '{self.config.name}'")
    
    def remove_capability(self, capability: RoleCapability) -> None:
        """Remove capability from role"""
        self.config.capabilities.discard(capability)
        self._capability_handlers.pop(capability, None)
        logger.debug(f"Removed capability {capability.name} from role '{self.config.name}'")
    
    def can_use_tool(self, tool_name: str) -> bool:
        """
        Check if role can use specific tool
        
        Note: preferred_tools check removed - AI will intelligently select tools
        based on conversation context. Only forbidden_tools are enforced.
        
        Args:
            tool_name: Tool name (may include prefix like "local_default___")
            
        Returns:
            True if tool is allowed
        """
        # Only check forbidden tools
        if tool_name in self.config.forbidden_tools:
            return False
        
        # Allow all other tools - AI will intelligently select based on context
        return True
    
    def get_system_prompt_additions(self) -> str:
        """
        Get system prompt additions based on role
        
        Returns:
            Additional prompt text
        """
        additions = []
        
        # Personality
        if self.config.personality:
            additions.append(f"你的性格特点：{self.config.personality}")
        
        # Tone
        if self.config.tone:
            additions.append(f"你的语气风格：{self.config.tone}")
        
        # Language style
        if self.config.language_style:
            additions.append(f"你的语言风格：{self.config.language_style}")
        
        # Capabilities
        if self.config.capabilities:
            caps = [c.name for c in self.config.capabilities]
            additions.append(f"你的能力范围：{', '.join(caps)}")
        
        return "\n".join(additions)
    
    def record_interaction(self, success: bool) -> None:
        """
        Record interaction result for learning
        
        Args:
            success: Whether interaction was successful
        """
        self.interaction_count += 1
        self.last_used = datetime.now()
        
        # Update success rate with exponential moving average
        alpha = 0.1
        self.success_rate = (1 - alpha) * self.success_rate + alpha * (1.0 if success else 0.0)
    
    def execute_capability(self, capability: RoleCapability, *args, **kwargs) -> Any:
        """
        Execute capability handler
        
        Args:
            capability: Capability to execute
            *args: Positional arguments
            **kwargs: Keyword arguments
            
        Returns:
            Handler result
        """
        if capability not in self.config.capabilities:
            raise ValueError(f"Role '{self.config.name}' does not have capability {capability.name}")
        
        handler = self._capability_handlers.get(capability)
        if handler:
            return handler(*args, **kwargs)
        
        logger.warning(f"No handler registered for capability {capability.name}")
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "config": self.config.to_dict(),
            "created_at": self.created_at.isoformat(),
            "last_used": self.last_used.isoformat(),
            "interaction_count": self.interaction_count,
            "success_rate": self.success_rate,
        }
    
    def __repr__(self) -> str:
        return f"Role(name='{self.config.name}', capabilities={len(self.config.capabilities)})"


class RoleManager:
    """
    Role Manager
    
    Manages multiple roles and handles role switching.
    """
    
    def __init__(self):
        self._roles: Dict[str, Role] = {}
        self._active_role: Optional[Role] = None
        self._default_role_name = "smart_home_assistant"
    
    def register_role(self, role: Role) -> None:
        """
        Register a role
        
        Args:
            role: Role instance
        """
        self._roles[role.config.name] = role
        logger.info(f"Registered role: {role.config.name}")
    
    def unregister_role(self, role_name: str) -> None:
        """
        Unregister a role
        
        Args:
            role_name: Role name
        """
        if role_name in self._roles:
            del self._roles[role_name]
            logger.info(f"Unregistered role: {role_name}")
    
    def get_role(self, role_name: str) -> Optional[Role]:
        """
        Get role by name
        
        Args:
            role_name: Role name
            
        Returns:
            Role instance or None
        """
        return self._roles.get(role_name)
    
    def switch_role(self, role_name: str) -> Role:
        """
        Switch to a different role
        
        Args:
            role_name: Role name to switch to
            
        Returns:
            New active role
        """
        if role_name not in self._roles:
            raise ValueError(f"Role '{role_name}' not found")
        
        self._active_role = self._roles[role_name]
        logger.info(f"Switched to role: {role_name}")
        return self._active_role
    
    def get_active_role(self) -> Optional[Role]:
        """Get currently active role"""
        return self._active_role
    
    def auto_select_role(self, query: str, context: Optional[Dict] = None) -> Role:
        """
        Automatically select appropriate role based on query
        
        Args:
            query: User query
            context: Optional context
            
        Returns:
            Selected role
        """
        query_lower = query.lower()
        
        # Security-related queries
        security_keywords = ["安全", "监控", "报警", "入侵", "陌生人", "异常"]
        if any(kw in query_lower for kw in security_keywords):
            return self._roles.get("security_guardian") or self._active_role
        
        # Automation-related queries
        automation_keywords = ["规则", "自动化", "场景", "条件", "触发"]
        if any(kw in query_lower for kw in automation_keywords):
            return self._roles.get("automation_expert") or self._active_role
        
        # Casual conversation
        casual_keywords = ["聊天", "建议", "推荐", "心情", "怎么样"]
        if any(kw in query_lower for kw in casual_keywords):
            return self._roles.get("lifestyle_companion") or self._active_role
        
        # Default to smart home assistant
        return self._roles.get(self._default_role_name, self._active_role)
    
    def list_roles(self) -> List[str]:
        """List all registered role names"""
        return list(self._roles.keys())
    
    def initialize_default_roles(self) -> None:
        """Initialize all default roles from templates"""
        for template_name in Role.TEMPLATES:
            role = Role.from_template(template_name)
            self.register_role(role)
        
        # Set default active role
        if not self._active_role and self._default_role_name in self._roles:
            self._active_role = self._roles[self._default_role_name]
