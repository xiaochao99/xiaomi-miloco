# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Rule trigger filter utility for managing trigger frequency and conditions.
Provides functionality to filter trigger rules based on frequency, period, and condition changes.
"""

import datetime
import logging
from collections import deque
from typing import Dict, OrderedDict

from croniter import croniter

from miloco_server.schema.trigger_schema import TriggerRule, TriggerFrequencyFilter

logger = logging.getLogger(name=__name__)


class RuleTriggerFilter:
    """Rule trigger filter class"""
    _CONTINUOUS_CHECK_INTERVAL: int = 1000 * 10    # Post-processing continuous non-trigger detection interval ms
    _TRIGGER_INTERVAL_MIN: int = 1000 * 10  # Post-processing trigger interval minimum value ms

    # Record rule condition changes for specified camera
    _condition_history: Dict[str, Dict[str, OrderedDict[int, bool]]]
    # Record trigger time queue for specified rule
    _trigger_history: Dict[str, deque]

    def __init__(self):
        self._condition_history = {}
        self._trigger_history = {}

    def _default_rule_state(self, rule_id: str, camera_tag: str = None, filter_frequency: int = 1):
        """Default rule state."""
        self._condition_history.setdefault(rule_id, {})

        if camera_tag:
            self._condition_history[rule_id].setdefault(camera_tag, OrderedDict())

        self._trigger_history.setdefault(rule_id, deque(maxlen=filter_frequency))

    def pre_filter(self, rule: TriggerRule) -> bool:
        """Pre Trigger filter."""
        ts_now = int(datetime.datetime.now().timestamp() * 1000)
        if not rule.enabled:
            return False

        if not rule.filter:
            return True

        frequency = rule.filter.frequency.frequency if rule.filter.frequency else 1
        self._default_rule_state(rule.id, filter_frequency=frequency)

        # Check trigger period
        cron_expression = rule.filter.period
        if cron_expression and croniter.is_valid(cron_expression):
            if not croniter.match(cron_expression, datetime.datetime.fromtimestamp(ts_now/1000)):
                logger.info(
                    "trigger_pre_filter rule-%s: period_cron: %s mismatch now_timestamp: %d, Not Exec",
                    rule.id, cron_expression, ts_now)
                return False

        # Check trigger frequency
        trigger_queue: deque = self._trigger_history[rule.id]
        filters = [rule.filter.frequency] if rule.filter.frequency else []
        if rule.filter.interval:
            filters.append(TriggerFrequencyFilter(frequency=1, period=rule.filter.interval))

        for freq_filter in filters:
            if (len(trigger_queue) >= freq_filter.frequency and
                    ts_now - trigger_queue[-freq_filter.frequency] < freq_filter.period * 1000):
                logger.info(
                    "trigger_pre_filter rule-%s: over frequency: %d/%ds, Not Exec",
                    rule.id, freq_filter.frequency, freq_filter.period)
                return False

        return True

    def post_filter(self, rule_id: str, camera_tag: str, result: bool) -> bool:
        """Post Trigger filter."""
        ts_now = int(datetime.datetime.now().timestamp() * 1000)
        self._default_rule_state(rule_id, camera_tag=camera_tag)

        # FIFO, remove oldest
        conditions: OrderedDict[int, bool] = self._condition_history[rule_id][camera_tag]
        while len(conditions) > 0 and list(conditions.keys())[0] < ts_now - self._CONTINUOUS_CHECK_INTERVAL:
            conditions.popitem(last=False)

        last_status = any(list(conditions.values()))
        conditions[ts_now] = result

        # Check if continuous status(total) same as current, exec only status changed
        if last_status == result:
            logger.info(
                "trigger_post_filter rule-%s_camera-%s: last_status-%s same to current_status-%s, Not Exec",
                rule_id, camera_tag, last_status, result)
            return False

        # Check if the last trigger time is too close
        if (len(self._trigger_history[rule_id]) > 0 and
                ts_now - self._trigger_history[rule_id][-1] <
                self._TRIGGER_INTERVAL_MIN):
            logger.info(
                "trigger_post_filter rule-%s_camera-%s: last_trigger_time-%d "
                "too close to current_trigger_time-%d, Not Exec",
                rule_id, camera_tag, self._trigger_history[rule_id][-1], ts_now)
            return False

        # Same rule different condition has been filtered by TRIGGER_INTERVAL_MIN
        if result:
            self._trigger_history[rule_id].append(ts_now)

        return result


trigger_filter = RuleTriggerFilter()
