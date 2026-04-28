# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Persona Manager Module

Manages user-defined persona settings with highest priority.
Supports AI name, user name, speaking style, and other personalized settings.
Provides persistent storage and force delete capabilities.
"""

import json
import logging
import os
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class PersonaSettings:
    """
    User-defined persona settings
    
    These settings have the highest priority and override role settings.
    """
    # AI Identity
    ai_name: str = "小助手"  # AI's name for self-reference
    ai_title: str = ""  # AI's title/role (e.g., "智能家居管家")
    
    # User Identity
    user_name: str = ""  # How AI addresses the user
    user_title: str = ""  # User's title/preference (e.g., "主人", "先生", "女士")
    
    # Speaking Style
    speaking_style: str = "友好、专业、简洁"  # General speaking style
    tone: str = "warm"  # Tone: formal, casual, warm, professional, playful
    language_style: str = "concise"  # concise, detailed, poetic, humorous
    response_length: str = "medium"  # short, medium, long
    
    # Personality Traits
    personality: str = " helpful, friendly, and professional"
    humor_level: int = 3  # 1-5 scale
    empathy_level: int = 4  # 1-5 scale
    formality_level: int = 3  # 1-5 scale (1=very casual, 5=very formal)
    
    # Greeting & Farewell
    custom_greeting: str = ""  # Custom greeting message
    custom_farewell: str = ""  # Custom farewell message
    
    # Special Instructions
    special_instructions: str = ""  # Any special behavior instructions
    forbidden_topics: List[str] = field(default_factory=list)  # Topics to avoid
    preferred_topics: List[str] = field(default_factory=list)  # Topics to encourage
    
    # Metadata
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    version: int = 1
    is_active: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PersonaSettings':
        """Create from dictionary"""
        # Filter only valid fields
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered_data)
    
    def update(self, **kwargs) -> None:
        """Update settings"""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        self.updated_at = datetime.now().isoformat()
        self.version += 1


class PersonaManager:
    """
    Persona Manager
    
    Manages user-defined persona settings with persistent storage.
    Provides CRUD operations and force delete capability.
    """
    
    def __init__(self, storage_dir: Optional[str] = None):
        """
        Initialize persona manager
        
        Args:
            storage_dir: Directory for storing persona data
        """
        if storage_dir is None:
            # Default to project config directory
            storage_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                "config", "personas"
            )
        
        self._storage_dir = Path(storage_dir)
        self._storage_dir.mkdir(parents=True, exist_ok=True)
        
        # In-memory cache
        self._personas: Dict[str, PersonaSettings] = {}
        self._active_persona_id: Optional[str] = None
        
        # Load existing personas
        self._load_all_personas()
        
        logger.info(f"PersonaManager initialized with storage: {self._storage_dir}")
    
    def _get_persona_file(self, persona_id: str) -> Path:
        """Get storage file path for a persona"""
        return self._storage_dir / f"{persona_id}.json"
    
    def _load_all_personas(self) -> None:
        """Load all personas from storage"""
        try:
            for file_path in self._storage_dir.glob("*.json"):
                persona_id = file_path.stem
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    persona = PersonaSettings.from_dict(data)
                    self._personas[persona_id] = persona
                    
                    # Set first active persona as default
                    if persona.is_active and self._active_persona_id is None:
                        self._active_persona_id = persona_id
                        
                except Exception as e:
                    logger.warning(f"Failed to load persona {persona_id}: {e}")
            
            logger.info(f"Loaded {len(self._personas)} personas from storage")
            
        except Exception as e:
            logger.error(f"Failed to load personas: {e}")
    
    def _save_persona(self, persona_id: str, persona: PersonaSettings) -> bool:
        """Save persona to storage"""
        try:
            file_path = self._get_persona_file(persona_id)
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(persona.to_dict(), f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"Failed to save persona {persona_id}: {e}")
            return False
    
    def create_persona(
        self,
        persona_id: str,
        ai_name: str = "小助手",
        user_name: str = "",
        speaking_style: str = "友好、专业、简洁",
        **kwargs
    ) -> PersonaSettings:
        """
        Create a new persona
        
        Args:
            persona_id: Unique identifier for the persona
            ai_name: AI's name
            user_name: User's name (how AI addresses user)
            speaking_style: Speaking style description
            **kwargs: Additional settings
            
        Returns:
            Created persona settings
        """
        if persona_id in self._personas:
            logger.warning(f"Persona {persona_id} already exists, updating instead")
            return self.update_persona(persona_id, ai_name=ai_name, user_name=user_name, 
                                     speaking_style=speaking_style, **kwargs)
        
        persona = PersonaSettings(
            ai_name=ai_name,
            user_name=user_name,
            speaking_style=speaking_style,
            **kwargs
        )
        
        self._personas[persona_id] = persona
        
        # Save to storage
        if self._save_persona(persona_id, persona):
            logger.info(f"Created persona: {persona_id} (AI: {ai_name}, User: {user_name})")
        
        # Set as active if first persona
        if self._active_persona_id is None:
            self._active_persona_id = persona_id
        
        return persona
    
    def update_persona(self, persona_id: str, **kwargs) -> Optional[PersonaSettings]:
        """
        Update an existing persona
        
        Args:
            persona_id: Persona identifier
            **kwargs: Settings to update
            
        Returns:
            Updated persona or None if not found
        """
        if persona_id not in self._personas:
            logger.warning(f"Persona {persona_id} not found")
            return None
        
        persona = self._personas[persona_id]
        persona.update(**kwargs)
        
        # Save to storage
        if self._save_persona(persona_id, persona):
            logger.info(f"Updated persona: {persona_id}")
        
        return persona
    
    def get_persona(self, persona_id: Optional[str] = None) -> Optional[PersonaSettings]:
        """
        Get persona settings
        
        Args:
            persona_id: Persona identifier (None for active persona)
            
        Returns:
            Persona settings or None
        """
        if persona_id is None:
            persona_id = self._active_persona_id
        
        if persona_id is None:
            return None
            
        return self._personas.get(persona_id)
    
    def get_active_persona(self) -> Optional[PersonaSettings]:
        """Get currently active persona"""
        return self.get_persona(self._active_persona_id)
    
    def set_active_persona(self, persona_id: str) -> bool:
        """
        Set active persona
        
        Args:
            persona_id: Persona to activate
            
        Returns:
            True if successful
        """
        if persona_id not in self._personas:
            logger.warning(f"Cannot activate unknown persona: {persona_id}")
            return False
        
        # Deactivate current
        if self._active_persona_id:
            current = self._personas.get(self._active_persona_id)
            if current:
                current.is_active = False
                self._save_persona(self._active_persona_id, current)
        
        # Activate new
        self._active_persona_id = persona_id
        new_persona = self._personas[persona_id]
        new_persona.is_active = True
        self._save_persona(persona_id, new_persona)
        
        logger.info(f"Activated persona: {persona_id}")
        return True
    
    def delete_persona(self, persona_id: str, force: bool = False) -> bool:
        """
        Delete a persona
        
        Args:
            persona_id: Persona to delete
            force: Force delete even if active
            
        Returns:
            True if deleted
        """
        if persona_id not in self._personas:
            logger.warning(f"Cannot delete unknown persona: {persona_id}")
            return False
        
        # Check if active
        if persona_id == self._active_persona_id and not force:
            logger.warning(f"Cannot delete active persona {persona_id} without force=True")
            return False
        
        # Remove from memory
        del self._personas[persona_id]
        
        # Remove from storage
        try:
            file_path = self._get_persona_file(persona_id)
            if file_path.exists():
                file_path.unlink()
        except Exception as e:
            logger.error(f"Failed to delete persona file {persona_id}: {e}")
        
        # Update active persona if needed
        if persona_id == self._active_persona_id:
            self._active_persona_id = None
            # Activate another persona if available
            for pid, p in self._personas.items():
                self.set_active_persona(pid)
                break
        
        logger.info(f"Deleted persona: {persona_id} (force={force})")
        return True
    
    def force_delete_all(self) -> int:
        """
        Force delete all personas (use with caution)
        
        Returns:
            Number of deleted personas
        """
        count = len(self._personas)
        
        # Clear memory
        self._personas.clear()
        self._active_persona_id = None
        
        # Clear storage
        try:
            for file_path in self._storage_dir.glob("*.json"):
                file_path.unlink()
            logger.warning(f"Force deleted all {count} personas")
        except Exception as e:
            logger.error(f"Failed to delete persona files: {e}")
        
        return count
    
    def list_personas(self) -> List[Dict[str, Any]]:
        """
        List all personas
        
        Returns:
            List of persona summaries
        """
        return [
            {
                "id": pid,
                "ai_name": p.ai_name,
                "user_name": p.user_name,
                "is_active": pid == self._active_persona_id,
                "updated_at": p.updated_at,
            }
            for pid, p in self._personas.items()
        ]
    
    def get_persona_prompt_additions(self, persona_id: Optional[str] = None) -> str:
        """
        Get prompt additions from persona settings
        
        These additions have the highest priority and override other settings.
        
        Args:
            persona_id: Persona identifier (None for active)
            
        Returns:
            Prompt additions string
        """
        persona = self.get_persona(persona_id)
        if not persona:
            return ""
        
        additions = []
        
        # Identity
        if persona.ai_name:
            additions.append(f"你的名字是：{persona.ai_name}")
        if persona.ai_title:
            additions.append(f"你的身份是：{persona.ai_title}")
        if persona.user_name:
            additions.append(f"用户的名字是：{persona.user_name}")
            additions.append(f"你应该用「{persona.user_name}」来称呼用户")
        if persona.user_title:
            additions.append(f"你应该用「{persona.user_title}」来尊称用户")
        
        # Speaking style
        if persona.speaking_style:
            additions.append(f"说话风格：{persona.speaking_style}")
        if persona.tone:
            additions.append(f"语气：{persona.tone}")
        if persona.language_style:
            additions.append(f"语言风格：{persona.language_style}")
        if persona.response_length:
            additions.append(f"回复长度：{persona.response_length}")
        
        # Personality
        if persona.personality:
            additions.append(f"性格特点：{persona.personality}")
        additions.append(f"幽默程度：{persona.humor_level}/5")
        additions.append(f"共情程度：{persona.empathy_level}/5")
        additions.append(f"正式程度：{persona.formality_level}/5")
        
        # Greetings
        if persona.custom_greeting:
            additions.append(f"问候语：{persona.custom_greeting}")
        if persona.custom_farewell:
            additions.append(f"结束语：{persona.custom_farewell}")
        
        # Special instructions
        if persona.special_instructions:
            additions.append(f"特殊指令：{persona.special_instructions}")
        if persona.forbidden_topics:
            additions.append(f"禁止话题：{', '.join(persona.forbidden_topics)}")
        if persona.preferred_topics:
            additions.append(f"偏好话题：{', '.join(persona.preferred_topics)}")
        
        # Priority marker
        additions.append("\n【以上设定具有最高优先级，必须严格遵守】")
        
        return "\n".join(additions)
    
    def export_persona(self, persona_id: str, filepath: str) -> bool:
        """
        Export persona to file
        
        Args:
            persona_id: Persona to export
            filepath: Output file path
            
        Returns:
            True if successful
        """
        persona = self.get_persona(persona_id)
        if not persona:
            return False
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(persona.to_dict(), f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"Failed to export persona: {e}")
            return False
    
    def import_persona(self, filepath: str, persona_id: Optional[str] = None) -> Optional[str]:
        """
        Import persona from file
        
        Args:
            filepath: Input file path
            persona_id: New persona ID (None to use filename)
            
        Returns:
            Imported persona ID or None
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if persona_id is None:
                persona_id = Path(filepath).stem
            
            # Ensure unique ID
            base_id = persona_id
            counter = 1
            while persona_id in self._personas:
                persona_id = f"{base_id}_{counter}"
                counter += 1
            
            persona = PersonaSettings.from_dict(data)
            self._personas[persona_id] = persona
            self._save_persona(persona_id, persona)
            
            logger.info(f"Imported persona: {persona_id}")
            return persona_id
            
        except Exception as e:
            logger.error(f"Failed to import persona: {e}")
            return None


# Global persona manager instance
persona_manager = PersonaManager()
