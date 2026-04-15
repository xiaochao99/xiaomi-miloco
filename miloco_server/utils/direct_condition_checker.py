# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Direct Condition Checker
Implements direct state matching for trigger conditions without using LLM.
Supports common condition patterns and provides zero-token-cost condition checking.
"""

import re
import logging
from typing import Dict, Any, Optional, List
from enum import Enum

logger = logging.getLogger(__name__)


class ConditionOperator(Enum):
    """Condition operator enumeration"""
    EQUAL = "=="
    NOT_EQUAL = "!="
    GREATER_THAN = ">"
    GREATER_THAN_OR_EQUAL = ">="
    LESS_THAN = "<"
    LESS_THAN_OR_EQUAL = "<="
    CONTAINS = "in"
    NOT_CONTAINS = "not in"
    MATCHES = "matches"
    NOT_MATCHES = "not matches"


class DirectConditionChecker:
    """
    Direct condition checker that evaluates conditions without LLM.
    Supports structured condition expressions and patterns.
    """

    # Pattern for common condition formats
    PATTERNS = {
        # "state == value" or "state=value"
        'simple_comparison': re.compile(r'^\s*(.+?)\s*(==|!=|>=|<=|>|<)\s*(.+?)\s*$', re.IGNORECASE),

        # "state in [a,b,c]" or "state not in [a,b,c]"
        'list_comparison': re.compile(r'^\s*(.+?)\s*(in|not in)\s*\[(.+?)\]\s*$', re.IGNORECASE),

        # "state matches pattern" or "state not matches pattern"
        'regex_comparison': re.compile(r'^\s*(.+?)\s*(matches|not matches)\s*(.+?)\s*$', re.IGNORECASE),
    }

    @staticmethod
    def parse_condition(condition: str) -> Dict[str, Any]:
        """
        Parse condition string into structured format.

        Args:
            condition: Condition string (e.g., "temperature > 25", "state == on")

        Returns:
            Parsed condition dict with keys:
            - type: 'comparison', 'list', 'regex', or 'unknown'
            - field: Field name to check
            - operator: Comparison operator
            - value: Expected value(s)
            - raw: Original condition string

        Examples:
            >>> parse_condition("temperature > 25")
            {'type': 'comparison', 'field': 'temperature', 'operator': '>', 'value': '25', 'raw': 'temperature > 25'}

            >>> parse_condition("state in [on,active]")
            {'type': 'list', 'field': 'state', 'operator': 'in', 'value': ['on', 'active'], 'raw': 'state in [on,active]'}
        """
        condition = condition.strip()

        # Try simple comparison pattern
        match = DirectConditionChecker.PATTERNS['simple_comparison'].match(condition)
        if match:
            field = match.group(1).strip()
            operator = match.group(2).strip()
            value = match.group(3).strip().strip('"\'')
            return {
                'type': 'comparison',
                'field': field,
                'operator': operator,
                'value': value,
                'raw': condition
            }

        # Try list comparison pattern
        match = DirectConditionChecker.PATTERNS['list_comparison'].match(condition)
        if match:
            field = match.group(1).strip()
            operator = match.group(2).strip().lower()
            value_str = match.group(3).strip()
            values = [v.strip().strip('"\'') for v in value_str.split(',')]
            return {
                'type': 'list',
                'field': field,
                'operator': operator,
                'value': values,
                'raw': condition
            }

        # Try regex comparison pattern
        match = DirectConditionChecker.PATTERNS['regex_comparison'].match(condition)
        if match:
            field = match.group(1).strip()
            operator = match.group(2).strip().lower()
            value = match.group(3).strip().strip('"\'')
            return {
                'type': 'regex',
                'field': field,
                'operator': operator,
                'value': value,
                'raw': condition
            }

        # Try natural language patterns (fallback)
        return DirectConditionChecker._parse_natural_language(condition)

    @staticmethod
    def _parse_natural_language(condition: str) -> Dict[str, Any]:
        """
        Parse natural language condition patterns.

        Supports:
        - "温度大于25度" -> temperature > 25
        - "灯是打开的" -> state == on
        - "灯打开了" -> state == on
        """
        result = {
            'type': 'natural',
            'field': 'state',
            'operator': '==',
            'value': None,
            'raw': condition
        }

        # Pattern: 灯打开了/灯是打开的 -> state == on
        if re.search(r'(打开|开启|on|active|true)', condition, re.IGNORECASE):
            if re.search(r'(关闭|关闭|off|inactive|false|not)', condition, re.IGNORECASE):
                # 灯没打开/灯不是打开的 -> state == off
                result['value'] = 'off'
            else:
                result['value'] = 'on'
            return result

        # Pattern: 灯关闭了 -> state == off
        if re.search(r'(关闭|关掉|off|inactive|false)', condition, re.IGNORECASE):
            result['value'] = 'off'
            return result

        # Pattern: 温度大于/小于/等于 X
        temp_match = re.search(r'(温度|湿度|数值).*?(大于|超过|>|小于|<|等于|==)\s*(\d+(?:\.\d+)?)', condition)
        if temp_match:
            field = 'temperature' if '温度' in temp_match.group(1) else 'humidity'
            operator_map = {'大于': '>', '超过': '>', '小于': '<', '等于': '=='}
            result['field'] = field
            result['operator'] = operator_map.get(temp_match.group(2), temp_match.group(2))
            result['value'] = temp_match.group(3)
            return result

        # Default: try to extract state from condition
        state_match = re.search(r'是\s*(.+?)$|状态为\s*(.+?)$|状态为(.+?)$', condition)
        if state_match:
            for group in state_match.groups():
                if group and group.strip():
                    result['value'] = group.strip()
                    return result

        return result

    @staticmethod
    def check_condition(
        parsed_condition: Dict[str, Any],
        device_states: Dict[str, Dict[str, Any]],
        trigger_entity_id: Optional[str] = None
    ) -> bool:
        """
        Check if the condition is satisfied based on device states.
        Checks ALL entities and returns True if ANY entity satisfies the condition.

        Args:
            parsed_condition: Parsed condition dict from parse_condition()
            device_states: Device states dict {entity_id: state_info}
            trigger_entity_id: The entity that triggered this check

        Returns:
            True if condition is satisfied by any entity, False otherwise
        """
        condition_type = parsed_condition.get('type', 'unknown')
        field = parsed_condition.get('field', 'state')
        operator = parsed_condition.get('operator', '==')
        expected_value = parsed_condition.get('value')

        if not device_states:
            logger.warning("No device states provided for condition: %s", parsed_condition['raw'])
            return False

        # If trigger_entity_id is specified and exists, only check that entity.
        if trigger_entity_id and trigger_entity_id in device_states:
            candidate_states = {trigger_entity_id: device_states[trigger_entity_id]}
            logger.info(
                "Checking condition '%s' on specified entity only: %s",
                parsed_condition['raw'], trigger_entity_id
            )
        else:
            candidate_states = device_states

        # Check candidate entities - return True if ANY entity satisfies the condition
        checked_count = 0
        logger.info("Checking condition '%s' against %d entities", parsed_condition['raw'], len(candidate_states))

        for entity_id, state_info in candidate_states.items():
            state_value = state_info.get('state')
            state_attributes = state_info.get('attributes', {})

            logger.info("  Entity %s: state=%s (type=%s)", entity_id, state_value, type(state_value).__name__)

            if state_value is None:
                continue

            checked_count += 1
            result = False

            # Check based on condition type
            try:
                if condition_type == 'comparison':
                    result = DirectConditionChecker._check_comparison(
                        state_value, operator, expected_value, state_attributes, field
                    )
                elif condition_type == 'list':
                    result = DirectConditionChecker._check_list(
                        state_value, operator, expected_value
                    )
                elif condition_type == 'regex':
                    result = DirectConditionChecker._check_regex(
                        state_value, operator, expected_value
                    )
                elif condition_type == 'natural':
                    result = DirectConditionChecker._check_comparison(
                        state_value, operator, expected_value, state_attributes, field
                    )
                else:
                    logger.warning("Unknown condition type: %s", condition_type)
                    continue
            except Exception as e:
                logger.error("Error checking condition %s for entity %s: %s",
                           parsed_condition['raw'], entity_id, e)
                continue

            logger.info("  Entity %s check result: %s", entity_id, result)

            # Return True immediately if any entity satisfies the condition
            if result:
                logger.info("Condition '%s' satisfied by entity %s (state: %s)",
                           parsed_condition['raw'], entity_id, state_value)
                return True

        logger.info("Condition '%s' not satisfied by any entity (checked %d)", parsed_condition['raw'], checked_count)

        if checked_count == 0:
            logger.warning("No valid state values found for condition: %s", parsed_condition['raw'])

        return False

    @staticmethod
    def _check_comparison(
        state_value: str,
        operator: str,
        expected_value: str,
        attributes: Dict[str, Any],
        field: str
    ) -> bool:
        """Check comparison condition."""
        def _numeric_compare(left: float, op: str, right: float) -> bool:
            if op == '==':
                return abs(left - right) < 0.001
            if op == '!=':
                return abs(left - right) >= 0.001
            if op == '>':
                return left > right
            if op == '>=':
                return left >= right
            if op == '<':
                return left < right
            if op == '<=':
                return left <= right
            return False

        # Try numeric comparison
        try:
            state_num = float(state_value)
            expected_num = float(expected_value)
            return _numeric_compare(state_num, operator, expected_num)
        except (ValueError, TypeError):
            pass  # Fall back to string comparison

        # String comparison
        if operator == '==':
            return str(state_value).lower() == str(expected_value).lower()
        if operator == '!=':
            return str(state_value).lower() != str(expected_value).lower()

        # Check attributes if field is not 'state'
        if field != 'state' and field in attributes:
            attr_value = attributes[field]
            try:
                attr_num = float(attr_value)
                expected_num = float(expected_value)
                return _numeric_compare(attr_num, operator, expected_num)
            except (ValueError, TypeError):
                if operator == '==':
                    return str(attr_value).lower() == str(expected_value).lower()
                if operator == '!=':
                    return str(attr_value).lower() != str(expected_value).lower()
                return False

        return False

    @staticmethod
    def _check_list(state_value: str, operator: str, expected_values: List[str]) -> bool:
        """Check list membership condition."""
        state_str = str(state_value).lower()
        expected_list = [str(v).lower() for v in expected_values]

        if operator == 'in':
            return state_str in expected_list
        elif operator == 'not in':
            return state_str not in expected_list

        return False

    @staticmethod
    def _check_regex(state_value: str, operator: str, pattern: str) -> bool:
        """Check regex match condition."""
        try:
            flags = re.IGNORECASE
            if operator == 'matches':
                return bool(re.search(pattern, str(state_value), flags))
            elif operator == 'not matches':
                return not bool(re.search(pattern, str(state_value), flags))
        except re.error as e:
            logger.error("Invalid regex pattern: %s, error: %s", pattern, e)

        return False

    @staticmethod
    def evaluate(
        condition: str,
        device_states: Dict[str, Dict[str, Any]],
        trigger_entity_id: Optional[str] = None
    ) -> bool:
        """
        Convenience method to parse and evaluate a condition in one call.

        Args:
            condition: Condition string
            device_states: Device states dict
            trigger_entity_id: The entity that triggered this check

        Returns:
            True if condition is satisfied, False otherwise
        """
        parsed = DirectConditionChecker.parse_condition(condition)
        return DirectConditionChecker.check_condition(parsed, device_states, trigger_entity_id)


# Global instance
direct_condition_checker = DirectConditionChecker()
