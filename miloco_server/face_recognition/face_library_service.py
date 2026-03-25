# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.
"""
Face library service backed by the existing KV table.

We store each profile as:
  - id, name, embeddings[]

Embeddings are assumed to be unit-normalized vectors (cosine similarity via dot product).
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

from miloco_server.utils.database import get_db_connector

logger = logging.getLogger(__name__)


INDEX_KEY = "face_library:index"
PROFILE_KEY_PREFIX = "face_library:profile:"
MAX_EMBEDDINGS_PER_PROFILE = 20


@dataclass
class FaceProfile:
    id: str
    name: str
    embeddings: List[np.ndarray]


@dataclass
class FaceMatch:
    id: str
    name: str
    score: float


class FaceLibraryService:
    """
    Minimal 1:N face search storage.

    Notes:
    - For CPU friendliness and MVP, we use in-process cosine similarity.
    - KVDao is used for persistence; this is suitable for small galleries.
    """

    def __init__(self):
        self.db = get_db_connector()

    def _kv_get(self, key: str) -> Optional[str]:
        rows = self.db.execute_query("SELECT value FROM kv WHERE key = ?", (key,))
        if not rows:
            return None
        return rows[0].get("value")

    def _kv_set(self, key: str, value: str) -> None:
        sql = """
            INSERT INTO kv (key, value, created_at, updated_at)
            VALUES (?, ?, datetime('now'), datetime('now'))
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = datetime('now')
        """
        self.db.execute_update(sql, (key, value))

    def _kv_delete(self, key: str) -> bool:
        affected = self.db.execute_update("DELETE FROM kv WHERE key = ?", (key,))
        return affected > 0

    def _load_index(self) -> List[str]:
        raw = self._kv_get(INDEX_KEY)
        if not raw:
            return []
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return [str(x) for x in data]
        except Exception:  # pylint: disable=broad-exception-caught
            pass
        return []

    def _save_index(self, ids: List[str]) -> None:
        self._kv_set(INDEX_KEY, json.dumps(ids, ensure_ascii=False))

    def list_profiles(self) -> List[Dict]:
        ids = self._load_index()
        profiles: List[Dict] = []
        for fid in ids:
            p = self._get_profile(fid)
            if not p:
                continue
            profiles.append({"id": p.id, "name": p.name})
        return profiles

    def _get_profile(self, profile_id: str) -> Optional[FaceProfile]:
        key = f"{PROFILE_KEY_PREFIX}{profile_id}"
        raw = self._kv_get(key)
        if not raw:
            return None
        data = json.loads(raw)
        embeddings = [np.asarray(e, dtype=np.float32) for e in data.get("embeddings", [])]
        # Ensure unit normalization; if stored vectors are already normalized this is cheap.
        normed = []
        for emb in embeddings:
            norm = float(np.linalg.norm(emb)) if emb.size else 0.0
            if emb.size and norm > 0:
                normed.append(emb / norm)
        return FaceProfile(
            id=str(data["id"]),
            name=str(data["name"]),
            embeddings=normed,
        )

    def _find_profile_id_by_name(self, name: str) -> Optional[str]:
        target = (name or "").strip()
        if not target:
            return None
        for fid in self._load_index():
            profile = self._get_profile(fid)
            if not profile:
                continue
            if profile.name.strip() == target:
                return fid
        return None

    def enroll(self, name: str, embedding: np.ndarray) -> Dict:
        clean_name = (name or "").strip()
        if not clean_name:
            raise ValueError("name is required")

        emb = np.asarray(embedding, dtype=np.float32)
        norm = float(np.linalg.norm(emb)) if emb.size else 0.0
        if emb.size and norm > 0:
            emb = emb / norm

        # Same-name aggregation: append embedding to existing profile instead of creating a new one.
        existing_id = self._find_profile_id_by_name(clean_name)
        if existing_id:
            key = f"{PROFILE_KEY_PREFIX}{existing_id}"
            raw = self._kv_get(key)
            if raw:
                data = json.loads(raw)
                embeddings = data.get("embeddings", [])
                embeddings.append(emb.tolist())
                # Keep only latest N vectors to avoid unbounded growth.
                if len(embeddings) > MAX_EMBEDDINGS_PER_PROFILE:
                    embeddings = embeddings[-MAX_EMBEDDINGS_PER_PROFILE:]
                data["embeddings"] = embeddings
                data["name"] = clean_name
                self._kv_set(key, json.dumps(data, ensure_ascii=False))
                return {
                    "id": existing_id,
                    "name": clean_name,
                    "merged": True,
                    "embedding_count": len(embeddings),
                }

        profile_id = str(uuid.uuid4())
        profile = {
            "id": profile_id,
            "name": clean_name,
            "embeddings": [emb.tolist()],
        }

        # Persist profile
        self._kv_set(f"{PROFILE_KEY_PREFIX}{profile_id}", json.dumps(profile, ensure_ascii=False))

        # Update index
        ids = self._load_index()
        if profile_id not in ids:
            ids.append(profile_id)
            self._save_index(ids)

        return {"id": profile_id, "name": clean_name, "merged": False, "embedding_count": 1}

    def delete_profile(self, profile_id: str) -> bool:
        key = f"{PROFILE_KEY_PREFIX}{profile_id}"
        ok = self._kv_delete(key)
        ids = self._load_index()
        if profile_id in ids:
            ids = [x for x in ids if x != profile_id]
            self._save_index(ids)
        return ok

    def search(
        self,
        query_embedding: np.ndarray,
        top_k: int = 5,
        accept_threshold: float = 0.35,
    ) -> List[FaceMatch]:
        ids = self._load_index()
        if not ids:
            return []

        q = np.asarray(query_embedding, dtype=np.float32)
        q_norm = float(np.linalg.norm(q)) if q.size else 0.0
        if q.size and q_norm > 0:
            q = q / q_norm

        matches: List[FaceMatch] = []
        for fid in ids:
            profile = self._get_profile(fid)
            if not profile or not profile.embeddings:
                continue

            # Best similarity per profile
            best = -1.0
            for emb in profile.embeddings:
                # cosine similarity via dot product since vectors are unit-normalized
                score = float(np.dot(q, emb))
                if score > best:
                    best = score

            if best >= accept_threshold:
                matches.append(FaceMatch(id=profile.id, name=profile.name, score=best))

        matches.sort(key=lambda x: x.score, reverse=True)
        return matches[:top_k]

