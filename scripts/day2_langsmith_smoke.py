import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.story_tracing import traceable, tracing_status


PLACEHOLDER_VALUES = {
    "your_nebius_api_key",
    "your_anthropic_api_key",
    "your_openai_api_key",
    "your_langsmith_api_key",
}


def _is_placeholder(value: str | None) -> bool:
    return not value or value.strip().lower() in PLACEHOLDER_VALUES


@traceable(name="day2_langsmith_smoke_run", run_type="chain", metadata={"purpose": "day2_trace_verification"})
def run_smoke(live: bool) -> dict:
    if not live:
        os.environ["NEBIUS_API_KEY"] = ""
        os.environ["ANTHROPIC_API_KEY"] = ""
        os.environ["OPENAI_IMAGE_MCP_URL"] = ""
        os.environ["OPENAI_API_KEY"] = ""
        os.environ["ELEVENLABS_API_KEY"] = ""
        os.environ["STORY_AGENT_MOCK_EMAIL"] = "true"

    import src.story_agent as story_agent
    from src.story_eval import evaluate_story_state
    if not live:
        story_agent.NEBIUS_API_KEY = ""
        story_agent.ANTHROPIC_API_KEY = ""
        story_agent.LLM_PROVIDER = "local"

    state = story_agent.generate_story_draft("demo-child", selected_theme="kindness")
    eval_result = evaluate_story_state(
        state,
        {
            "target_theme": "kindness",
            "target_moral": "kindness helps friends feel included",
            "must_avoid": ["violence", "scary stories"],
            "word_count_range": [80, 260],
            "max_latency_ms": 15000,
            "max_estimated_cost_usd": 0.05,
        },
        {
            "latency_ms": None,
            "estimated_cost_usd": None,
            "tool_failures": [],
        },
    )
    return {
        "live": live,
        "tracing": tracing_status(),
        "story_id": state.get("story_id"),
        "status": state.get("status"),
        "generation_source": state.get("generation_source"),
        "llm_model": state.get("llm_model"),
        "llm_usage": state.get("llm_usage", {}),
        "eval_passed": eval_result["passed"],
        "failed_metrics": eval_result["failed_metrics"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a Day 2 LangSmith tracing smoke test.")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Use configured providers instead of forcing local fallback mode.",
    )
    args = parser.parse_args()

    load_dotenv(override=True)
    status = tracing_status()
    if args.live and not status["enabled"]:
        print("Live tracing requested, but LangSmith is not enabled. Set LANGSMITH_TRACING=true and LANGSMITH_API_KEY.")
        return 1
    if args.live and _is_placeholder(os.getenv("NEBIUS_API_KEY")) and _is_placeholder(os.getenv("ANTHROPIC_API_KEY")):
        print("Live tracing requested, but no real LLM API key is configured.")
        return 1

    result = run_smoke(live=args.live)
    print(json.dumps(result, indent=2))
    if result["tracing"]["enabled"]:
        print(
            "LangSmith project URL: "
            f"https://smith.langchain.com/o/default/projects/p/{result['tracing']['project']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
