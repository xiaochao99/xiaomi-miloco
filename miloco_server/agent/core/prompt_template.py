# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Prompt Template Module

Provides dynamic prompt generation with context awareness.
Supports template inheritance, variable substitution, and conditional rendering.
"""

import re
import json
import logging
from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import dataclass, field
from enum import Enum, auto
from datetime import datetime

logger = logging.getLogger(__name__)


class PromptSection(Enum):
    """Prompt section types"""
    SYSTEM = "system"
    ROLE = "role"
    CONTEXT = "context"
    INSTRUCTIONS = "instructions"
    CONSTRAINTS = "constraints"
    EXAMPLES = "examples"
    TOOLS = "tools"
    OUTPUT_FORMAT = "output_format"


@dataclass
class PromptContext:
    """Context data for prompt rendering"""
    user_query: str = ""
    conversation_history: List[Dict[str, str]] = field(default_factory=list)
    available_tools: List[Dict[str, Any]] = field(default_factory=list)
    device_states: Dict[str, Any] = field(default_factory=dict)
    environment_info: Dict[str, Any] = field(default_factory=dict)
    user_preferences: Dict[str, Any] = field(default_factory=dict)
    session_metadata: Dict[str, Any] = field(default_factory=dict)
    custom_variables: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "user_query": self.user_query,
            "conversation_history": self.conversation_history,
            "available_tools": self.available_tools,
            "device_states": self.device_states,
            "environment_info": self.environment_info,
            "user_preferences": self.user_preferences,
            "session_metadata": self.session_metadata,
            "custom_variables": self.custom_variables,
        }


@dataclass
class TemplateVariable:
    """Template variable definition"""
    name: str
    description: str
    required: bool = True
    default_value: Any = None
    validator: Optional[Callable[[Any], bool]] = None
    
    def validate(self, value: Any) -> bool:
        """Validate variable value"""
        if self.validator:
            return self.validator(value)
        return True


class PromptTemplate:
    """
    Prompt Template Class
    
    Manages template content with variable substitution and conditional rendering.
    Supports inheritance from base templates.
    """
    
    # Template variable pattern: {{variable_name}} or {{variable_name|default}}
    VAR_PATTERN = re.compile(r'\{\{(\w+)(?:\|([^}]+))?\}\}')
    # Conditional pattern: {% if condition %}...{% endif %}
    COND_PATTERN = re.compile(r'\{%\s*if\s+(\w+)\s*\%}(.*?)\{%\s*endif\s*\%}', re.DOTALL)
    # For loop pattern: {% for item in list %}...{% endfor %}
    LOOP_PATTERN = re.compile(r'\{%\s*for\s+(\w+)\s+in\s+(\w+)\s*\%}(.*?)\{%\s*endfor\s*\%}', re.DOTALL)
    
    def __init__(
        self,
        name: str,
        content: str,
        description: str = "",
        variables: Optional[List[TemplateVariable]] = None,
        parent: Optional["PromptTemplate"] = None,
        section: PromptSection = PromptSection.SYSTEM,
        priority: int = 0,
    ):
        """
        Initialize prompt template
        
        Args:
            name: Template name
            content: Template content
            description: Template description
            variables: Template variables
            parent: Parent template for inheritance
            section: Prompt section type
            priority: Template priority (higher = more important)
        """
        self.name = name
        self.content = content
        self.description = description
        self.variables = {v.name: v for v in (variables or [])}
        self.parent = parent
        self.section = section
        self.priority = priority
        self.created_at = datetime.now()
        self.usage_count = 0
        self.success_rate = 1.0
        
        logger.debug(f"Created prompt template: {name}")
    
    def render(self, context: Union[PromptContext, Dict[str, Any]]) -> str:
        """
        Render template with context
        
        Args:
            context: Rendering context
            
        Returns:
            Rendered prompt string
        """
        if isinstance(context, PromptContext):
            context = context.to_dict()
        
        # Start with parent content if exists
        if self.parent:
            content = self.parent.render(context)
            content += "\n\n" + self.content
        else:
            content = self.content
        
        # Process loops first
        content = self._process_loops(content, context)
        
        # Process conditionals
        content = self._process_conditionals(content, context)
        
        # Process variables
        content = self._process_variables(content, context)
        
        self.usage_count += 1
        return content
    
    def _process_variables(self, content: str, context: Dict[str, Any]) -> str:
        """Process variable substitutions"""
        def replace_var(match):
            var_name = match.group(1)
            default_val = match.group(2)
            
            if var_name in context:
                value = context[var_name]
                if isinstance(value, (list, dict)):
                    return json.dumps(value, ensure_ascii=False, indent=2)
                return str(value)
            elif default_val is not None:
                return default_val
            elif var_name in self.variables:
                var = self.variables[var_name]
                if var.default_value is not None:
                    return str(var.default_value)
            
            logger.warning(f"Variable '{var_name}' not found in context")
            return match.group(0)
        
        return self.VAR_PATTERN.sub(replace_var, content)
    
    def _process_conditionals(self, content: str, context: Dict[str, Any]) -> str:
        """Process conditional blocks"""
        def replace_cond(match):
            condition = match.group(1)
            block_content = match.group(2)
            
            # Check condition
            if condition in context:
                value = context[condition]
                if isinstance(value, bool):
                    return block_content if value else ""
                elif isinstance(value, (list, dict, str)):
                    return block_content if value else ""
                elif isinstance(value, (int, float)):
                    return block_content if value > 0 else ""
            
            return ""
        
        return self.COND_PATTERN.sub(replace_cond, content)
    
    def _process_loops(self, content: str, context: Dict[str, Any]) -> str:
        """Process for loops"""
        def replace_loop(match):
            item_name = match.group(1)
            list_name = match.group(2)
            loop_content = match.group(3)
            
            if list_name not in context:
                logger.warning(f"List '{list_name}' not found in context")
                return ""
            
            items = context[list_name]
            if not isinstance(items, list):
                logger.warning(f"'{list_name}' is not a list")
                return ""
            
            results = []
            for item in items:
                item_context = {**context, item_name: item}
                rendered = self._process_variables(loop_content, item_context)
                results.append(rendered)
            
            return "\n".join(results)
        
        return self.LOOP_PATTERN.sub(replace_loop, content)
    
    def validate_context(self, context: Dict[str, Any]) -> List[str]:
        """
        Validate context against template variables
        
        Args:
            context: Context to validate
            
        Returns:
            List of validation errors
        """
        errors = []
        
        for var_name, var in self.variables.items():
            if var_name not in context:
                if var.required and var.default_value is None:
                    errors.append(f"Required variable '{var_name}' is missing")
            else:
                if not var.validate(context[var_name]):
                    errors.append(f"Variable '{var_name}' validation failed")
        
        return errors
    
    def record_result(self, success: bool) -> None:
        """Record usage result for optimization"""
        alpha = 0.1
        self.success_rate = (1 - alpha) * self.success_rate + alpha * (1.0 if success else 0.0)
    
    def clone(self, new_name: str, **overrides) -> "PromptTemplate":
        """
        Clone template with modifications
        
        Args:
            new_name: New template name
            **overrides: Properties to override
            
        Returns:
            New template instance
        """
        return PromptTemplate(
            name=new_name,
            content=overrides.get("content", self.content),
            description=overrides.get("description", self.description),
            variables=overrides.get("variables", list(self.variables.values())),
            parent=overrides.get("parent", self),
            section=overrides.get("section", self.section),
            priority=overrides.get("priority", self.priority),
        )


class TemplateEngine:
    """
    Template Engine
    
    Manages multiple templates and provides template composition.
    """
    
    def __init__(self):
        self._templates: Dict[str, PromptTemplate] = {}
        self._section_templates: Dict[PromptSection, List[PromptTemplate]] = {
            section: [] for section in PromptSection
        }
    
    def register_template(self, template: PromptTemplate) -> None:
        """
        Register a template
        
        Args:
            template: Template to register
        """
        self._templates[template.name] = template
        self._section_templates[template.section].append(template)
        
        # Sort by priority
        self._section_templates[template.section].sort(
            key=lambda t: t.priority, reverse=True
        )
        
        logger.info(f"Registered template: {template.name}")
    
    def unregister_template(self, name: str) -> None:
        """
        Unregister a template
        
        Args:
            name: Template name
        """
        if name in self._templates:
            template = self._templates[name]
            self._section_templates[template.section].remove(template)
            del self._templates[name]
            logger.info(f"Unregistered template: {name}")
    
    def get_template(self, name: str) -> Optional[PromptTemplate]:
        """
        Get template by name
        
        Args:
            name: Template name
            
        Returns:
            Template or None
        """
        return self._templates.get(name)
    
    def compose_prompt(
        self,
        context: PromptContext,
        sections: Optional[List[PromptSection]] = None,
        template_names: Optional[List[str]] = None,
    ) -> str:
        """
        Compose prompt from multiple templates
        
        Args:
            context: Prompt context
            sections: Sections to include (default: all)
            template_names: Specific templates to include
            
        Returns:
            Composed prompt
        """
        parts = []
        
        # Convert context to dict and flatten custom_variables
        if isinstance(context, PromptContext):
            context_dict = context.to_dict()
        else:
            context_dict = context
        
        # Flatten custom_variables to top level for template rendering
        custom_vars = context_dict.pop("custom_variables", {})
        flattened_context = {**context_dict, **custom_vars}
        
        if template_names:
            # Use specific templates
            for name in template_names:
                template = self._templates.get(name)
                if template:
                    parts.append(template.render(flattened_context))
        else:
            # Use sections
            sections = sections or list(PromptSection)
            for section in sections:
                for template in self._section_templates[section]:
                    parts.append(template.render(flattened_context))
        
        return "\n\n".join(parts)
    
    def create_dynamic_template(
        self,
        name: str,
        base_content: str,
        dynamic_sections: Dict[str, Callable[[PromptContext], str]],
    ) -> PromptTemplate:
        """
        Create a dynamic template with callable sections
        
        Args:
            name: Template name
            base_content: Base template content
            dynamic_sections: Dynamic section generators
            
        Returns:
            Dynamic template
        """
        def render_dynamic(context: PromptContext) -> str:
            content = base_content
            for section_name, generator in dynamic_sections.items():
                section_content = generator(context)
                placeholder = f"{{{{{section_name}}}}}"
                content = content.replace(placeholder, section_content)
            return content
        
        # Create wrapper template
        template = PromptTemplate(
            name=name,
            content=base_content,
            description=f"Dynamic template: {name}",
        )
        
        # Override render method
        original_render = template.render
        def new_render(context):
            base = original_render(context)
            # Apply dynamic sections
            for section_name, generator in dynamic_sections.items():
                if isinstance(context, PromptContext):
                    section_content = generator(context)
                else:
                    section_content = generator(PromptContext(**context))
                placeholder = f"{{{{{section_name}}}}}"
                base = base.replace(placeholder, section_content)
            return base
        
        template.render = new_render
        return template
    
    def list_templates(self, section: Optional[PromptSection] = None) -> List[str]:
        """
        List available templates
        
        Args:
            section: Filter by section
            
        Returns:
            List of template names
        """
        if section:
            return [t.name for t in self._section_templates[section]]
        return list(self._templates.keys())
    
    def initialize_default_templates(self) -> None:
        """Initialize default prompt templates"""
        
        # System template
        system_template = PromptTemplate(
            name="system_base",
            section=PromptSection.SYSTEM,
            priority=100,
            content="""# 角色与目标
你是一个高度智能的AI代理，专门负责通过分解任务和调用工具来精确满足用户的请求。

# 核心原则
- 任务分解 (Decomposition): 对于任何非单一操作的请求，你必须将其分解为逻辑清晰的子步骤
- 工具依赖 (Tool-Reliant): 你不能从先前的知识中编造任何实时状态信息
- 循序渐进 (Step-by-Step): 严格遵循"思考->行动->观察"的循环来解决问题
- 思考优先 (Think-First): 在决定调用任何工具之前，你必须先进行深度思考

当前时间: {{current_time}}
用户语言: {{user_language}}
""",
            variables=[
                TemplateVariable("current_time", "Current timestamp", default_value=""),
                TemplateVariable("user_language", "User's preferred language", default_value="zh"),
            ],
        )
        self.register_template(system_template)
        
        # Role template
        role_template = PromptTemplate(
            name="role_context",
            section=PromptSection.ROLE,
            priority=90,
            content="""# 角色设定
{{role_description}}

你的能力范围: {{capabilities}}
""",
            variables=[
                TemplateVariable("role_description", "Role description"),
                TemplateVariable("capabilities", "List of capabilities"),
            ],
        )
        self.register_template(role_template)
        
        # Context template
        context_template = PromptTemplate(
            name="conversation_context",
            section=PromptSection.CONTEXT,
            priority=80,
            content="""# 对话上下文
{% if conversation_history %}
最近的对话记录:
{% for msg in conversation_history %}
{{msg.role}}: {{msg.content}}
{% endfor %}
{% endif %}

{% if device_states %}
当前设备状态:
{{device_states}}
{% endif %}
""",
            variables=[
                TemplateVariable("conversation_history", "Previous messages", required=False),
                TemplateVariable("device_states", "Current device states", required=False),
            ],
        )
        self.register_template(context_template)
        
        # Tools template
        tools_template = PromptTemplate(
            name="available_tools",
            section=PromptSection.TOOLS,
            priority=70,
            content="""# 可用工具
{% if available_tools %}
你可以使用以下工具:
{% for tool in available_tools %}
- {{tool.name}}: {{tool.description}}
{% endfor %}
{% endif %}

{% if preferred_tools %}
推荐优先使用的工具: {{preferred_tools}}
{% endif %}
""",
            variables=[
                TemplateVariable("available_tools", "List of available tools", required=False),
                TemplateVariable("preferred_tools", "Preferred tools for this role", required=False),
            ],
        )
        self.register_template(tools_template)
        
        # Output format template
        output_template = PromptTemplate(
            name="output_format",
            section=PromptSection.OUTPUT_FORMAT,
            priority=60,
            content="""# 输出格式
- 思考过程必须包裹在 <reflect> 和 </reflect> 标签内
- 最终答案必须包裹在 <final_answer> 和 </final_answer> 标签内
- 工具调用必须遵循 OpenAI Tool Calling 格式
- 所有输出使用 Markdown 格式
""",
        )
        self.register_template(output_template)
        
        logger.info("Initialized default prompt templates")


# Global template engine instance
template_engine = TemplateEngine()
