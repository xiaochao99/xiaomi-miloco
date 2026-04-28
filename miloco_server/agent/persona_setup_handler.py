# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Persona Setup Handler

Handles natural language persona setup through conversation.
Integrates with EnhancedChatAgent to allow users to set persona via chat.
"""

import logging
import re
from typing import Optional, Dict, Any

from miloco_server.agent.core import (
    persona_manager,
    PersonaSettings,
    PersonaNLPParser,
    PersonaInitializer,
)

logger = logging.getLogger(__name__)


class PersonaSetupHandler:
    """
    Persona Setup Handler
    
    Detects and processes persona setup commands from natural language.
    """
    
    # Setup trigger patterns
    SETUP_PATTERNS = [
        r"(?:设定|设置|配置)(?:你|AI|助手)?(?:的?名字|名称)",
        r"(?:你|AI|助手)?(?:叫|叫做|是|名为)",
        r"(?:叫我|称呼我)",
        r"(?:设定|设置|配置)(?:主角色|角色|人设)",
        r"(?:重新|更改|修改)(?:设定|设置|配置)",
        r"(?:初始化|创建)(?:主角色|角色|人设)",
    ]
    
    # Query patterns
    QUERY_PATTERNS = [
        r"(?:查看|显示|告诉我)(?:当前)?(?:主角色|角色|人设|设定)",
        r"(?:我|当前)(?:的?设定|的设置|主角色)",
    ]
    
    # Delete patterns
    DELETE_PATTERNS = [
        r"(?:删除|清除|重置)(?:主角色|角色|人设|设定)",
        r"(?:恢复|回到)(?:默认|初始|出厂)",
    ]
    
    @classmethod
    def is_setup_command(cls, text: str) -> bool:
        """Check if text is a persona setup command"""
        text = text.strip().lower()
        for pattern in cls.SETUP_PATTERNS:
            if re.search(pattern, text):
                return True
        return False
    
    @classmethod
    def is_query_command(cls, text: str) -> bool:
        """Check if text is a persona query command"""
        text = text.strip().lower()
        for pattern in cls.QUERY_PATTERNS:
            if re.search(pattern, text):
                return True
        return False
    
    @classmethod
    def is_delete_command(cls, text: str) -> bool:
        """Check if text is a persona delete command"""
        text = text.strip().lower()
        for pattern in cls.DELETE_PATTERNS:
            if re.search(pattern, text):
                return True
        return False
    
    @classmethod
    def handle_setup(cls, text: str) -> Dict[str, Any]:
        """
        Handle persona setup from natural language
        
        Args:
            text: Natural language setup command
            
        Returns:
            Result dictionary with status and message
        """
        try:
            # Parse natural language
            parsed = PersonaNLPParser.parse(text)
            settings = PersonaNLPParser.to_persona_settings(parsed)
            
            if not settings:
                return {
                    "success": False,
                    "message": "未能从您的描述中识别出设定信息。请尝试这样说：\n"
                              "• '你叫小智，叫我张先生'\n"
                              "• '设定你的名字为小助手，说话风格要幽默'\n"
                              "• '叫我主人，你叫小管家'",
                    "action": "none"
                }
            
            # Check if persona exists
            existing = persona_manager.get_active_persona()
            
            if existing:
                # Update existing
                persona_manager.update_persona("default", **settings)
                action = "update"
                message = cls._build_update_message(settings, existing)
            else:
                # Create new
                PersonaInitializer.setup_default_persona(
                    template_name="friendly_assistant",
                    **settings
                )
                action = "create"
                message = cls._build_create_message(settings)
            
            return {
                "success": True,
                "message": message,
                "action": action,
                "settings": settings,
                "confidence": parsed.confidence,
            }
            
        except Exception as e:
            logger.error(f"Failed to handle persona setup: {e}")
            return {
                "success": False,
                "message": f"设定失败：{str(e)}",
                "action": "error"
            }
    
    @classmethod
    def handle_query(cls) -> Dict[str, Any]:
        """Handle persona query"""
        persona = persona_manager.get_active_persona()
        
        if not persona:
            return {
                "success": True,
                "message": "您还没有设置主角色。您可以说：\n"
                          "• '你叫小智，叫我张先生'\n"
                          "• '设定你的名字为小助手'",
                "action": "query",
                "has_persona": False,
            }
        
        message = cls._build_current_settings_message(persona)
        
        return {
            "success": True,
            "message": message,
            "action": "query",
            "has_persona": True,
            "persona": {
                "ai_name": persona.ai_name,
                "user_name": persona.user_name,
                "speaking_style": persona.speaking_style,
            }
        }
    
    @classmethod
    def handle_delete(cls, force: bool = False) -> Dict[str, Any]:
        """Handle persona delete/reset"""
        try:
            if force:
                # Force delete all
                count = persona_manager.force_delete_all()
                return {
                    "success": True,
                    "message": f"已重置所有设定，删除了 {count} 个配置。",
                    "action": "reset"
                }
            else:
                # Try to delete current
                success = persona_manager.delete_persona("default", force=True)
                if success:
                    return {
                        "success": True,
                        "message": "已删除当前主角色设定。",
                        "action": "delete"
                    }
                else:
                    return {
                        "success": False,
                        "message": "删除失败，没有找到主角色设定。",
                        "action": "none"
                    }
        except Exception as e:
            return {
                "success": False,
                "message": f"删除失败：{str(e)}",
                "action": "error"
            }
    
    @classmethod
    def _build_create_message(cls, settings: Dict[str, Any]) -> str:
        """Build message for create action"""
        parts = ["✅ 主角色设定创建成功！"]
        
        if "ai_name" in settings:
            parts.append(f"\n🤖 AI名字：{settings['ai_name']}")
        if "user_name" in settings:
            parts.append(f"👤 您的名字：{settings['user_name']}")
        if "user_title" in settings:
            parts.append(f"🎩 尊称：{settings['user_title']}")
        if "speaking_style" in settings:
            parts.append(f"💬 说话风格：{settings['speaking_style']}")
        
        parts.append("\n💡 您可以随时修改这些设定，比如：")
        parts.append("• '改一下，叫我李总'")
        parts.append("• '说话风格要更幽默一点'")
        
        return "\n".join(parts)
    
    @classmethod
    def _build_update_message(cls, new_settings: Dict[str, Any], existing: PersonaSettings) -> str:
        """Build message for update action"""
        parts = ["✅ 主角色设定已更新！"]
        
        # Show what changed
        changes = []
        if "ai_name" in new_settings and new_settings["ai_name"] != existing.ai_name:
            changes.append(f"AI名字：{existing.ai_name} → {new_settings['ai_name']}")
        if "user_name" in new_settings and new_settings["user_name"] != existing.user_name:
            changes.append(f"您的名字：{existing.user_name or '未设置'} → {new_settings['user_name']}")
        if "speaking_style" in new_settings and new_settings["speaking_style"] != existing.speaking_style:
            changes.append(f"说话风格已更新")
        
        if changes:
            parts.append("\n📝 变更内容：")
            for change in changes:
                parts.append(f"  • {change}")
        else:
            parts.append("\n📝 设定已保存")
        
        return "\n".join(parts)
    
    @classmethod
    def _build_current_settings_message(cls, persona: PersonaSettings) -> str:
        """Build message showing current settings"""
        parts = ["📋 当前主角色设定："]
        parts.append("=" * 40)
        
        parts.append(f"\n🤖 AI名字：{persona.ai_name}")
        if persona.ai_title:
            parts.append(f"   身份：{persona.ai_title}")
        
        parts.append(f"\n👤 您的名字：{persona.user_name or '未设置'}")
        if persona.user_title:
            parts.append(f"   尊称：{persona.user_title}")
        
        parts.append(f"\n💬 说话风格：{persona.speaking_style}")
        if persona.tone:
            parts.append(f"   语气：{persona.tone}")
        
        if persona.personality:
            parts.append(f"\n🎭 性格：{persona.personality}")
        
        parts.append("\n" + "=" * 40)
        parts.append("\n💡 修改方法：")
        parts.append("• '改一下，叫我李总'")
        parts.append("• '你叫小智吧'")
        parts.append("• '说话风格要更幽默'")
        
        return "\n".join(parts)


# Convenience function
def process_persona_command(text: str) -> Optional[Dict[str, Any]]:
    """
    Process persona-related command from user input
    
    Args:
        text: User input text
        
    Returns:
        Result if it's a persona command, None otherwise
    """
    handler = PersonaSetupHandler()
    
    if handler.is_setup_command(text):
        return handler.handle_setup(text)
    elif handler.is_query_command(text):
        return handler.handle_query()
    elif handler.is_delete_command(text):
        return handler.handle_delete()
    
    return None
