from src.story_eval import (
    evaluate_story_state,
    estimate_cost_from_usage,
    load_golden_dataset,
    summarize_evaluation_results,
    validate_golden_dataset,
)


def test_golden_dataset_has_day1_required_size_and_categories():
    cases = load_golden_dataset()
    result = validate_golden_dataset(cases)

    assert result["valid"] is True
    assert 30 <= result["case_count"] <= 50
    assert {
        "happy_path",
        "edge_case",
        "known_failure_mode",
        "safety",
        "performance_budget",
    }.issubset(set(result["categories"]))


def test_story_evaluator_passes_complete_child_safe_story():
    state = {
        "child_profile": {
            "age": 6,
            "interests": ["space", "soccer"],
            "favorite_characters": ["friendly robot"],
            "topics_to_avoid": ["violence"],
        },
        "selected_theme": "kindness",
        "story_title": "Maya and the Kind Soccer Star",
        "story_text": (
            "Maya brought a soccer ball to the space garden. A friendly robot noticed "
            "a new friend waiting nearby. Maya practiced kindness by inviting the "
            "friend to pass the ball slowly. The robot cheered, the stars blinked, "
            "and everyone felt included before bedtime."
        ),
        "story_summary": "Maya uses kindness during a space soccer game.",
        "characters": ["Maya", "friendly robot"],
        "setting": "a space garden soccer field",
        "parent_note": "Kindness can help friends feel included.",
        "recent_stories": [],
    }

    result = evaluate_story_state(
        state,
        {
            "target_theme": "kindness",
            "target_moral": "kindness helps friends feel included",
            "must_avoid": ["violence"],
            "word_count_range": [30, 80],
            "max_latency_ms": 5000,
            "max_estimated_cost_usd": 0.02,
        },
        {"latency_ms": 1200, "estimated_cost_usd": 0.01, "tool_failures": []},
    )

    assert result["passed"] is True
    assert result["score"] >= 0.95


def test_story_evaluator_flags_safety_structure_and_budget_failures():
    state = {
        "child_profile": {
            "age": 6,
            "interests": ["space", "soccer"],
            "favorite_characters": ["friendly robot"],
            "topics_to_avoid": ["violence"],
        },
        "selected_theme": "kindness",
        "story_title": "A Rough Day",
        "story_text": "Maya saw violence in space.",
        "story_summary": "",
        "characters": ["Maya"],
        "setting": "space",
        "parent_note": "Be kind.",
        "recent_stories": [],
    }

    result = evaluate_story_state(
        state,
        {
            "target_theme": "kindness",
            "target_moral": "kindness helps friends feel included",
            "must_avoid": ["violence"],
            "word_count_range": [30, 80],
            "max_latency_ms": 1000,
            "max_estimated_cost_usd": 0.01,
        },
        {
            "latency_ms": 2000,
            "estimated_cost_usd": 0.02,
            "tool_failures": ["image_generation"],
        },
    )

    assert result["passed"] is False
    assert "output_structure_valid" in result["failed_metrics"]
    assert "child_safe_content" in result["failed_metrics"]
    assert "latency_within_budget" in result["failed_metrics"]
    assert "estimated_cost_within_budget" in result["failed_metrics"]
    assert "tool_steps_succeeded" in result["failed_metrics"]


def test_estimate_cost_from_usage_uses_total_tokens():
    assert estimate_cost_from_usage(
        {"total_tokens": 2500},
        cost_per_1k_tokens_usd=0.002,
    ) == 0.005


def test_summarize_evaluation_results_clusters_failures_and_cost():
    summary = summarize_evaluation_results(
        [
            {
                "category": "happy_path",
                "failed_metrics": [],
                "latency_ms": 1000,
                "estimated_cost_usd": 0.001,
                "total_tokens": 1000,
            },
            {
                "category": "safety",
                "failed_metrics": ["child_safe_content", "moral_alignment"],
                "latency_ms": 2000,
                "estimated_cost_usd": 0.002,
                "total_tokens": 2000,
            },
            {
                "category": "safety",
                "failed_metrics": ["child_safe_content"],
                "latency_ms": 3000,
                "estimated_cost_usd": 0.003,
                "total_tokens": 3000,
            },
        ]
    )

    assert summary["case_count"] == 3
    assert summary["pass_rate"] == 0.333
    assert summary["dominant_failure_mode"] == "child_safe_content"
    assert summary["dominant_failure_count"] == 2
    assert summary["failed_estimated_cost_usd"] == 0.005
    assert summary["failed_tokens"] == 5000
