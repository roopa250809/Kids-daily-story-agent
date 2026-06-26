import os
from typing import Any, Callable, Dict


def langsmith_enabled() -> bool:
    return (
        os.getenv("LANGSMITH_TRACING", "").lower() == "true"
        or os.getenv("LANGCHAIN_TRACING_V2", "").lower() == "true"
    ) and bool(os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY"))


def traceable(*, name: str, run_type: str = "chain", metadata: Dict[str, Any] | None = None) -> Callable:
    try:
        from langsmith import traceable as langsmith_traceable
    except ImportError:
        return lambda func: func

    return langsmith_traceable(name=name, run_type=run_type, metadata=metadata or {})


def tracing_status() -> Dict[str, Any]:
    return {
        "enabled": langsmith_enabled(),
        "project": os.getenv("LANGSMITH_PROJECT") or os.getenv("LANGCHAIN_PROJECT") or "default",
        "endpoint": os.getenv("LANGSMITH_ENDPOINT") or os.getenv("LANGCHAIN_ENDPOINT") or "https://api.smith.langchain.com",
        "has_api_key": bool(os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY")),
    }
