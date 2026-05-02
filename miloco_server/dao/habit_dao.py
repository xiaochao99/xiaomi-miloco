# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

import json
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from miloco_server.schema.habit_schema import (
    BehaviorPattern,
    HabitCategory,
    HabitEvent,
    HabitEventType,
    LearningModel,
)
from miloco_server.utils.database import SQLiteConnector

logger = logging.getLogger(__name__)


class HabitDAO:
    _instance: Optional["HabitDAO"] = None

    def __init__(self, db_connector: SQLiteConnector):
        self.db = db_connector
        self._initialized_tables: set = set()
        self._initialized = False
        HabitDAO._instance = self

    @classmethod
    def get_instance(cls) -> Optional["HabitDAO"]:
        return cls._instance

    def initialize(self) -> None:
        if self._initialized:
            return
        self._ensure_pattern_table()
        self._ensure_model_table()
        self._ensure_current_month_table()
        self._migrate_recent_tables()
        self._initialized = True
        logger.info("HabitDAO initialized")

    def _migrate_recent_tables(self) -> None:
        now = datetime.now()
        for months_ago in range(6):
            year = now.year
            month = now.month - months_ago
            if month <= 0:
                month += 12
                year -= 1
            table_name = f"habit_events_{year}_{month:02d}"
            if self._table_exists(table_name):
                self._migrate_events_table(table_name)

    def _get_table_name(self, date: Optional[datetime] = None) -> str:
        date = date or datetime.now()
        return f"habit_events_{date.strftime('%Y_%m')}"

    def _ensure_current_month_table(self) -> None:
        table_name = self._get_table_name()
        if table_name in self._initialized_tables:
            return
        self._create_events_table(table_name)
        self._initialized_tables.add(table_name)

    def _create_events_table(self, table_name: str) -> None:
        self.db.execute_update(f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                event_id TEXT NOT NULL UNIQUE,
                event_type TEXT NOT NULL,
                category TEXT NOT NULL,
                entity_id TEXT,
                device_domain TEXT,
                device_name TEXT,
                old_state TEXT,
                new_state TEXT,
                attributes TEXT,
                day_of_week INTEGER,
                hour_of_day INTEGER,
                minute_of_hour INTEGER,
                is_weekend INTEGER DEFAULT 0,
                is_holiday INTEGER DEFAULT 0,
                temperature REAL,
                humidity REAL,
                light_level REAL,
                is_home INTEGER,
                is_anyone_present INTEGER,
                outdoor_temperature REAL,
                weather TEXT,
                water_leak_detected INTEGER,
                traffic_restricted TEXT,
                source TEXT DEFAULT 'ha_websocket',
                confidence REAL DEFAULT 1.0,
                metadata TEXT
            )
        """)
        self.db.execute_update(
            f"CREATE INDEX IF NOT EXISTS idx_{table_name}_timestamp ON {table_name} (timestamp)"
        )
        self.db.execute_update(
            f"CREATE INDEX IF NOT EXISTS idx_{table_name}_entity ON {table_name} (entity_id, timestamp)"
        )
        self.db.execute_update(
            f"CREATE INDEX IF NOT EXISTS idx_{table_name}_category ON {table_name} (category, timestamp)"
        )

    def _ensure_pattern_table(self) -> None:
        self.db.execute_update("""
            CREATE TABLE IF NOT EXISTS user_behavior_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern_type TEXT NOT NULL,
                user_id TEXT DEFAULT 'default',
                entity_id TEXT,
                category TEXT,
                day_of_week INTEGER,
                hour_of_day INTEGER,
                minute_of_hour INTEGER,
                confidence REAL DEFAULT 0.5,
                occurrence_count INTEGER DEFAULT 1,
                last_occurrence REAL,
                metadata TEXT,
                created_at REAL,
                updated_at REAL
            )
        """)
        self.db.execute_update(
            "CREATE INDEX IF NOT EXISTS idx_patterns_type ON user_behavior_patterns (pattern_type)"
        )
        self.db.execute_update(
            "CREATE INDEX IF NOT EXISTS idx_patterns_entity ON user_behavior_patterns (entity_id)"
        )
        self.db.execute_update(
            "CREATE INDEX IF NOT EXISTS idx_patterns_time ON user_behavior_patterns (day_of_week, hour_of_day)"
        )

    def _ensure_model_table(self) -> None:
        self.db.execute_update("""
            CREATE TABLE IF NOT EXISTS learning_models (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_type TEXT NOT NULL UNIQUE,
                model_data BLOB,
                version INTEGER DEFAULT 1,
                accuracy REAL,
                training_samples INTEGER,
                created_at REAL
            )
        """)

    def insert_event(self, event: HabitEvent) -> str:
        self._ensure_current_month_table()
        table_name = self._get_table_name(event.timestamp)
        data = event.to_dict()
        cols = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        self.db.execute_update(
            f"INSERT OR IGNORE INTO {table_name} ({cols}) VALUES ({placeholders})",
            tuple(data.values()),
        )
        return event.event_id

    def insert_events_batch(self, events: List[HabitEvent]) -> int:
        if not events:
            return 0
        grouped: Dict[str, List[HabitEvent]] = {}
        for event in events:
            table_name = self._get_table_name(event.timestamp)
            grouped.setdefault(table_name, []).append(event)

        total = 0
        for table_name, table_events in grouped.items():
            if table_name not in self._initialized_tables:
                self._create_events_table(table_name)
                self._migrate_events_table(table_name)
                self._initialized_tables.add(table_name)
            all_data_keys = list(table_events[0].to_dict().keys())
            table_cols = self._get_table_columns(table_name)
            valid_keys = [k for k in all_data_keys if k in table_cols]
            cols = ", ".join(valid_keys)
            placeholders = ", ".join(["?"] * len(valid_keys))
            params_list = [tuple(e.to_dict()[k] for k in valid_keys) for e in table_events]
            total += self.db.execute_many(
                f"INSERT OR IGNORE INTO {table_name} ({cols}) VALUES ({placeholders})",
                params_list,
            )
        return total

    def get_events_by_timerange(
        self,
        start: datetime,
        end: datetime,
        entity_id: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 1000,
    ) -> List[HabitEvent]:
        tables = self._get_tables_in_range(start, end)
        results: List[HabitEvent] = []

        for table_name in tables:
            if not self._table_exists(table_name):
                continue

            conditions = ["timestamp >= ?", "timestamp <= ?"]
            params: list = [start.timestamp(), end.timestamp()]

            if entity_id:
                conditions.append("entity_id = ?")
                params.append(entity_id)
            if category:
                conditions.append("category = ?")
                params.append(category)

            where_clause = " AND ".join(conditions)
            params.append(limit - len(results))

            try:
                rows = self.db.execute_query(
                    f"SELECT * FROM {table_name} WHERE {where_clause} ORDER BY timestamp DESC LIMIT ?",
                    tuple(params),
                )
                results.extend(HabitEvent.from_row(row) for row in rows)
            except Exception:
                continue

            if len(results) >= limit:
                break

        return results[:limit]

    def get_events_by_entity(
        self, entity_id: str, days: int = 30, limit: int = 500
    ) -> List[HabitEvent]:
        end = datetime.now()
        start = end - timedelta(days=days)
        return self.get_events_by_timerange(start, end, entity_id=entity_id, limit=limit)

    def get_events_by_category(
        self, category: str, days: int = 30, limit: int = 500
    ) -> List[HabitEvent]:
        end = datetime.now()
        start = end - timedelta(days=days)
        return self.get_events_by_timerange(start, end, category=category, limit=limit)

    def get_recent_events(self, hours: int = 24, limit: int = 200) -> List[HabitEvent]:
        end = datetime.now()
        start = end - timedelta(hours=hours)
        return self.get_events_by_timerange(start, end, limit=limit)

    def _get_tables_in_range(self, start: datetime, end: datetime) -> List[str]:
        tables = []
        current = start.replace(day=1)
        end_month = end.replace(day=1)

        while current <= end_month:
            table_name = self._get_table_name(current)
            tables.append(table_name)
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)

        return tables

    def save_patterns(self, patterns: List[BehaviorPattern]) -> int:
        count = 0
        now = time.time()

        for pattern in patterns:
            existing = self.db.execute_query(
                "SELECT id, occurrence_count FROM user_behavior_patterns "
                "WHERE pattern_type = ? AND entity_id = ? AND day_of_week = ? AND hour_of_day = ? AND minute_of_hour = ?",
                (pattern.pattern_type, pattern.entity_id, pattern.day_of_week, pattern.hour_of_day, pattern.minute_of_hour),
            )

            if existing:
                old_count = existing[0]["occurrence_count"]
                new_count = old_count + pattern.occurrence_count
                new_confidence = min(1.0, (old_count * existing[0].get("confidence", 0.5) + pattern.occurrence_count * pattern.confidence) / new_count)

                self.db.execute_update(
                    "UPDATE user_behavior_patterns SET occurrence_count = ?, confidence = ?, last_occurrence = ?, updated_at = ? WHERE id = ?",
                    (new_count, new_confidence, pattern.last_occurrence or now, now, existing[0]["id"]),
                )
            else:
                data = pattern.to_dict()
                data["created_at"] = now
                data["updated_at"] = now
                if data["last_occurrence"] is None:
                    data["last_occurrence"] = now

                cols = ", ".join(data.keys())
                placeholders = ", ".join(["?"] * len(data))
                self.db.execute_update(
                    f"INSERT INTO user_behavior_patterns ({cols}) VALUES ({placeholders})",
                    tuple(data.values()),
                )
            count += 1

        return count

    def get_patterns(
        self,
        pattern_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        category: Optional[str] = None,
        day_of_week: Optional[int] = None,
        min_confidence: float = 0.0,
        limit: int = 100,
    ) -> List[BehaviorPattern]:
        if not self._table_exists("user_behavior_patterns"):
            return []

        conditions = ["confidence >= ?"]
        params: list = [min_confidence]

        if pattern_type:
            conditions.append("pattern_type = ?")
            params.append(pattern_type)
        if entity_id:
            conditions.append("entity_id = ?")
            params.append(entity_id)
        if category:
            conditions.append("category = ?")
            params.append(category)
        if day_of_week is not None:
            conditions.append("(day_of_week = ? OR day_of_week IS NULL)")
            params.append(day_of_week)

        where_clause = " AND ".join(conditions)
        params.append(limit)

        rows = self.db.execute_query(
            f"SELECT * FROM user_behavior_patterns WHERE {where_clause} ORDER BY confidence DESC, occurrence_count DESC LIMIT ?",
            tuple(params),
        )

        return [BehaviorPattern.from_row(row) for row in rows]

    def get_all_patterns(self, min_confidence: float = 0.3) -> List[BehaviorPattern]:
        return self.get_patterns(min_confidence=min_confidence, limit=1000)

    def delete_pattern(self, pattern_id: int) -> bool:
        rows = self.db.execute_update(
            "DELETE FROM user_behavior_patterns WHERE id = ?", (pattern_id,)
        )
        return rows > 0

    def save_model(self, model_type: str, model_data: bytes, accuracy: Optional[float] = None, training_samples: Optional[int] = None) -> None:
        now = time.time()
        existing = self.db.execute_query(
            "SELECT id, version FROM learning_models WHERE model_type = ?", (model_type,)
        )

        if existing:
            new_version = existing[0]["version"] + 1
            self.db.execute_update(
                "UPDATE learning_models SET model_data = ?, version = ?, accuracy = ?, training_samples = ?, created_at = ? WHERE model_type = ?",
                (model_data, new_version, accuracy, training_samples, now, model_type),
            )
        else:
            self.db.execute_update(
                "INSERT INTO learning_models (model_type, model_data, version, accuracy, training_samples, created_at) VALUES (?, ?, 1, ?, ?, ?)",
                (model_type, model_data, accuracy, training_samples, now),
            )

    def load_model(self, model_type: str) -> Optional[LearningModel]:
        rows = self.db.execute_query(
            "SELECT * FROM learning_models WHERE model_type = ?", (model_type,)
        )
        if not rows:
            return None

        row = rows[0]
        return LearningModel(
            id=row["id"],
            model_type=row["model_type"],
            model_data=row["model_data"],
            version=row["version"],
            accuracy=row["accuracy"],
            training_samples=row["training_samples"],
            created_at=row["created_at"],
        )

    def delete_expired_events(self, cutoff_date: datetime) -> int:
        tables = self._get_tables_in_range(datetime(2020, 1, 1), cutoff_date)
        total_deleted = 0
        cutoff_ts = cutoff_date.timestamp()

        for table_name in tables:
            try:
                if not self._table_exists(table_name):
                    continue
                rows = self.db.execute_update(
                    f"DELETE FROM {table_name} WHERE timestamp < ?", (cutoff_ts,)
                )
                total_deleted += rows
            except Exception:
                continue

        return total_deleted

    def delete_expired_patterns(self, cutoff_date: datetime) -> int:
        if not self._table_exists("user_behavior_patterns"):
            return 0
        cutoff_ts = cutoff_date.timestamp()
        try:
            rows = self.db.execute_update(
                "DELETE FROM user_behavior_patterns WHERE last_occurrence < ? OR (last_occurrence IS NULL AND created_at < ?)",
                (cutoff_ts, cutoff_ts)
            )
            return rows
        except Exception as e:
            logger.error("Failed to delete expired patterns: %s", e)
            return 0

    def _table_exists(self, table_name: str) -> bool:
        try:
            rows = self.db.execute_query(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,),
            )
            return len(rows) > 0
        except Exception:
            return False

    def _get_table_columns(self, table_name: str) -> set:
        try:
            rows = self.db.execute_query(f"PRAGMA table_info({table_name})")
            return {row["name"] for row in rows}
        except Exception:
            return set()

    def _migrate_events_table(self, table_name: str) -> None:
        new_columns = {
            "is_home": "INTEGER",
            "is_anyone_present": "INTEGER",
            "outdoor_temperature": "REAL",
            "weather": "TEXT",
            "water_leak_detected": "INTEGER",
            "traffic_restricted": "TEXT",
        }
        existing = self._get_table_columns(table_name)
        for col_name, col_type in new_columns.items():
            if col_name not in existing:
                try:
                    self.db.execute_update(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}")
                except Exception:
                    pass

    def get_event_stats(self) -> Dict[str, Any]:
        now = datetime.now()
        tables = self._get_tables_in_range(now - timedelta(days=90), now)
        total_events = 0
        table_stats = []

        for table_name in tables:
            if not self._table_exists(table_name):
                continue
            try:
                rows = self.db.execute_query(f"SELECT COUNT(*) as cnt FROM {table_name}")
                count = rows[0]["cnt"] if rows else 0
                total_events += count
                if count > 0:
                    table_stats.append({"table": table_name, "count": count})
            except Exception:
                continue

        pattern_count = 0
        if self._table_exists("user_behavior_patterns"):
            try:
                pattern_rows = self.db.execute_query("SELECT COUNT(*) as cnt FROM user_behavior_patterns")
                pattern_count = pattern_rows[0]["cnt"] if pattern_rows else 0
            except Exception:
                pass

        return {
            "total_events": total_events,
            "table_stats": table_stats,
            "total_patterns": pattern_count,
        }

    def get_context_grouped_events(self, days: int = 30, limit: int = 5000) -> List[Dict[str, Any]]:
        try:
            start_time = (datetime.now() - timedelta(days=days)).timestamp()
            end_time = datetime.now().timestamp()
            all_events: List[Dict[str, Any]] = []
            months = set()
            current = datetime.fromtimestamp(start_time)
            end = datetime.fromtimestamp(end_time)
            while current <= end:
                months.add(current.strftime("%Y_%m"))
                if current.month == 12:
                    current = current.replace(year=current.year + 1, month=1)
                else:
                    current = current.replace(month=current.month + 1)
            for month_str in months:
                table_name = f"habit_events_{month_str}"
                if not self._table_exists(table_name):
                    continue
                rows = self.db.execute_query(
                    f"""SELECT * FROM {table_name}
                        WHERE timestamp BETWEEN ? AND ?
                        ORDER BY entity_id, timestamp""",
                    (start_time, end_time),
                    fetch_all=True,
                )
                all_events.extend(rows)
            all_events.sort(key=lambda e: e.get("entity_id", ""))
            return all_events[:limit]
        except Exception as e:
            logger.error("Failed to get context grouped events: %s", e)
            return []
