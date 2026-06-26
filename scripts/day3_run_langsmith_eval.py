import argparse
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.story_eval import (
    estimate_cost_from_usage,
    evaluate_story_state,
    load_golden_dataset,
    summarize_evaluation_results,
    validate_golden_dataset,
)
from src.story_tracing import traceable, tracing_status


PROJECT_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = PROJECT_ROOT / "data" / "eval" / "runs"
REPORT_PATH = PROJECT_ROOT / "docs" / "day3_failure_analysis.md"
DEFAULT_DATASET_NAME = "kids-daily-story-agent-golden-v1"
DEFAULT_COST_PER_1K_TOKENS_USD = 0.0005


def _require_live_config() -> None:
    status = tracing_status()
    if not status["enabled"]:
        raise RuntimeError("LangSmith tracing is not enabled. Set LANGSMITH_TRACING=true and LANGSMITH_API_KEY.")
    if not (os.getenv("NEBIUS_API_KEY") or os.getenv("ANTHROPIC_API_KEY")):
        raise RuntimeError("A real LLM key is required for the live Day 3 eval run.")


def _sync_dataset_to_langsmith(cases: List[Dict[str, Any]], dataset_name: str) -> Dict[str, Any]:
    from langsmith import Client

    client = Client()
    if client.has_dataset(dataset_name=dataset_name):
        dataset = client.read_dataset(dataset_name=dataset_name)
    else:
        dataset = client.create_dataset(
            dataset_name,
            description="Golden dataset for the Kids Daily Story Agent Day 3 evaluation.",
            metadata={"source": "data/eval/golden_story_cases.jsonl", "case_count": len(cases)},
        )

    examples = []
    namespace = uuid.uuid5(uuid.NAMESPACE_URL, dataset_name)
    for case in cases:
        examples.append(
            {
                "id": str(uuid.uuid5(namespace, case["case_id"])),
                "inputs": {
                    "case_id": case["case_id"],
                    "category": case["category"],
                    "description": case.get("description", ""),
                    "child_profile": case["child_profile"],
                    "selected_theme": case["selected_theme"],
                    "recent_stories": case.get("recent_stories", []),
                    "mem0_memories": case.get("mem0_memories", []),
                    "options": case.get("options", {}),
                },
                "outputs": case["expected"],
                "metadata": {"category": case["category"], "line_number": case.get("_line_number")},
            }
        )
    existing_ids = {str(example.id) for example in client.list_examples(dataset_id=dataset.id)}
    new_examples = [example for example in examples if str(example["id"]) not in existing_ids]
    if new_examples:
        client.create_examples(dataset_id=dataset.id, examples=new_examples)
    return {"dataset_name": dataset_name, "dataset_id": str(dataset.id), "example_count": len(examples)}


def _attach_feedback(eval_result: Dict[str, Any]) -> None:
    if not tracing_status()["enabled"]:
        return
    try:
        from langsmith import Client
        from langsmith.run_helpers import get_current_run_tree
    except ImportError:
        return

    run_tree = get_current_run_tree()
    if run_tree is None:
        return

    client = Client()
    client.create_feedback(
        run_id=run_tree.id,
        key="overall_eval_score",
        score=eval_result["score"],
        value={"passed": eval_result["passed"], "failed_metrics": eval_result["failed_metrics"]},
        comment="Day 3 golden dataset evaluator score.",
    )
    for metric in eval_result["metrics"]:
        client.create_feedback(
            run_id=run_tree.id,
            key=metric["name"],
            score=metric["score"],
            value=metric["details"],
            comment="Automated Day 3 metric.",
        )


@traceable(name="day3_golden_dataset_case", run_type="chain", metadata={"workflow": "day3_eval"})
def _run_case(case: Dict[str, Any], cost_per_1k_tokens_usd: float) -> Dict[str, Any]:
    import src.story_agent as story_agent

    story_agent.find_similar_stories = lambda *args, **kwargs: []
    base_state: Dict[str, Any] = {
        "child_id": f"eval-{case['case_id']}",
        "child_profile": {**case["child_profile"], "child_id": f"eval-{case['case_id']}"},
        "selected_theme": case["selected_theme"],
        "recent_stories": case.get("recent_stories", []),
        "mem0_memories": case.get("mem0_memories", []),
        "retry_count": 0,
    }

    started = time.perf_counter()
    generated = story_agent.generate_story_node(base_state)
    state = {**base_state, **generated}
    validation = story_agent.validate_story_node(state)
    state = {**state, **validation}
    latency_ms = round((time.perf_counter() - started) * 1000, 2)

    usage = state.get("llm_usage", {})
    estimated_cost_usd = estimate_cost_from_usage(
        usage,
        cost_per_1k_tokens_usd=cost_per_1k_tokens_usd,
    )
    eval_result = evaluate_story_state(
        state,
        case["expected"],
        {
            "latency_ms": latency_ms,
            "estimated_cost_usd": estimated_cost_usd,
            "tool_failures": [],
        },
    )
    _attach_feedback(eval_result)
    return {
        "case_id": case["case_id"],
        "category": case["category"],
        "description": case.get("description", ""),
        "passed": eval_result["passed"],
        "score": eval_result["score"],
        "failed_metrics": eval_result["failed_metrics"],
        "metrics": eval_result["metrics"],
        "story_id": state.get("story_id"),
        "story_title": state.get("story_title"),
        "generation_source": state.get("generation_source"),
        "llm_model": state.get("llm_model"),
        "llm_usage": usage,
        "total_tokens": int(usage.get("total_tokens") or 0),
        "estimated_cost_usd": estimated_cost_usd,
        "latency_ms": latency_ms,
        "validation_passed": state.get("validation_passed"),
        "validation_issues": state.get("validation_issues", []),
    }


def _write_outputs(results: List[Dict[str, Any]], dataset_info: Dict[str, Any]) -> Dict[str, Any]:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    result_path = RESULTS_DIR / f"day3_eval_results_{stamp}.json"
    summary = summarize_evaluation_results(results)
    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "langsmith": tracing_status(),
        "dataset": dataset_info,
        "summary": summary,
        "results": results,
    }
    result_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _write_markdown_report(result_path, payload)
    return {"result_path": str(result_path), "report_path": str(REPORT_PATH), "summary": summary}


def _write_markdown_report(result_path: Path, payload: Dict[str, Any]) -> None:
    summary = payload["summary"]
    metric_lines = "\n".join(
        f"- `{metric}`: {count}"
        for metric, count in summary["metric_failures"].items()
    ) or "- None"
    category_lines = "\n".join(
        f"- `{category}`: {rate:.1%}"
        for category, rate in summary["category_failure_rates"].items()
    )
    failed_rows = [
        result for result in payload["results"]
        if result["failed_metrics"]
    ][:12]
    failed_table = "\n".join(
        "| {case_id} | {category} | {score:.3f} | {failed} | {latency} | {cost:.6f} |".format(
            case_id=row["case_id"],
            category=row["category"],
            score=row["score"],
            failed=", ".join(row["failed_metrics"]),
            latency=row["latency_ms"],
            cost=row["estimated_cost_usd"],
        )
        for row in failed_rows
    ) or "| None | - | - | - | - | - |"

    REPORT_PATH.write_text(
        f"""# Day 3: Evaluation and Failure Analysis

## Run Summary

- Cases run: {summary["case_count"]}
- Passed: {summary["passed_count"]}
- Failed: {summary["failed_count"]}
- Pass rate: {summary["pass_rate"]:.1%}
- Average latency: {summary["average_latency_ms"]} ms
- Total tokens: {summary["total_tokens"]}
- Failed-case tokens: {summary["failed_tokens"]}
- Estimated total cost: ${summary["total_estimated_cost_usd"]:.6f}
- Estimated failed-case cost: ${summary["failed_estimated_cost_usd"]:.6f}
- Dominant failure mode: `{summary["dominant_failure_mode"]}` ({summary["dominant_failure_count"]} cases)

LangSmith project: `{payload["langsmith"]["project"]}`

Raw results:

```text
{result_path}
```

## Failure Clusters

{metric_lines}

## Category Failure Rates

{category_lines}

## Sample Failed Cases

| Case | Category | Score | Failed Metrics | Latency ms | Est. Cost |
| --- | --- | ---: | --- | ---: | ---: |
{failed_table}

## Notes

Cost is estimated from provider-reported token usage using the configured `EVAL_COST_PER_1K_TOKENS_USD` rate. LangSmith stores the trace latency and token metadata for each case run.
""",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Day 3 golden dataset evaluation with LangSmith tracing.")
    parser.add_argument("--dataset-name", default=DEFAULT_DATASET_NAME)
    parser.add_argument("--limit", type=int, default=0, help="Optional limit for smoke-testing the eval runner.")
    parser.add_argument("--case-id", default="", help="Run a single case by ID.")
    parser.add_argument("--skip-langsmith-dataset-sync", action="store_true")
    args = parser.parse_args()

    load_dotenv(override=True)
    _require_live_config()
    cases = load_golden_dataset()
    validation = validate_golden_dataset(cases)
    if not validation["valid"]:
        print(json.dumps(validation, indent=2))
        return 1

    if args.case_id:
        cases = [case for case in cases if case["case_id"] == args.case_id]
    if args.limit:
        cases = cases[: args.limit]
    if not cases:
        print("No cases selected.")
        return 1

    dataset_info = {"dataset_name": args.dataset_name, "dataset_id": "", "example_count": len(cases)}
    if not args.skip_langsmith_dataset_sync:
        dataset_info = _sync_dataset_to_langsmith(cases, args.dataset_name)

    cost_per_1k_tokens_usd = float(os.getenv("EVAL_COST_PER_1K_TOKENS_USD", str(DEFAULT_COST_PER_1K_TOKENS_USD)))
    results = []
    for index, case in enumerate(cases, start=1):
        print(f"[{index}/{len(cases)}] {case['case_id']}")
        results.append(_run_case(case, cost_per_1k_tokens_usd))

    output = _write_outputs(results, dataset_info)
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
