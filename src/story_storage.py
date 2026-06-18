import json
import hashlib
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from src.config import (
        PINECONE_API_KEY,
        PINECONE_AUTO_CREATE_INDEX,
        PINECONE_CLOUD,
        PINECONE_DIMENSION,
        PINECONE_INDEX_NAME,
        PINECONE_REGION,
    )
except ImportError:
    PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
    PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "kids-daily-story-history")
    PINECONE_DIMENSION = int(os.getenv("PINECONE_DIMENSION", "384"))
    PINECONE_AUTO_CREATE_INDEX = os.getenv("PINECONE_AUTO_CREATE_INDEX", "false").lower() == "true"
    PINECONE_CLOUD = os.getenv("PINECONE_CLOUD", "aws")
    PINECONE_REGION = os.getenv("PINECONE_REGION", "us-east-1")


DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "story_agent"
PROFILES_FILE = DATA_DIR / "child_profiles.json"
HISTORY_FILE = DATA_DIR / "story_history.json"
EMAIL_LOG_FILE = DATA_DIR / "email_log.json"
DAILY_DELIVERY_FILE = DATA_DIR / "daily_delivery_log.json"


DEFAULT_PROFILE = {
    "child_id": "demo-child",
    "child_name": "Maya",
    "age": 6,
    "gender": "prefer not to say",
    "reading_level": "beginner",
    "interests": ["space", "soccer", "kind animals"],
    "favorite_characters": ["friendly robot", "curious explorer"],
    "parent_goals": ["confidence", "kindness", "bedtime routine"],
    "topics_to_avoid": ["violence", "scary stories"],
    "parent_email": "parent@example.com",
    "preferred_story_time": "8:30 PM",
}


def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _read_json(path: Path, default: Any) -> Any:
    _ensure_data_dir()
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def _write_json(path: Path, payload: Any) -> None:
    _ensure_data_dir()
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_child_profile(child_id: str = "demo-child") -> Dict[str, Any]:
    profiles = _read_json(PROFILES_FILE, {})
    profile = profiles.get(child_id)
    if profile:
        return profile

    profile = dict(DEFAULT_PROFILE)
    profile["child_id"] = child_id
    profiles[child_id] = profile
    _write_json(PROFILES_FILE, profiles)
    return profile


def save_child_profile(profile: Dict[str, Any]) -> Dict[str, Any]:
    child_id = profile.get("child_id") or "demo-child"
    profile = {**profile, "child_id": child_id}
    profiles = _read_json(PROFILES_FILE, {})
    profiles[child_id] = profile
    _write_json(PROFILES_FILE, profiles)
    return profile


_pinecone_index = None


def _story_text_for_embedding(record: Dict[str, Any]) -> str:
    parts = [
        record.get("story_title") or record.get("title", ""),
        record.get("theme", ""),
        " ".join(record.get("characters") or []),
        record.get("setting", ""),
        record.get("story_summary") or record.get("summary", ""),
    ]
    return " ".join(str(part) for part in parts if part)


def embed_story_record(record: Dict[str, Any]) -> List[float]:
    """
    Lightweight deterministic embedding for Pinecone demo storage.

    It is intentionally local so the app can use Pinecone without adding a
    second external embedding provider. For production, replace this with a
    real embedding model and keep the same Pinecone metadata/filter pattern.
    """
    text = _story_text_for_embedding(record).lower()
    tokens = re.findall(r"[a-z0-9]+", text)
    tokens.extend(text[i : i + 3] for i in range(max(len(text) - 2, 0)))

    vector = [0.0] * PINECONE_DIMENSION
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % PINECONE_DIMENSION
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign

    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        vector[0] = 1.0
        return vector
    return [value / norm for value in vector]


def _metadata_from_story(child_id: str, record: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "child_id": child_id,
        "story_id": record.get("story_id", ""),
        "story_title": record.get("story_title", ""),
        "theme": record.get("theme", ""),
        "characters": [str(item) for item in record.get("characters", [])],
        "setting": record.get("setting", ""),
        "story_summary": record.get("story_summary", ""),
        "story_text": str(record.get("story_text", ""))[:5000],
        "parent_note": record.get("parent_note", ""),
        "email_status": record.get("email_status", "unknown"),
        "saved_at": record.get("saved_at", ""),
    }


def _get_pinecone_index():
    global _pinecone_index
    if _pinecone_index is not None:
        return _pinecone_index
    if not PINECONE_API_KEY:
        return None

    from pinecone import Pinecone

    pc = Pinecone(api_key=PINECONE_API_KEY)
    index_names = pc.list_indexes().names()
    if PINECONE_INDEX_NAME not in index_names:
        if not PINECONE_AUTO_CREATE_INDEX:
            raise RuntimeError(
                f"Pinecone index '{PINECONE_INDEX_NAME}' does not exist. "
                "Create it or set PINECONE_AUTO_CREATE_INDEX=true."
            )
        from pinecone import ServerlessSpec

        pc.create_index(
            name=PINECONE_INDEX_NAME,
            dimension=PINECONE_DIMENSION,
            metric="cosine",
            spec=ServerlessSpec(cloud=PINECONE_CLOUD, region=PINECONE_REGION),
        )

    _pinecone_index = pc.Index(PINECONE_INDEX_NAME)
    return _pinecone_index


def _match_to_story(match: Any) -> Dict[str, Any]:
    metadata = getattr(match, "metadata", None) or match.get("metadata", {})
    score = getattr(match, "score", None)
    if score is None and isinstance(match, dict):
        score = match.get("score")
    return {
        "story_id": metadata.get("story_id"),
        "story_title": metadata.get("story_title"),
        "theme": metadata.get("theme"),
        "characters": metadata.get("characters", []),
        "setting": metadata.get("setting"),
        "story_summary": metadata.get("story_summary"),
        "story_text": metadata.get("story_text"),
        "parent_note": metadata.get("parent_note"),
        "email_status": metadata.get("email_status"),
        "saved_at": metadata.get("saved_at"),
        "similarity_score": score or 0.0,
    }


def get_recent_stories(child_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    index = _get_pinecone_index()
    if index is None:
        return []

    query_record = {
        "story_title": f"story history for {child_id}",
        "theme": "",
        "characters": [],
        "setting": "",
        "story_summary": f"previous stories for child {child_id}",
    }
    result = index.query(
        vector=embed_story_record(query_record),
        top_k=limit,
        filter={"child_id": {"$eq": child_id}},
        include_metadata=True,
    )
    matches = getattr(result, "matches", None) or result.get("matches", [])
    return [_match_to_story(match) for match in matches]


def find_similar_stories(
    child_id: str,
    story_record: Dict[str, Any],
    limit: int = 3,
) -> List[Dict[str, Any]]:
    index = _get_pinecone_index()
    if index is None:
        return []

    result = index.query(
        vector=embed_story_record(story_record),
        top_k=limit,
        filter={"child_id": {"$eq": child_id}},
        include_metadata=True,
    )
    matches = getattr(result, "matches", None) or result.get("matches", [])
    return [_match_to_story(match) for match in matches]


def save_story_history(child_id: str, story_record: Dict[str, Any]) -> Dict[str, Any]:
    story_id = story_record.get("story_id") or f"story-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    record = {
        **story_record,
        "story_id": story_id,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    index = _get_pinecone_index()
    if index is None:
        return {**record, "pinecone_status": "disabled"}

    index.upsert(
        vectors=[
            {
                "id": f"{child_id}:{story_id}",
                "values": embed_story_record(record),
                "metadata": _metadata_from_story(child_id, record),
            }
        ]
    )
    record["pinecone_status"] = "upserted"
    return record


def log_email_status(entry: Dict[str, Any]) -> Dict[str, Any]:
    logs = _read_json(EMAIL_LOG_FILE, [])
    record = {
        **entry,
        "logged_at": datetime.now(timezone.utc).isoformat(),
    }
    logs.append(record)
    _write_json(EMAIL_LOG_FILE, logs)
    return record


def get_daily_delivery_record(child_id: str, date_key: str) -> Optional[Dict[str, Any]]:
    records = _read_json(DAILY_DELIVERY_FILE, [])
    for record in records:
        if record.get("child_id") == child_id and record.get("date") == date_key:
            return record
    return None


def save_daily_delivery_record(entry: Dict[str, Any]) -> Dict[str, Any]:
    records = _read_json(DAILY_DELIVERY_FILE, [])
    record = {
        **entry,
        "logged_at": datetime.now(timezone.utc).isoformat(),
    }
    records.append(record)
    _write_json(DAILY_DELIVERY_FILE, records)
    return record


def find_story_by_id(child_id: str, story_id: str) -> Optional[Dict[str, Any]]:
    index = _get_pinecone_index()
    if index is None:
        return None

    result = index.fetch(ids=[f"{child_id}:{story_id}"])
    vectors = getattr(result, "vectors", None) or result.get("vectors", {})
    vector = vectors.get(f"{child_id}:{story_id}")
    if not vector:
        return None
    return _match_to_story({"metadata": vector.get("metadata", {}), "score": 1.0})
