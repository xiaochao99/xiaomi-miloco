# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Music data access object
Handles CRUD operations for music_songs and music_scan_dirs tables
"""

import json
import logging
from typing import Optional, List, Dict, Any

from miloco_server.utils.database import get_db_connector

logger = logging.getLogger(__name__)


class MusicDAO:
    """Music data access object for songs and scan directories."""

    def __init__(self):
        self.db_connector = get_db_connector()
        # Try to migrate any legacy JSON data on first init
        self._migrate_from_json()

    # ─── Song Operations ────────────────────────────

    def get_all_songs(self) -> List[Dict[str, Any]]:
        """Retrieve all songs from the database."""
        try:
            sql = "SELECT * FROM music_songs ORDER BY title"
            return self.db_connector.execute_query(sql)
        except Exception as e:
            logger.error("Failed to get all songs: %s", e)
            return []

    def get_song(self, song_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a single song by ID."""
        try:
            sql = "SELECT * FROM music_songs WHERE id = ?"
            rows = self.db_connector.execute_query(sql, (song_id,))
            return rows[0] if rows else None
        except Exception as e:
            logger.error("Failed to get song %s: %s", song_id, e)
            return None

    def get_song_by_file_path(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Retrieve a song by its file path."""
        try:
            sql = "SELECT * FROM music_songs WHERE file_path = ?"
            rows = self.db_connector.execute_query(sql, (file_path,))
            return rows[0] if rows else None
        except Exception as e:
            logger.error("Failed to get song by path %s: %s", file_path, e)
            return None

    def upsert_song(self, song: Dict[str, Any]) -> bool:
        """
        Insert or update a song record.
        Uses INSERT OR REPLACE based on song ID.
        """
        try:
            lyrics_json = None
            if song.get("lyrics"):
                lyrics_json = json.dumps(
                    [{"time": l.get("time", l.time) if hasattr(l, 'time') else l["time"],
                      "text": l.get("text", l.text) if hasattr(l, 'text') else l["text"]}
                     for l in song["lyrics"]],
                    ensure_ascii=False,
                )

            sql = """
                INSERT OR REPLACE INTO music_songs
                    (id, title, artist, album, duration, cover_url, audio_url, file_path, lyrics_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """
            params = (
                song["id"],
                song.get("title", "未知歌曲"),
                song.get("artist", "未知歌手"),
                song.get("album", "未知专辑"),
                float(song.get("duration", 0)),
                song.get("cover_url", ""),
                song.get("audio_url", ""),
                song.get("file_path", ""),
                lyrics_json,
            )
            affected = self.db_connector.execute_update(sql, params)
            return affected > 0
        except Exception as e:
            logger.error("Failed to upsert song %s: %s", song.get("id"), e)
            return False

    def upsert_songs_batch(self, songs: List[Dict[str, Any]]) -> int:
        """Batch upsert multiple songs. Returns count of affected rows."""
        if not songs:
            return 0
        try:
            sql = """
                INSERT OR REPLACE INTO music_songs
                    (id, title, artist, album, duration, cover_url, audio_url, file_path, lyrics_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """
            params_list = []
            for song in songs:
                lyrics_json = None
                if song.get("lyrics"):
                    lyrics_json = json.dumps(
                        [{"time": l.get("time", l.time) if hasattr(l, 'time') else l["time"],
                          "text": l.get("text", l.text) if hasattr(l, 'text') else l["text"]}
                         for l in song["lyrics"]],
                        ensure_ascii=False,
                    )
                params_list.append((
                    song["id"],
                    song.get("title", "未知歌曲"),
                    song.get("artist", "未知歌手"),
                    song.get("album", "未知专辑"),
                    float(song.get("duration", 0)),
                    song.get("cover_url", ""),
                    song.get("audio_url", ""),
                    song.get("file_path", ""),
                    lyrics_json,
                ))
            return self.db_connector.execute_many(sql, params_list)
        except Exception as e:
            logger.error("Failed to batch upsert songs: %s", e)
            return 0

    def delete_song(self, song_id: str) -> bool:
        """Delete a song by ID."""
        try:
            sql = "DELETE FROM music_songs WHERE id = ?"
            affected = self.db_connector.execute_update(sql, (song_id,))
            return affected > 0
        except Exception as e:
            logger.error("Failed to delete song %s: %s", song_id, e)
            return False

    def delete_all_local_songs(self) -> int:
        """Delete all local_ prefixed songs. Returns count of deleted rows."""
        try:
            sql = "DELETE FROM music_songs WHERE id LIKE 'local_%'"
            return self.db_connector.execute_update(sql)
        except Exception as e:
            logger.error("Failed to delete local songs: %s", e)
            return 0

    def get_lyrics_json(self, song_id: str) -> Optional[str]:
        """Get lyrics JSON string for a song."""
        try:
            sql = "SELECT lyrics_json FROM music_songs WHERE id = ?"
            rows = self.db_connector.execute_query(sql, (song_id,))
            return rows[0]["lyrics_json"] if rows and rows[0].get("lyrics_json") else None
        except Exception as e:
            logger.error("Failed to get lyrics for %s: %s", song_id, e)
            return None

    def get_all_file_paths(self) -> Dict[str, str]:
        """Get mapping of song_id -> file_path for all songs."""
        try:
            sql = "SELECT id, file_path FROM music_songs WHERE file_path != ''"
            rows = self.db_connector.execute_query(sql)
            return {row["id"]: row["file_path"] for row in rows}
        except Exception as e:
            logger.error("Failed to get file paths: %s", e)
            return {}

    # ─── Scan Directory Operations ──────────────────

    def get_all_scan_dirs(self) -> List[Dict[str, Any]]:
        """Retrieve all scan directories."""
        try:
            sql = "SELECT * FROM music_scan_dirs ORDER BY created_at"
            return self.db_connector.execute_query(sql)
        except Exception as e:
            logger.error("Failed to get scan dirs: %s", e)
            return []

    def add_scan_dir(self, entry: Dict[str, Any]) -> bool:
        """Add a scan directory entry."""
        try:
            sql = """
                INSERT OR REPLACE INTO music_scan_dirs (id, name, path, recursive, last_scan, updated_at)
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """
            params = (
                entry["id"],
                entry.get("name", ""),
                entry["path"],
                1 if entry.get("recursive", True) else 0,
                entry.get("last_scan", None),
            )
            return self.db_connector.execute_update(sql, params) > 0
        except Exception as e:
            logger.error("Failed to add scan dir: %s", e)
            return False

    def delete_scan_dir(self, dir_id: str) -> bool:
        """Delete a scan directory by ID."""
        try:
            sql = "DELETE FROM music_scan_dirs WHERE id = ?"
            return self.db_connector.execute_update(sql, (dir_id,)) > 0
        except Exception as e:
            logger.error("Failed to delete scan dir %s: %s", dir_id, e)
            return False

    def update_scan_dir(self, dir_id: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Update a scan directory entry."""
        if not kwargs:
            return None
        try:
            allowed = {"name", "path", "recursive", "last_scan"}
            set_clauses = []
            params = []
            for k, v in kwargs.items():
                if k in allowed:
                    set_clauses.append(f"{k} = ?")
                    params.append(v)
            if not set_clauses:
                return None
            set_clauses.append("updated_at = CURRENT_TIMESTAMP")
            params.append(dir_id)
            sql = f"UPDATE music_scan_dirs SET {', '.join(set_clauses)} WHERE id = ?"
            self.db_connector.execute_update(sql, tuple(params))
            rows = self.db_connector.execute_query(
                "SELECT * FROM music_scan_dirs WHERE id = ?", (dir_id,)
            )
            return rows[0] if rows else None
        except Exception as e:
            logger.error("Failed to update scan dir %s: %s", dir_id, e)
            return None

    # ─── Migration from legacy JSON ─────────────────

    def _migrate_from_json(self):
        """Migrate legacy JSON files to database if they exist."""
        import os
        from pathlib import Path

        data_dir = Path(__file__).parent.parent / "data" / "music"
        songs_file = data_dir / "songs.json"
        dirs_file = data_dir / "scan_dirs.json"

        # Migrate songs.json
        if songs_file.exists():
            try:
                with open(songs_file, "r", encoding="utf-8") as f:
                    songs_data = json.load(f)
                if songs_data:
                    migrated = self.upsert_songs_batch(songs_data)
                    logger.info("Migrated %d songs from songs.json to database", migrated)
                    # Rename old file to avoid re-migration
                    backup = songs_file.with_suffix(".json.bak")
                    songs_file.rename(backup)
                    logger.info("Backed up songs.json to songs.json.bak")
            except Exception as e:
                logger.warning("Failed to migrate songs.json: %s", e)

        # Migrate scan_dirs.json
        if dirs_file.exists():
            try:
                with open(dirs_file, "r", encoding="utf-8") as f:
                    dirs_data = json.load(f)
                if dirs_data:
                    for entry in dirs_data:
                        self.add_scan_dir(entry)
                    logger.info("Migrated %d scan dirs from scan_dirs.json to database", len(dirs_data))
                    backup = dirs_file.with_suffix(".json.bak")
                    dirs_file.rename(backup)
                    logger.info("Backed up scan_dirs.json to scan_dirs.json.bak")
            except Exception as e:
                logger.warning("Failed to migrate scan_dirs.json: %s", e)

    # ─── Favorites Operations ───────────────────────

    def get_favorites(self) -> List[str]:
        """Get list of favorited song IDs."""
        try:
            sql = "SELECT song_id FROM music_favorites ORDER BY created_at DESC"
            rows = self.db_connector.execute_query(sql)
            return [r["song_id"] for r in rows]
        except Exception as e:
            logger.error("Failed to get favorites: %s", e)
            return []

    def is_favorite(self, song_id: str) -> bool:
        """Check if a song is favorited."""
        try:
            sql = "SELECT 1 FROM music_favorites WHERE song_id = ?"
            rows = self.db_connector.execute_query(sql, (song_id,))
            return len(rows) > 0
        except Exception as e:
            logger.error("Failed to check favorite %s: %s", song_id, e)
            return False

    def add_favorite(self, song_id: str) -> bool:
        """Add a song to favorites."""
        try:
            sql = "INSERT OR IGNORE INTO music_favorites (song_id) VALUES (?)"
            return self.db_connector.execute_update(sql, (song_id,)) > 0
        except Exception as e:
            logger.error("Failed to add favorite %s: %s", song_id, e)
            return False

    def remove_favorite(self, song_id: str) -> bool:
        """Remove a song from favorites."""
        try:
            sql = "DELETE FROM music_favorites WHERE song_id = ?"
            return self.db_connector.execute_update(sql, (song_id,)) > 0
        except Exception as e:
            logger.error("Failed to remove favorite %s: %s", song_id, e)
            return False

    def toggle_favorite(self, song_id: str) -> bool:
        """Toggle favorite state, returns new state (True=favorited)."""
        if self.is_favorite(song_id):
            self.remove_favorite(song_id)
            return False
        else:
            self.add_favorite(song_id)
            return True


# Global singleton
_music_dao_instance: Optional[MusicDAO] = None


def get_music_dao() -> MusicDAO:
    """Get the MusicDAO singleton instance."""
    global _music_dao_instance
    if _music_dao_instance is None:
        _music_dao_instance = MusicDAO()
    return _music_dao_instance
