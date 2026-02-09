# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Trigger rule log data access object
Handles CRUD operations for trigger_rule_log table
"""

import logging
import json
import uuid
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from miloco_server.utils.database import get_db_connector
from miloco_server.schema.trigger_log_schema import (
    TriggerRuleLog,
    TriggerConditionResult,
    ExecuteResult,
)

logger = logging.getLogger(__name__)


class TriggerRuleLogDAO:
    """Trigger rule log data access object"""

    def __init__(self):
        self.db_connector = get_db_connector()


    def _dict_to_trigger_rule_log(self, data: Dict[str, Any]) -> TriggerRuleLog:
        """Convert database data to TriggerRuleLog object"""
        # Parse JSON fields
        camera_condition_results_data = (json.loads(data["camera_condition_results"])
                                        if data["camera_condition_results"] else [])
        camera_condition_results = [TriggerConditionResult(**item)
                                   for item in camera_condition_results_data]

        # Parse execute_result
        execute_result = None
        if data.get("execute_result"):
            execute_result_data = json.loads(data["execute_result"])
            execute_result = ExecuteResult(**execute_result_data)

            # Reduce the data sent to the UI, and obtain the dynamic execution results separately
            if execute_result.ai_recommend_dynamic_execute_result:
                # pylint: disable=assigning-non-slot
                execute_result.ai_recommend_dynamic_execute_result.chat_history_session = None

        return TriggerRuleLog(
            id=data["id"],
            timestamp=data["timestamp"],
            trigger_rule_id=data["trigger_rule_id"],
            trigger_rule_name=data["trigger_rule_name"],
            trigger_rule_condition=data["trigger_rule_condition"],
            condition_results=camera_condition_results,
            execute_result=execute_result
        )


    def create(self, log: TriggerRuleLog) -> Optional[str]:
        """
        Create new trigger rule log

        Args:
            log: Trigger rule log object

        Returns:
            Optional[str]: New ID (UUID) if successful, None if failed
        """
        try:
            if log.id is None:
                log.id = str(uuid.uuid4())

            if (log.execute_result and
                log.execute_result.ai_recommend_dynamic_execute_result and
                log.execute_result.ai_recommend_dynamic_execute_result.chat_history_session):
                log.execute_result.ai_recommend_dynamic_execute_result.chat_history_session.zip_toast_stream()

            sql = """
                INSERT INTO trigger_rule_log (id, timestamp, trigger_rule_id, trigger_rule_name, trigger_rule_condition, camera_condition_results, execute_result)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """
            params = (
                log.id,
                log.timestamp,
                log.trigger_rule_id,
                log.trigger_rule_name,
                log.trigger_rule_condition,
                json.dumps([result.model_dump(mode="json") for result in log.condition_results]),
                json.dumps(log.execute_result.model_dump(mode="json")) if log.execute_result else None
            )

            with self.db_connector.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(sql, params)
                conn.commit()

                logger.info("Trigger rule log created successfully: id=%s, rule_id=%s", log.id, log.trigger_rule_id)
                return log.id

        except (ValueError, TypeError, KeyError, AttributeError) as e:
            logger.error("Error creating trigger rule log: rule_id=%s, error=%s", log.trigger_rule_id, e)
            return None


    def get_all(self, limit: Optional[int] = None, offset: Optional[int] = None) -> List[TriggerRuleLog]:
        """
        Get all trigger rule logs with pagination support

        Args:
            limit: Limit number of logs to return
            offset: Offset for pagination

        Returns:
            List[TriggerRuleLog]: List of trigger rule logs, ordered by timestamp desc
        """
        try:
            if limit and offset is not None:
                sql = "SELECT * FROM trigger_rule_log ORDER BY timestamp DESC LIMIT ? OFFSET ?"
                params = (limit, offset)
            elif limit:
                sql = "SELECT * FROM trigger_rule_log ORDER BY timestamp DESC LIMIT ?"
                params = (limit,)
            else:
                sql = "SELECT * FROM trigger_rule_log ORDER BY timestamp DESC"
                params = ()

            results = self.db_connector.execute_query(sql, params)

            logs = [self._dict_to_trigger_rule_log(row) for row in results]
            logger.debug("Retrieved %s trigger rule logs", len(logs))
            return logs

        except (ValueError, TypeError, KeyError, AttributeError) as e:
            logger.error("Error retrieving trigger rule logs: error=%s", e)
            return []

    def delete_by_id(self, log_id: str) -> bool:
        """
        Delete trigger rule log by ID

        Args:
            log_id: Log ID (UUID)

        Returns:
            bool: True if deletion successful, False otherwise
        """
        try:
            sql = "DELETE FROM trigger_rule_log WHERE id = ?"
            params = (log_id,)

            affected_rows = self.db_connector.execute_update(sql, params)

            if affected_rows > 0:
                logger.info("Trigger rule log deleted successfully: id=%s", log_id)
                return True
            else:
                logger.warning("Trigger rule log not found for deletion: id=%s", log_id)
                return False

        except (ValueError, TypeError, KeyError, AttributeError) as e:
            logger.error("Error deleting trigger rule log: id=%s, error=%s", log_id, e)
            return False

    def delete_by_ids(self, log_ids: List[str]) -> bool:
        """
        Delete trigger rule logs by IDs

        Args:
            log_ids: List of log IDs (UUIDs)

        Returns:
            bool: True if deletion successful, False otherwise
        """
        try:
            if not log_ids:
                logger.warning("No log IDs provided for deletion")
                return True

            # Use executemany for better performance and cleaner code
            sql = "DELETE FROM trigger_rule_log WHERE id = ?"
            params_list = [(log_id,) for log_id in log_ids]

            affected_rows = self.db_connector.execute_many(sql, params_list)
            if affected_rows > 0:
                logger.info("Trigger rule logs deleted successfully: ids=%s, count=%s", log_ids, affected_rows)
                return True
            else:
                logger.warning("No trigger rule logs found for deletion: ids=%s", log_ids)
                return False
        except (ValueError, TypeError, KeyError, AttributeError) as e:
            logger.error("Error deleting trigger rule logs: ids=%s, error=%s", log_ids, e)
            return False

    def delete_by_rule_id(self, rule_id: str) -> bool:
        """
        Delete all trigger rule logs by rule ID

        Args:
            rule_id: Rule ID

        Returns:
            bool: True if deletion successful, False otherwise
        """
        try:
            sql = "DELETE FROM trigger_rule_log WHERE trigger_rule_id = ?"
            params = (rule_id,)

            affected_rows = self.db_connector.execute_update(sql, params)

            if affected_rows > 0:
                logger.info("Trigger rule logs deleted successfully: rule_id=%s, count=%s", rule_id, affected_rows)
                return True
            else:
                logger.warning("No trigger rule logs found for deletion: rule_id=%s", rule_id)
                return False

        except (ValueError, TypeError, KeyError, AttributeError) as e:
            logger.error("Error deleting trigger rule logs: rule_id=%s, error=%s", rule_id, e)
            return False

    def count_all(self) -> int:
        """
        Get total count of all trigger rule logs

        Returns:
            int: Total log count
        """
        try:
            sql = "SELECT COUNT(*) as count FROM trigger_rule_log"
            results = self.db_connector.execute_query(sql)

            count = results[0]["count"] if results else 0
            logger.debug("Total trigger rule logs count: %s", count)
            return count

        except (ValueError, TypeError, KeyError, AttributeError) as e:
            logger.error("Error counting trigger rule logs: error=%s", e)
            return 0

    def count_by_rule_id(self, rule_id: str) -> int:
        """
        Get total count of trigger logs for specified rule

        Args:
            rule_id: Rule ID

        Returns:
            int: Total log count
        """
        try:
            sql = "SELECT COUNT(*) as count FROM trigger_rule_log WHERE trigger_rule_id = ?"
            params = (rule_id,)
            results = self.db_connector.execute_query(sql, params)

            count = results[0]["count"] if results else 0
            logger.debug("Trigger rule logs count for rule_id=%s: %s", rule_id, count)
            return count

        except (ValueError, TypeError, KeyError, AttributeError) as e:
            logger.error("Error counting trigger rule logs: rule_id=%s, error=%s", rule_id, e)
            return 0


    def get_logs_before_days(self, days: int) -> List[TriggerRuleLog]:
        """
        Get logs before specified days

        Args:
            days: Number of days, get records before days days

        Returns:
            List[TriggerRuleLog]: List of trigger rule log records before specified days
        """
        try:
            cutoff_timestamp = int((datetime.now().timestamp() - days * 24 * 3600) * 1000)

            sql = """
                SELECT * FROM trigger_rule_log
                WHERE timestamp < ?
                ORDER BY timestamp DESC
            """
            params = (cutoff_timestamp, )

            results = self.db_connector.execute_query(sql, params)

            # Convert to TriggerRuleLog objects
            trigger_rule_logs = [
                self._dict_to_trigger_rule_log(row) for row in results
            ]

            logger.debug(
                "Found %d trigger rule log records older than %d days",
                len(trigger_rule_logs), days
            )
            return trigger_rule_logs

        except (ValueError, TypeError, KeyError, AttributeError) as e:
            logger.error(
                "Error getting trigger rule log records before %d days: error=%s",
                days, e
            )
            return []

    def update_execute_result(self, log_id: str, execute_result: ExecuteResult) -> bool:
        """
        Update execute_result for specified log ID
        
        Args:
            log_id: Log ID (UUID)
            execute_result: Execute result object
            
        Returns:
            bool: True if update successful, False otherwise
        """
        try:
            if (execute_result.ai_recommend_dynamic_execute_result and
                execute_result.ai_recommend_dynamic_execute_result.chat_history_session):
                execute_result.ai_recommend_dynamic_execute_result.chat_history_session.zip_toast_stream()
            sql = """
                UPDATE trigger_rule_log 
                SET execute_result = ?
                WHERE id = ?
            """
            params = (
                json.dumps(execute_result.model_dump(mode="json")),
                log_id
            )

            affected_rows = self.db_connector.execute_update(sql, params)

            if affected_rows > 0:
                logger.info("Execute result updated successfully: id=%s", log_id)
                return True
            else:
                logger.warning("Trigger rule log not found for update: id=%s", log_id)
                return False

        except (ValueError, TypeError, KeyError, AttributeError) as e:
            logger.error("Error updating execute result: id=%s, error=%s", log_id, e)
            return False

    def get_execute_result(self, log_id: str) -> Tuple[Optional[ExecuteResult], Optional[str]]:
        """
        Get execute_result and rule_id for specified log ID
        
        Args:
            log_id: Log ID (UUID)
            
        Returns:
            Tuple[Optional[ExecuteResult], Optional[str]]: (Execute result object, rule_id), (None, None) if not found
        """
        try:
            sql = """
                SELECT execute_result, trigger_rule_id 
                FROM trigger_rule_log 
                WHERE id = ?
            """
            params = (log_id,)

            results = self.db_connector.execute_query(sql, params)

            if not results:
                logger.debug("Execute result not found: id=%s", log_id)
                return None, None

            row = results[0]
            rule_id = row.get("trigger_rule_id")

            if not row.get("execute_result"):
                logger.debug("Execute result not found: id=%s", log_id)
                return None, rule_id

            execute_result_data = json.loads(row["execute_result"])
            execute_result = ExecuteResult(**execute_result_data)

            logger.debug("Execute result retrieved successfully: id=%s, rule_id=%s", log_id, rule_id)
            return execute_result, rule_id

        except (ValueError, TypeError, KeyError, AttributeError) as e:
            logger.error("Error retrieving execute result: id=%s, error=%s", log_id, e)
            return None, None
