# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Trigger rule data access object
Handles CRUD operations for trigger_rule_v2 table
"""

import logging
import json
import uuid
from typing import Optional, List, Dict, Any
from datetime import datetime
from miloco_server.utils.database import get_db_connector
from miloco_server.schema.trigger_schema import (
    TriggerRuleV2,
)


logger = logging.getLogger(__name__)


class TriggerRuleDAO:
    """Trigger rule data access object"""

    def __init__(self):
        self.db_connector = get_db_connector()

    def _dict_to_trigger_rule_v2(self, data: Dict[str, Any]) -> TriggerRuleV2:
        """Convert database row to TriggerRuleV2."""
        payload = data.get("payload")
        if not payload:
            raise ValueError("Invalid v2 trigger rule row: payload is empty")
        return TriggerRuleV2.model_validate(json.loads(payload))

    def _trigger_rule_v2_to_dict(self, rule: TriggerRuleV2) -> Dict[str, Any]:
        """Convert TriggerRuleV2 to database fields."""
        payload = rule.model_dump(mode="json")
        condition_type = payload.get("trigger", {}).get("type", "llm")
        return {
            "id": rule.id,
            "name": rule.name,
            "enabled": rule.enabled,
            "condition_type": condition_type,
            "payload": json.dumps(payload),
        }

    # --------------------
    # v2 table operations
    # --------------------
    def create_v2(self, rule: TriggerRuleV2) -> Optional[str]:
        """Create trigger rule in trigger_rule_v2 table."""
        try:
            rule_id = str(uuid.uuid4())
            rule.id = rule_id
            data = self._trigger_rule_v2_to_dict(rule)
            now = datetime.now().isoformat()
            sql = """
                INSERT INTO trigger_rule_v2 (id, name, enabled, condition_type, payload, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """
            params = (
                data["id"],
                data["name"],
                data["enabled"],
                data["condition_type"],
                data["payload"],
                now,
                now,
            )
            with self.db_connector.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(sql, params)
                conn.commit()
            return rule_id
        except (ValueError, TypeError, KeyError, AttributeError) as e:
            logger.error("Error creating trigger rule v2: name=%s, error=%s", getattr(rule, "name", ""), e, exc_info=True)
            return None

    def get_by_id_v2(self, rule_id: str) -> Optional[TriggerRuleV2]:
        """Get trigger rule v2 by ID."""
        try:
            sql = "SELECT * FROM trigger_rule_v2 WHERE id = ?"
            rows = self.db_connector.execute_query(sql, (rule_id,))
            if not rows:
                return None
            return self._dict_to_trigger_rule_v2(rows[0])
        except (ValueError, TypeError, KeyError, AttributeError) as e:
            logger.error("Error querying trigger rule v2: id=%s, error=%s", rule_id, e)
            return None

    def get_all_v2(self, enabled_only: bool = False) -> List[TriggerRuleV2]:
        """Get all trigger rules from trigger_rule_v2."""
        if enabled_only:
            sql = "SELECT * FROM trigger_rule_v2 WHERE enabled = 1 ORDER BY created_at DESC"
        else:
            sql = "SELECT * FROM trigger_rule_v2 ORDER BY created_at DESC"
        rows = self.db_connector.execute_query(sql)
        return [self._dict_to_trigger_rule_v2(row) for row in rows]

    def update_v2(self, rule: TriggerRuleV2) -> bool:
        """Update trigger rule in trigger_rule_v2."""
        if not rule.id:
            return False
        data = self._trigger_rule_v2_to_dict(rule)
        sql = """
            UPDATE trigger_rule_v2
            SET name = ?, enabled = ?, condition_type = ?, payload = ?, updated_at = ?
            WHERE id = ?
        """
        params = (
            data["name"],
            data["enabled"],
            data["condition_type"],
            data["payload"],
            datetime.now().isoformat(),
            data["id"],
        )
        affected = self.db_connector.execute_update(sql, params)
        return affected > 0

    def delete_v2(self, rule_id: str) -> bool:
        """Delete trigger rule from trigger_rule_v2."""
        affected = self.db_connector.execute_update("DELETE FROM trigger_rule_v2 WHERE id = ?", (rule_id,))
        return affected > 0

    def exists_v2(self, rule_id: str) -> bool:
        """Check if v2 rule exists."""
        rows = self.db_connector.execute_query("SELECT COUNT(*) AS count FROM trigger_rule_v2 WHERE id = ?", (rule_id,))
        return bool(rows and rows[0]["count"] > 0)

    def exists_by_name_v2(self, name: str, exclude_id: Optional[str] = None) -> bool:
        """Check if v2 rule name exists."""
        if exclude_id:
            rows = self.db_connector.execute_query(
                "SELECT COUNT(*) AS count FROM trigger_rule_v2 WHERE name = ? AND id != ?",
                (name, exclude_id),
            )
        else:
            rows = self.db_connector.execute_query(
                "SELECT COUNT(*) AS count FROM trigger_rule_v2 WHERE name = ?",
                (name,),
            )
        return bool(rows and rows[0]["count"] > 0)

    def get_rules_by_camera_with_detection_v2(self, camera_id: str, exclude_rule_id: Optional[str] = None) -> List[TriggerRuleV2]:
        """
        Get v2 rules that have detection condition enabled for a specific camera.

        This is used by detection lifecycle management to decide whether a camera's
        detection pipeline can be stopped safely when a rule is deleted/disabled.
        """
        try:
            sql = "SELECT * FROM trigger_rule_v2 WHERE enabled = 1"
            rows = self.db_connector.execute_query(sql)

            rules: List[TriggerRuleV2] = []
            for row in rows:
                if exclude_rule_id and row.get("id") == exclude_rule_id:
                    continue
                try:
                    rule_v2 = self._dict_to_trigger_rule_v2(row)
                except Exception as e:  # pylint: disable=broad-exception-caught
                    logger.warning("Error parsing v2 rule row id=%s: %s", row.get("id"), e)
                    continue

                if camera_id not in (rule_v2.targets.camera_ids or []):
                    continue
                if not rule_v2.trigger.detection_condition or not rule_v2.trigger.detection_condition.enabled:
                    continue

                rules.append(rule_v2)

            return rules
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Error getting v2 rules by camera with detection: %s", e)
            return []
