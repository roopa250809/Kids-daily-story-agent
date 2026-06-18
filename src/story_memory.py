import os
from typing import Any, Dict, List


_mem0_client = None


def get_mem0_client() -> Any:
    global _mem0_client
    api_key = os.getenv("MEM0_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        from mem0 import MemoryClient
    except ImportError:
        return None
    if _mem0_client is None:
        _mem0_client = MemoryClient(api_key=api_key)
    return _mem0_client


def search_child_memory(child_id: str, query: str, limit: int = 5) -> List[Dict[str, Any]]:
    client = get_mem0_client()
    if client is None:
        return []
    try:
        result = client.search(query, user_id=child_id, limit=limit)
    except TypeError:
        result = client.search(query, user_id=child_id)
    except Exception:
        return []
    if isinstance(result, list):
        return result[:limit]
    if isinstance(result, dict):
        memories = result.get("results") or result.get("memories") or []
        return memories[:limit] if isinstance(memories, list) else []
    return []


def remember_child_fact(child_id: str, fact: str) -> bool:
    client = get_mem0_client()
    if client is None or not fact.strip():
        return False
    try:
        client.add([{"role": "user", "content": fact}], user_id=child_id)
    except Exception:
        return False
    return True


def format_mem0_memories(memories: List[Dict[str, Any]]) -> List[str]:
    formatted = []
    for memory in memories:
        if isinstance(memory, str):
            text = memory
        else:
            text = (
                memory.get("memory")
                or memory.get("text")
                or memory.get("content")
                or memory.get("data")
                or ""
            )
        if str(text).strip():
            formatted.append(str(text).strip())
    return formatted
