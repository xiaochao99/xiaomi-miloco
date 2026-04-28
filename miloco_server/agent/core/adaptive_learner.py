# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Adaptive Learner Module

Implements learning mechanisms to improve agent responses over time.
Tracks interaction patterns, user preferences, and tool effectiveness.
"""

import json
import logging
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict
from enum import Enum
import statistics

logger = logging.getLogger(__name__)


@dataclass
class LearningRecord:
    """Record of a learning interaction"""
    session_id: str
    query: str
    intent: str
    selected_tools: List[str]
    success: bool
    user_satisfaction: Optional[float] = None  # 0.0 - 1.0
    response_time: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)
    context_features: Dict[str, Any] = field(default_factory=dict)
    feedback: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "query": self.query,
            "intent": self.intent,
            "selected_tools": self.selected_tools,
            "success": self.success,
            "user_satisfaction": self.user_satisfaction,
            "response_time": self.response_time,
            "timestamp": self.timestamp.isoformat(),
            "context_features": self.context_features,
            "feedback": self.feedback,
        }


class OptimizationStrategy(Enum):
    """Optimization strategies"""
    TOOL_SELECTION = "tool_selection"
    PROMPT_ENGINEERING = "prompt_engineering"
    PARAMETER_TUNING = "parameter_tuning"
    RESPONSE_FORMAT = "response_format"


@dataclass
class OptimizationSuggestion:
    """Optimization suggestion"""
    strategy: OptimizationStrategy
    target: str
    current_value: Any
    suggested_value: Any
    confidence: float
    reasoning: str
    expected_improvement: float


class AdaptiveLearner:
    """
    Adaptive Learner
    
    Learns from interactions to improve agent performance.
    Tracks patterns and generates optimization suggestions.
    """
    
    def __init__(self, learning_rate: float = 0.1, min_samples: int = 10, min_samples_for_suggestions: int = None):
        """
        Initialize adaptive learner
        
        Args:
            learning_rate: Learning rate for updates
            min_samples: Minimum samples before making suggestions
            min_samples_for_suggestions: Alias for min_samples (for compatibility)
        """
        self.learning_rate = learning_rate
        self.min_samples = min_samples_for_suggestions if min_samples_for_suggestions is not None else min_samples
        
        # Storage
        self._records: List[LearningRecord] = []
        self._intent_patterns: Dict[str, Dict] = defaultdict(lambda: {
            "count": 0,
            "success_count": 0,
            "tools_used": defaultdict(int),
            "avg_response_time": 0.0,
            "satisfaction_scores": [],
        })
        self._tool_effectiveness: Dict[str, Dict] = defaultdict(lambda: {
            "count": 0,
            "success_count": 0,
            "avg_response_time": 0.0,
            "contexts": [],
        })
        self._user_preferences: Dict[str, Dict] = defaultdict(lambda: {
            "preferred_tools": set(),
            "avoided_tools": set(),
            "common_intents": [],
            "satisfaction_trend": [],
        })
        
        logger.info(f"AdaptiveLearner initialized: learning_rate={learning_rate}")
    
    def record_interaction(self, record: LearningRecord) -> None:
        """
        Record an interaction for learning
        
        Args:
            record: Learning record
        """
        self._records.append(record)
        
        # Update intent patterns
        self._update_intent_patterns(record)
        
        # Update tool effectiveness
        self._update_tool_effectiveness(record)
        
        # Update user preferences
        self._update_user_preferences(record)
        
        logger.debug(f"Recorded interaction: intent={record.intent}, success={record.success}")
    
    def _update_intent_patterns(self, record: LearningRecord) -> None:
        """Update intent pattern statistics"""
        pattern = self._intent_patterns[record.intent]
        pattern["count"] += 1
        if record.success:
            pattern["success_count"] += 1
        
        for tool in record.selected_tools:
            pattern["tools_used"][tool] += 1
        
        # Update average response time
        n = pattern["count"]
        pattern["avg_response_time"] = (
            (n - 1) * pattern["avg_response_time"] + record.response_time
        ) / n
        
        if record.user_satisfaction is not None:
            pattern["satisfaction_scores"].append(record.user_satisfaction)
    
    def _update_tool_effectiveness(self, record: LearningRecord) -> None:
        """Update tool effectiveness statistics"""
        for tool in record.selected_tools:
            stats = self._tool_effectiveness[tool]
            stats["count"] += 1
            if record.success:
                stats["success_count"] += 1
            
            n = stats["count"]
            stats["avg_response_time"] = (
                (n - 1) * stats["avg_response_time"] + record.response_time
            ) / n
            
            stats["contexts"].append({
                "intent": record.intent,
                "success": record.success,
                "timestamp": record.timestamp,
            })
    
    def _update_user_preferences(self, record: LearningRecord) -> None:
        """Update user preference model"""
        # Use session_id as user identifier (could be enhanced with actual user ID)
        user_id = record.session_id
        prefs = self._user_preferences[user_id]
        
        if record.success:
            prefs["preferred_tools"].update(record.selected_tools)
        else:
            prefs["avoided_tools"].update(record.selected_tools)
        
        prefs["common_intents"].append(record.intent)
        
        if record.user_satisfaction is not None:
            prefs["satisfaction_trend"].append({
                "score": record.user_satisfaction,
                "timestamp": record.timestamp,
            })
    
    def get_intent_statistics(self, intent: Optional[str] = None) -> Dict[str, Any]:
        """
        Get statistics for intents
        
        Args:
            intent: Specific intent (None for all)
            
        Returns:
            Statistics dictionary
        """
        if intent:
            if intent not in self._intent_patterns:
                return {}
            pattern = self._intent_patterns[intent]
            return {
                "intent": intent,
                "count": pattern["count"],
                "success_rate": pattern["success_count"] / pattern["count"] if pattern["count"] > 0 else 0,
                "most_common_tools": sorted(
                    pattern["tools_used"].items(),
                    key=lambda x: x[1],
                    reverse=True
                )[:5],
                "avg_response_time": pattern["avg_response_time"],
                "avg_satisfaction": statistics.mean(pattern["satisfaction_scores"]) if pattern["satisfaction_scores"] else None,
            }
        
        return {intent: self.get_intent_statistics(intent) for intent in self._intent_patterns.keys()}
    
    def get_tool_recommendations(
        self,
        intent: str,
        context: Optional[Dict] = None,
        top_k: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        Get tool recommendations for an intent
        
        Args:
            intent: Target intent
            context: Optional context
            top_k: Number of recommendations
            
        Returns:
            List of tool recommendations with scores
        """
        if intent not in self._intent_patterns:
            return []
        
        pattern = self._intent_patterns[intent]
        if pattern["count"] < self.min_samples:
            return []
        
        recommendations = []
        for tool, count in pattern["tools_used"].items():
            tool_stats = self._tool_effectiveness[tool]
            
            # Calculate recommendation score
            usage_score = count / pattern["count"]
            success_score = tool_stats["success_count"] / tool_stats["count"] if tool_stats["count"] > 0 else 0
            
            # Combine scores
            score = 0.5 * usage_score + 0.5 * success_score
            
            recommendations.append({
                "tool": tool,
                "score": score,
                "usage_frequency": usage_score,
                "success_rate": success_score,
                "avg_response_time": tool_stats["avg_response_time"],
            })
        
        recommendations.sort(key=lambda x: x["score"], reverse=True)
        return recommendations[:top_k]
    
    def generate_optimization_suggestions(self) -> List[OptimizationSuggestion]:
        """
        Generate optimization suggestions based on learning
        
        Returns:
            List of optimization suggestions
        """
        suggestions = []
        
        # Analyze tool selection patterns
        for intent, pattern in self._intent_patterns.items():
            if pattern["count"] < self.min_samples:
                continue
            
            success_rate = pattern["success_count"] / pattern["count"]
            
            # Suggest alternative tools if success rate is low
            if success_rate < 0.7:
                best_tools = sorted(
                    pattern["tools_used"].items(),
                    key=lambda x: x[1],
                    reverse=True
                )
                
                if len(best_tools) >= 2:
                    current_tool = best_tools[0][0]
                    alternative_tool = best_tools[1][0]
                    
                    suggestions.append(OptimizationSuggestion(
                        strategy=OptimizationStrategy.TOOL_SELECTION,
                        target=f"intent:{intent}",
                        current_value=current_tool,
                        suggested_value=alternative_tool,
                        confidence=0.6,
                        reasoning=f"Low success rate ({success_rate:.2f}) with current tool for intent '{intent}'",
                        expected_improvement=0.15,
                    ))
        
        # Analyze response times
        for tool, stats in self._tool_effectiveness.items():
            if stats["count"] < self.min_samples:
                continue
            
            if stats["avg_response_time"] > 2.0:  # 2 seconds threshold
                suggestions.append(OptimizationSuggestion(
                    strategy=OptimizationStrategy.PARAMETER_TUNING,
                    target=f"tool:{tool}",
                    current_value=stats["avg_response_time"],
                    suggested_value="< 2.0s",
                    confidence=0.7,
                    reasoning=f"Tool '{tool}' has high average response time",
                    expected_improvement=0.1,
                ))
        
        return suggestions
    
    def predict_user_satisfaction(
        self,
        intent: str,
        selected_tools: List[str],
        context: Optional[Dict] = None,
    ) -> float:
        """
        Predict user satisfaction for an interaction
        
        Args:
            intent: User intent
            selected_tools: Tools to be used
            context: Optional context
            
        Returns:
            Predicted satisfaction score (0.0 - 1.0)
        """
        if intent not in self._intent_patterns:
            return 0.5  # Neutral default
        
        pattern = self._intent_patterns[intent]
        
        # Base satisfaction on historical success rate
        base_satisfaction = pattern["success_count"] / pattern["count"] if pattern["count"] > 0 else 0.5
        
        # Adjust based on tool selection
        tool_bonus = 0.0
        for tool in selected_tools:
            if tool in pattern["tools_used"]:
                usage = pattern["tools_used"][tool] / pattern["count"]
                tool_bonus += 0.1 * usage
        
        predicted = min(base_satisfaction + tool_bonus, 1.0)
        return predicted
    
    def get_learning_summary(self) -> Dict[str, Any]:
        """
        Get summary of learning progress
        
        Returns:
            Summary dictionary
        """
        total_interactions = len(self._records)
        successful_interactions = sum(1 for r in self._records if r.success)
        
        return {
            "total_interactions": total_interactions,
            "overall_success_rate": successful_interactions / total_interactions if total_interactions > 0 else 0,
            "unique_intents": len(self._intent_patterns),
            "unique_tools_used": len(self._tool_effectiveness),
            "avg_response_time": statistics.mean([r.response_time for r in self._records]) if self._records else 0,
            "intents_learned": list(self._intent_patterns.keys()),
        }
    
    def export_data(self, filepath: str) -> None:
        """
        Export learning data to file
        
        Args:
            filepath: Output file path
        """
        data = {
            "records": [r.to_dict() for r in self._records],
            "intent_patterns": dict(self._intent_patterns),
            "tool_effectiveness": dict(self._tool_effectiveness),
            "summary": self.get_learning_summary(),
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Exported learning data to {filepath}")
    
    def import_data(self, filepath: str) -> None:
        """
        Import learning data from file
        
        Args:
            filepath: Input file path
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Restore records
            for record_data in data.get("records", []):
                record = LearningRecord(**record_data)
                self.record_interaction(record)
            
            logger.info(f"Imported learning data from {filepath}")
        except Exception as e:
            logger.error(f"Failed to import learning data: {e}")
    
    def reset(self) -> None:
        """Reset all learning data"""
        self._records.clear()
        self._intent_patterns.clear()
        self._tool_effectiveness.clear()
        self._user_preferences.clear()
        logger.info("Reset all learning data")


# Global adaptive learner instance
adaptive_learner = AdaptiveLearner()
