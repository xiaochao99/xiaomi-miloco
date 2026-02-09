# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Business prompt matcher with bilingual support
"""
from dataclasses import dataclass
import re

@dataclass
class MatchResult:
    """Match result"""
    matched: bool
    key: str
    placeholders: dict
    language: str  # 'chinese' or 'english'


class PromptMatcher:
    """Business prompt matcher with bilingual support"""

    def __init__(self, prompt_templates: dict):
        """
        Initialize matcher
        
        Args:
            prompt_templates: Prompt template dictionary
                Format: {key: {'chinese': template, 'english': template}}
                    or {key: template} for backward compatibility
        """
        self.prompt_templates = prompt_templates
        self._compile_patterns()

    def _compile_patterns(self):
        """Compile regex patterns for bilingual templates"""
        self.compiled_patterns = {}
        for key, template_data in self.prompt_templates.items():
            # Check if template_data is bilingual or single template (backward compatibility)
            if isinstance(template_data, dict) and ('chinese' in template_data or 'english' in template_data):
                # Bilingual format
                self.compiled_patterns[key] = {}

                for lang in ['chinese', 'english']:
                    template = template_data.get(lang, '')
                    if not template or isinstance(template, dict):
                        continue

                    # Extract placeholders from template
                    placeholders = re.findall(r'\{(\w+)\}', template)

                    # Convert template to regex pattern
                    # Escape special characters but preserve placeholders
                    pattern = re.escape(template)
                    # Convert escaped placeholders to regex groups
                    for placeholder in placeholders:
                        escaped_placeholder = re.escape(f'{{{placeholder}}}')
                        pattern = pattern.replace(escaped_placeholder,
                                                  f'(?P<{placeholder}>.*?)')

                    # Compile regex pattern
                    self.compiled_patterns[key][lang] = {
                        'pattern': re.compile(pattern, re.DOTALL),
                        'placeholders': placeholders
                    }
            else:
                # Single template format (backward compatibility)
                template = template_data
                placeholders = re.findall(r'\{(\w+)\}', template)

                pattern = re.escape(template)
                for placeholder in placeholders:
                    escaped_placeholder = re.escape(f'{{{placeholder}}}')
                    pattern = pattern.replace(escaped_placeholder,
                                              f'(?P<{placeholder}>.*?)')

                self.compiled_patterns[key] = {
                    'default': {
                        'pattern': re.compile(pattern, re.DOTALL),
                        'placeholders': placeholders
                    }
                }

    def match(self, text: str) -> MatchResult:
        """
        Match if text satisfies a template format (supports bilingual)
        
        Args:
            text: Text to match
            
        Returns:
            Match result containing:
            - matched: bool, whether match succeeded
            - key: str, matched template key
            - placeholders: dict, placeholder contents
            - language: str, matched language ('chinese', 'english', or 'default')
        """
        # Clean whitespace from input text
        cleaned_text = text.strip()
        for key, lang_patterns in self.compiled_patterns.items():
            # Try matching with all language variants
            for lang, pattern_info in lang_patterns.items():
                pattern = pattern_info['pattern']
                placeholders = pattern_info['placeholders']
                match = pattern.search(cleaned_text)
                if match:
                    # Extract placeholder contents
                    placeholder_values = {}
                    for placeholder in placeholders:
                        placeholder_values[placeholder] = match.group(
                            placeholder).strip()

                    return MatchResult(
                        matched=True,
                        key=key,
                        placeholders=placeholder_values,
                        language=lang
                    )

        return MatchResult(
            matched=False,
            key=None,
            placeholders={},
            language=None
        )

    def get_all_placeholders(self) -> dict:
        """
        Get placeholder information for all templates
        
        Returns:
            Dictionary with template names as keys and language-placeholder mapping as values
            Format: {key: {lang: [placeholders]}} or {key: {'default': [placeholders]}}
        """
        result = {}
        for key, lang_patterns in self.compiled_patterns.items():
            result[key] = {}
            for lang, pattern_info in lang_patterns.items():
                result[key][lang] = pattern_info['placeholders']
        return result
        