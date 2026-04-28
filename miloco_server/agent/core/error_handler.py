# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Error Handler Module

Provides comprehensive error handling and recovery mechanisms.
Implements fallback strategies and graceful degradation.
"""

import logging
import traceback
from typing import Dict, List, Optional, Any, Callable, Type, Tuple
from dataclasses import dataclass, field
from enum import Enum, auto
from datetime import datetime
from collections import defaultdict
import asyncio

logger = logging.getLogger(__name__)


class ErrorSeverity(Enum):
    """Error severity levels"""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """Error categories"""
    LLM_ERROR = "llm_error"
    TOOL_ERROR = "tool_error"
    NETWORK_ERROR = "network_error"
    TIMEOUT_ERROR = "timeout_error"
    VALIDATION_ERROR = "validation_error"
    RESOURCE_ERROR = "resource_error"
    UNKNOWN_ERROR = "unknown_error"


@dataclass
class ErrorRecord:
    """Error record"""
    error: Exception
    category: ErrorCategory
    severity: ErrorSeverity
    timestamp: datetime = field(default_factory=datetime.now)
    context: Dict[str, Any] = field(default_factory=dict)
    stack_trace: str = ""
    recovered: bool = False
    recovery_action: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_type": type(self.error).__name__,
            "error_message": str(self.error),
            "category": self.category.value,
            "severity": self.severity.value,
            "timestamp": self.timestamp.isoformat(),
            "context": self.context,
            "stack_trace": self.stack_trace,
            "recovered": self.recovered,
            "recovery_action": self.recovery_action,
        }


class FallbackStrategy(Enum):
    """Fallback strategies"""
    RETRY = "retry"
    ALTERNATIVE_TOOL = "alternative_tool"
    SIMPLIFIED_PROMPT = "simplified_prompt"
    CACHED_RESPONSE = "cached_response"
    DEFAULT_RESPONSE = "default_response"
    HUMAN_HANDOFF = "human_handoff"
    GRACEFUL_DEGRADATION = "graceful_degradation"


@dataclass
class RecoveryAction:
    """Recovery action"""
    strategy: FallbackStrategy
    action: Callable
    max_attempts: int = 3
    delay_seconds: float = 1.0
    fallback_to: Optional["RecoveryAction"] = None


class ErrorHandler:
    """
    Error Handler
    
    Centralized error handling with recovery mechanisms.
    Implements fallback strategies for different error types.
    """
    
    # Error category mappings
    ERROR_CATEGORIES = {
        # LLM errors
        "ConnectionError": (ErrorCategory.NETWORK_ERROR, ErrorSeverity.ERROR),
        "TimeoutError": (ErrorCategory.TIMEOUT_ERROR, ErrorSeverity.ERROR),
        "RuntimeError": (ErrorCategory.LLM_ERROR, ErrorSeverity.ERROR),
        "ValueError": (ErrorCategory.VALIDATION_ERROR, ErrorSeverity.WARNING),
        
        # Tool errors
        "ToolExecutionError": (ErrorCategory.TOOL_ERROR, ErrorSeverity.ERROR),
        "ToolNotFoundError": (ErrorCategory.TOOL_ERROR, ErrorSeverity.ERROR),
        
        # Resource errors
        "ResourceNotFoundException": (ErrorCategory.RESOURCE_ERROR, ErrorSeverity.ERROR),
        "FileNotFoundError": (ErrorCategory.RESOURCE_ERROR, ErrorSeverity.ERROR),
    }
    
    def __init__(self, max_retries: int = 3, enable_logging: bool = True):
        """
        Initialize error handler
        
        Args:
            max_retries: Maximum retry attempts
            enable_logging: Whether to enable error logging
        """
        self.max_retries = max_retries
        self.enable_logging = enable_logging
        
        self._error_history: List[ErrorRecord] = []
        self._recovery_strategies: Dict[ErrorCategory, List[RecoveryAction]] = defaultdict(list)
        self._default_responses: Dict[ErrorCategory, str] = {}
        
        self._setup_default_strategies()
        
        logger.info(f"ErrorHandler initialized: max_retries={max_retries}")
    
    def _setup_default_strategies(self) -> None:
        """Setup default recovery strategies"""
        
        # Network error strategies
        self._recovery_strategies[ErrorCategory.NETWORK_ERROR] = [
            RecoveryAction(
                strategy=FallbackStrategy.RETRY,
                action=self._retry_with_backoff,
                max_attempts=3,
                delay_seconds=2.0,
            ),
            RecoveryAction(
                strategy=FallbackStrategy.CACHED_RESPONSE,
                action=self._use_cached_response,
            ),
        ]
        
        # Timeout error strategies
        self._recovery_strategies[ErrorCategory.TIMEOUT_ERROR] = [
            RecoveryAction(
                strategy=FallbackStrategy.RETRY,
                action=self._retry_with_backoff,
                max_attempts=2,
                delay_seconds=1.0,
            ),
            RecoveryAction(
                strategy=FallbackStrategy.SIMPLIFIED_PROMPT,
                action=self._use_simplified_prompt,
            ),
        ]
        
        # Tool error strategies
        self._recovery_strategies[ErrorCategory.TOOL_ERROR] = [
            RecoveryAction(
                strategy=FallbackStrategy.ALTERNATIVE_TOOL,
                action=self._use_alternative_tool,
            ),
            RecoveryAction(
                strategy=FallbackStrategy.GRACEFUL_DEGRADATION,
                action=self._graceful_degradation,
            ),
        ]
        
        # LLM error strategies
        self._recovery_strategies[ErrorCategory.LLM_ERROR] = [
            RecoveryAction(
                strategy=FallbackStrategy.RETRY,
                action=self._retry_with_backoff,
                max_attempts=2,
                delay_seconds=1.0,
            ),
            RecoveryAction(
                strategy=FallbackStrategy.DEFAULT_RESPONSE,
                action=self._use_default_response,
            ),
        ]
        
        # Set default responses
        self._default_responses = {
            ErrorCategory.LLM_ERROR: "抱歉，我暂时无法处理您的请求，请稍后再试。",
            ErrorCategory.TOOL_ERROR: "工具执行出现问题，我将尝试其他方式帮助您。",
            ErrorCategory.NETWORK_ERROR: "网络连接不稳定，请检查网络后重试。",
            ErrorCategory.TIMEOUT_ERROR: "处理超时，让我简化一下再试。",
            ErrorCategory.RESOURCE_ERROR: "所需资源暂时不可用。",
            ErrorCategory.UNKNOWN_ERROR: "发生了意外错误，请稍后再试。",
        }
    
    def classify_error(self, error: Exception) -> Tuple[ErrorCategory, ErrorSeverity]:
        """
        Classify error type and severity
        
        Args:
            error: Exception to classify
            
        Returns:
            Tuple of (category, severity)
        """
        error_type = type(error).__name__
        
        if error_type in self.ERROR_CATEGORIES:
            return self.ERROR_CATEGORIES[error_type]
        
        # Check error message for patterns
        error_msg = str(error).lower()
        
        if any(kw in error_msg for kw in ["timeout", "timed out"]):
            return ErrorCategory.TIMEOUT_ERROR, ErrorSeverity.ERROR
        elif any(kw in error_msg for kw in ["connection", "network", "connect"]):
            return ErrorCategory.NETWORK_ERROR, ErrorSeverity.ERROR
        elif any(kw in error_msg for kw in ["tool", "mcp", "execution"]):
            return ErrorCategory.TOOL_ERROR, ErrorSeverity.ERROR
        elif any(kw in error_msg for kw in ["not found", "missing", "resource"]):
            return ErrorCategory.RESOURCE_ERROR, ErrorSeverity.ERROR
        
        return ErrorCategory.UNKNOWN_ERROR, ErrorSeverity.ERROR
    
    async def handle_error(
        self,
        error: Exception,
        context: Optional[Dict[str, Any]] = None,
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
        category, severity = self.classify_error(error)
        
        # Create error record
        record = ErrorRecord(
            error=error,
            category=category,
            severity=severity,
            context=context or {},
            stack_trace=traceback.format_exc(),
        )
        
        self._error_history.append(record)
        
        if self.enable_logging:
            self._log_error(record)
        
        # Attempt recovery
        result = await self._attempt_recovery(record, recovery_context)
        
        if result.get("success"):
            record.recovered = True
            record.recovery_action = result.get("strategy")
        
        return result
    
    async def _attempt_recovery(
        self,
        record: ErrorRecord,
        recovery_context: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Attempt to recover from error
        
        Args:
            record: Error record
            recovery_context: Recovery context
            
        Returns:
            Recovery result
        """
        strategies = self._recovery_strategies.get(record.category, [])
        
        if not strategies:
            # Use default response
            return {
                "success": True,
                "strategy": FallbackStrategy.DEFAULT_RESPONSE.value,
                "response": self._default_responses.get(
                    record.category,
                    self._default_responses[ErrorCategory.UNKNOWN_ERROR]
                ),
            }
        
        for strategy in strategies:
            try:
                result = await strategy.action(record, recovery_context, strategy)
                if result.get("success"):
                    return result
            except Exception as e:
                logger.warning(f"Recovery strategy {strategy.strategy.value} failed: {e}")
                continue
        
        # All strategies failed
        return {
            "success": False,
            "error": "All recovery strategies failed",
            "response": self._default_responses.get(
                record.category,
                self._default_responses[ErrorCategory.UNKNOWN_ERROR]
            ),
        }
    
    def _log_error(self, record: ErrorRecord) -> None:
        """Log error record"""
        log_msg = (
            f"Error: {type(record.error).__name__}: {record.error}\n"
            f"Category: {record.category.value}, Severity: {record.severity.value}\n"
            f"Context: {record.context}"
        )
        
        if record.severity == ErrorSeverity.CRITICAL:
            logger.critical(log_msg, exc_info=True)
        elif record.severity == ErrorSeverity.ERROR:
            logger.error(log_msg, exc_info=True)
        elif record.severity == ErrorSeverity.WARNING:
            logger.warning(log_msg)
        elif record.severity == ErrorSeverity.INFO:
            logger.info(log_msg)
        else:
            logger.debug(log_msg)
    
    # Recovery action implementations
    
    async def _retry_with_backoff(
        self,
        record: ErrorRecord,
        context: Optional[Dict],
        strategy: RecoveryAction,
    ) -> Dict[str, Any]:
        """Retry with exponential backoff"""
        original_func = context.get("original_func") if context else None
        original_args = context.get("args", [])
        original_kwargs = context.get("kwargs", {})
        
        if not original_func:
            return {"success": False, "error": "No original function to retry"}
        
        for attempt in range(strategy.max_attempts):
            delay = strategy.delay_seconds * (2 ** attempt)
            logger.info(f"Retry attempt {attempt + 1}/{strategy.max_attempts} after {delay}s delay")
            
            await asyncio.sleep(delay)
            
            try:
                if asyncio.iscoroutinefunction(original_func):
                    result = await original_func(*original_args, **original_kwargs)
                else:
                    result = original_func(*original_args, **original_kwargs)
                
                return {
                    "success": True,
                    "strategy": FallbackStrategy.RETRY.value,
                    "result": result,
                    "attempts": attempt + 1,
                }
            except Exception as e:
                logger.warning(f"Retry attempt {attempt + 1} failed: {e}")
                continue
        
        return {"success": False, "error": f"All {strategy.max_attempts} retry attempts failed"}
    
    async def _use_alternative_tool(
        self,
        record: ErrorRecord,
        context: Optional[Dict],
        strategy: RecoveryAction,
    ) -> Dict[str, Any]:
        """Use alternative tool"""
        alternatives = context.get("alternative_tools", []) if context else []
        tool_executor = context.get("tool_executor") if context else None
        
        for alt_tool in alternatives:
            try:
                if tool_executor:
                    result = await tool_executor.execute_tool_by_params(
                        alt_tool["client_id"],
                        alt_tool["tool_name"],
                        alt_tool.get("parameters", {})
                    )
                    return {
                        "success": True,
                        "strategy": FallbackStrategy.ALTERNATIVE_TOOL.value,
                        "tool_used": alt_tool["tool_name"],
                        "result": result,
                    }
            except Exception as e:
                logger.warning(f"Alternative tool {alt_tool.get('tool_name')} failed: {e}")
                continue
        
        return {"success": False, "error": "No alternative tool succeeded"}
    
    async def _use_simplified_prompt(
        self,
        record: ErrorRecord,
        context: Optional[Dict],
        strategy: RecoveryAction,
    ) -> Dict[str, Any]:
        """Use simplified prompt"""
        llm_proxy = context.get("llm_proxy") if context else None
        original_messages = context.get("messages", []) if context else []
        
        if not llm_proxy or not original_messages:
            return {"success": False, "error": "Missing LLM proxy or messages"}
        
        # Simplify messages - keep only system and last user message
        simplified = [
            msg for msg in original_messages
            if msg.get("role") in ["system", "user"]
        ][-2:]  # Keep last 2 messages
        
        try:
            result = await llm_proxy.async_call_llm(simplified)
            return {
                "success": True,
                "strategy": FallbackStrategy.SIMPLIFIED_PROMPT.value,
                "result": result,
            }
        except Exception as e:
            return {"success": False, "error": f"Simplified prompt failed: {e}"}
    
    async def _use_cached_response(
        self,
        record: ErrorRecord,
        context: Optional[Dict],
        strategy: RecoveryAction,
    ) -> Dict[str, Any]:
        """Use cached response"""
        cache_key = context.get("cache_key") if context else None
        cache_manager = context.get("cache_manager") if context else None
        
        if cache_manager and cache_key:
            cached = cache_manager.get(cache_key)
            if cached:
                return {
                    "success": True,
                    "strategy": FallbackStrategy.CACHED_RESPONSE.value,
                    "result": cached,
                    "from_cache": True,
                }
        
        return {"success": False, "error": "No cached response available"}
    
    async def _use_default_response(
        self,
        record: ErrorRecord,
        context: Optional[Dict],
        strategy: RecoveryAction,
    ) -> Dict[str, Any]:
        """Use default response"""
        default_response = self._default_responses.get(
            record.category,
            self._default_responses[ErrorCategory.UNKNOWN_ERROR]
        )
        
        return {
            "success": True,
            "strategy": FallbackStrategy.DEFAULT_RESPONSE.value,
            "response": default_response,
        }
    
    async def _graceful_degradation(
        self,
        record: ErrorRecord,
        context: Optional[Dict],
        strategy: RecoveryAction,
    ) -> Dict[str, Any]:
        """Graceful degradation"""
        # Provide partial results or simplified functionality
        partial_result = context.get("partial_result") if context else None
        
        return {
            "success": True,
            "strategy": FallbackStrategy.GRACEFUL_DEGRADATION.value,
            "result": partial_result or {"partial": True, "message": "部分功能暂时不可用"},
            "degraded": True,
        }
    
    def add_recovery_strategy(
        self,
        category: ErrorCategory,
        strategy: RecoveryAction,
    ) -> None:
        """
        Add custom recovery strategy
        
        Args:
            category: Error category
            strategy: Recovery strategy
        """
        self._recovery_strategies[category].append(strategy)
        logger.info(f"Added recovery strategy for {category.value}: {strategy.strategy.value}")
    
    def set_default_response(self, category: ErrorCategory, response: str) -> None:
        """
        Set default response for error category
        
        Args:
            category: Error category
            response: Default response message
        """
        self._default_responses[category] = response
    
    def get_error_statistics(self) -> Dict[str, Any]:
        """
        Get error statistics
        
        Returns:
            Statistics dictionary
        """
        if not self._error_history:
            return {}
        
        total = len(self._error_history)
        recovered = sum(1 for r in self._error_history if r.recovered)
        
        by_category = {}
        for record in self._error_history:
            cat = record.category.value
            if cat not in by_category:
                by_category[cat] = {"count": 0, "recovered": 0}
            by_category[cat]["count"] += 1
            if record.recovered:
                by_category[cat]["recovered"] += 1
        
        return {
            "total_errors": total,
            "recovered": recovered,
            "recovery_rate": recovered / total if total > 0 else 0,
            "by_category": by_category,
            "recent_errors": [r.to_dict() for r in self._error_history[-10:]],
        }
    
    def clear_history(self) -> None:
        """Clear error history"""
        self._error_history.clear()
        logger.info("Cleared error history")


# Global error handler instance
error_handler = ErrorHandler()
