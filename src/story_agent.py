import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TypedDict

try:
    from src.config import (
        ANTHROPIC_API_KEY,
        LLM_MODEL,
        LLM_PROVIDER,
        NEBIUS_API_KEY,
        NEBIUS_BASE_URL,
    )
except ImportError:
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "nebius").lower()
    LLM_MODEL = os.getenv("LLM_MODEL", "Qwen/Qwen3-30B-A3B")
    NEBIUS_API_KEY = os.getenv("NEBIUS_API_KEY")
    NEBIUS_BASE_URL = os.getenv("NEBIUS_BASE_URL", "https://api.studio.nebius.com/v1")
from src.story_email import format_story_email, format_story_email_html, send_story_email
from src.story_image import build_illustration_prompt, generate_openai_image
from src.story_memory import format_mem0_memories, remember_child_fact, search_child_memory
from src.story_pdf import create_story_pdf
from src.story_audio import generate_story_audio
from src.story_storage import (
    find_similar_stories,
    get_recent_stories,
    load_child_profile,
    save_story_history,
)
from src.story_tracing import traceable


SENSITIVE_TOPICS = {
    "bullying",
    "grief",
    "illness",
    "anxiety",
    "family conflict",
    "discipline",
    "body image",
    "religion",
    "violence",
    "fear",
    "abuse",
    "nudity"
}

THEME_POOL = [
    "kindness",
    "confidence",
    "patience",
    "sharing",
    "bedtime routine",
    "trying again",
    "school courage",
    "screen-time balance",
    "listening",
    "gratitude",
]

CHARACTER_INSPIRATION_MAP = {
    "elsa": "snow princess",
}


class StoryAgentState(TypedDict, total=False):
    child_id: str
    child_profile: Dict[str, Any]
    recent_stories: List[Dict[str, Any]]
    mem0_memories: List[Dict[str, Any]]
    selected_theme: str
    story_id: str
    story_title: str
    story_text: str
    story_summary: str
    characters: List[str]
    setting: str
    parent_note: str
    validation_passed: bool
    validation_issues: List[str]
    repetition_result: Dict[str, Any]
    approval_required: bool
    approval_reason: str
    parent_decision: str
    parent_feedback: str
    retry_count: int
    email_status: str
    email_result: Dict[str, Any]
    include_audio: bool
    audio_status: str
    audio_path: str
    audio_result: Dict[str, Any]
    illustration_prompt: str
    illustration_url: str
    illustration_path: str
    illustration_status: str
    illustration_error: str
    illustration_result: Dict[str, Any]
    story_pdf_path: str
    generation_source: str
    generation_error: str
    graph_thread_id: str
    approval_payload: Dict[str, Any]
    status: str
    errors: List[str]
    llm_usage: Dict[str, Any]
    llm_model: str


_story_llm: Optional[Any] = None


def _get_llm() -> Optional[Any]:
    global _story_llm
    if not ANTHROPIC_API_KEY:
        return None
    try:
        from langchain_anthropic import ChatAnthropic
    except ImportError:
        return None
    if _story_llm is None:
        _story_llm = ChatAnthropic(
            model=LLM_MODEL,
            api_key=ANTHROPIC_API_KEY,
            temperature=0.7,
            max_tokens=1200,
        )
    return _story_llm


@traceable(
    name="nebius_story_chat_completion",
    run_type="llm",
    metadata={"provider": "nebius", "component": "story_generation"},
)
def _call_nebius(system: str, user: Dict[str, Any]) -> Dict[str, Any]:
    if not NEBIUS_API_KEY:
        raise RuntimeError("NEBIUS_API_KEY is not configured.")

    import httpx

    response = httpx.post(
        f"{NEBIUS_BASE_URL.rstrip('/')}/chat/completions",
        headers={
            "Authorization": f"Bearer {NEBIUS_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": LLM_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, indent=2)},
            ],
            "temperature": 0.7,
            "max_tokens": 1200,
            "response_format": {"type": "json_object"},
        },
        timeout=45,
    )
    response.raise_for_status()
    payload = response.json()
    content = payload["choices"][0]["message"]["content"]
    parsed = _extract_json(content)
    parsed["_llm_usage"] = payload.get("usage", {})
    parsed["_llm_model"] = payload.get("model", LLM_MODEL)
    return parsed


@traceable(
    name="anthropic_story_chat_completion",
    run_type="llm",
    metadata={"provider": "anthropic", "component": "story_generation"},
)
def _call_anthropic(system: str, user: Dict[str, Any]) -> Dict[str, Any]:
    llm = _get_llm()
    if not llm:
        raise RuntimeError("Anthropic LLM is not configured.")

    from langchain_core.messages import HumanMessage, SystemMessage

    response = llm.invoke(
        [
            SystemMessage(content=system),
            HumanMessage(content=json.dumps(user, indent=2)),
        ]
    )
    payload = _extract_json(response.content)
    usage = getattr(response, "usage_metadata", None) or getattr(response, "response_metadata", {}).get("usage", {})
    payload["_llm_usage"] = usage or {}
    payload["_llm_model"] = LLM_MODEL
    return payload


def _extract_json(text: str) -> Dict[str, Any]:
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError("LLM response did not contain JSON.")
    return json.loads(match.group(0))


def _fallback_story(profile: Dict[str, Any], theme: str, error: str = "") -> Dict[str, Any]:
    child_name = profile.get("child_name", "your child")
    interest = (profile.get("interests") or ["stars"])[0]
    favorite_character = _story_safe_character_type((profile.get("favorite_characters") or ["gentle helper"])[0])
    pronouns = _pronouns_for_gender(profile.get("gender", "prefer not to say"))
    title = f"{child_name} and the Little Lesson in {theme.title()}"
    story = (
        f"{child_name} found a tiny map tucked beside a favorite {interest}. "
        f"A {favorite_character} waved from the first bend in the path. "
        f"The map led to a bright garden where every path needed a little {theme}. "
        f"When a friend felt unsure, {child_name} paused, listened, and helped one "
        f"small step at a time. By bedtime, the garden lights glowed softly, and "
        f"{child_name} felt proud of choosing care over rushing. "
        f"That night, {pronouns['subject']} smiled softly and felt ready for rest."
    )
    return {
        "title": title,
        "story": story,
        "summary": f"{child_name} practices {theme} while helping a friend.",
        "characters": [child_name, str(favorite_character)],
        "setting": "a bright garden",
        "parent_note": f"Tonight's story gently reinforces {theme}.",
        "_generation_source": "local_fallback",
        "_generation_error": error,
    }


@traceable(
    name="generate_story_payload",
    run_type="chain",
    metadata={"component": "story_agent", "stage": "draft_or_revision"},
)
def _generate_story_payload(state: StoryAgentState, revision: bool = False) -> Dict[str, Any]:
    profile = state["child_profile"]
    theme = state["selected_theme"]
    favorite_character_types = _story_safe_favorite_character_types(profile)
    age = int(profile.get("age") or 6)
    word_budget = "70-140 words" if age <= 3 else "80-160 words" if age < 5 else "120-240 words"
    interests = [str(interest) for interest in profile.get("interests", []) if str(interest).strip()]
    avoided_topics = sorted(
        {
            *(str(topic).lower() for topic in profile.get("topics_to_avoid", []) if str(topic).strip()),
            *SENSITIVE_TOPICS,
        }
    )
    recent_summaries = [
        {
            "title": s.get("story_title") or s.get("title"),
            "theme": s.get("theme"),
            "summary": s.get("story_summary") or s.get("summary"),
            "characters": s.get("characters", []),
            "setting": s.get("setting"),
        }
        for s in state.get("recent_stories", [])[:5]
    ]
    feedback = state.get("parent_feedback", "")
    mem0_memory_text = format_mem0_memories(state.get("mem0_memories", []))

    system = """Act as a Montessori specialist. You write safe, warm, age-appropriate children's stories.
Return only valid JSON with these keys:
title, story, summary, characters, setting, parent_note.
Avoid scary, violent, shaming, medical, or manipulative content.
Make the lesson gentle, not preachy.
Keep the selected theme explicit in the story, summary, or parent_note."""

    user = {
        "child_profile": profile,
        "theme": theme,
        "recent_stories_to_avoid_repeating": recent_summaries,
        "long_term_child_memories": mem0_memory_text,
        "revision_feedback": feedback if revision else "",
        "requirements": [
            f"Write a short bedtime story within this word budget: {word_budget}.",
            "Use simple language appropriate for the child's age and reading level.",
            "Include every child interest exactly enough that a checker can find the words in the title, setting, characters, summary, parent_note, or story events.",
            f"Child interests that must appear: {', '.join(interests)}.",
            "Include at least one favorite character type as a visible character or story helper.",
            "If a favorite is a specific copyrighted character, do not use the exact name; use the story-safe character type instead.",
            f"Story-safe favorite character types to include: {', '.join(favorite_character_types)}.",
            f"Selected theme to make explicit: {theme}.",
            "State the gentle lesson in parent_note using plain words from the selected theme and story action.",
            f"Do not use these avoided words or topics anywhere: {', '.join(avoided_topics)}.",
            "Do not repeat recent plots, settings, story titles, or character combinations; change at least one major element when recent stories exist.",
            "Use long_term_child_memories when they are relevant, but do not mention private memory details directly.",
        ],
    }

    try:
        if LLM_PROVIDER == "nebius":
            payload = _call_nebius(system, user)
            return {**payload, "_generation_source": "nebius", "_generation_error": ""}

        if not _get_llm():
            return _fallback_story(profile, theme, "No configured LLM provider was available.")
        payload = _call_anthropic(system, user)
        return {**payload, "_generation_source": LLM_PROVIDER, "_generation_error": ""}
    except Exception as exc:
        return _fallback_story(profile, theme, f"{type(exc).__name__}: provider call failed.")


def _story_word_count(story_text: str) -> int:
    return len(re.findall(r"\b\w+\b", story_text))


def _token_set(value: Any) -> set:
    if isinstance(value, list):
        value = " ".join(str(item) for item in value)
    return set(re.findall(r"[a-z0-9]+", str(value).lower()))


def _story_safe_character_type(character: Any) -> str:
    text = str(character).strip()
    if not text:
        return ""
    return CHARACTER_INSPIRATION_MAP.get(text.lower(), text)


def _story_safe_favorite_character_types(profile: Dict[str, Any]) -> List[str]:
    safe_types = [
        _story_safe_character_type(character)
        for character in profile.get("favorite_characters", [])
    ]
    return [character for character in safe_types if character]


def _pronouns_for_gender(gender: Any) -> Dict[str, str]:
    normalized = str(gender or "").strip().lower()
    if normalized == "girl":
        return {"subject": "she", "object": "her", "possessive": "her"}
    if normalized == "boy":
        return {"subject": "he", "object": "him", "possessive": "his"}
    return {"subject": "they", "object": "them", "possessive": "their"}


def story_uses_child_interest(state: StoryAgentState) -> Dict[str, Any]:
    interests = [
        str(interest).strip()
        for interest in state.get("child_profile", {}).get("interests", [])
        if str(interest).strip()
    ]
    if not interests:
        return {"uses_interest": True, "matched_interests": []}

    story_blob = " ".join(
        [
            state.get("story_title", ""),
            state.get("story_summary", ""),
            state.get("story_text", ""),
            " ".join(state.get("characters", [])),
            state.get("setting", ""),
        ]
    ).lower()
    story_tokens = _token_set(story_blob)
    matched = []
    missing = []
    for interest in interests:
        interest_text = interest.lower()
        interest_tokens = _token_set(interest_text)
        if interest_text in story_blob or story_tokens.intersection(interest_tokens):
            matched.append(interest)
        else:
            missing.append(interest)

    return {
        "uses_interest": not missing,
        "matched_interests": matched,
        "missing_interests": missing,
    }


def story_uses_favorite_character_type(state: StoryAgentState) -> Dict[str, Any]:
    favorite_characters = _story_safe_favorite_character_types(state.get("child_profile", {}))
    if not favorite_characters:
        return {"uses_favorite_character": True, "matched_favorite_characters": []}

    story_blob = " ".join(
        [
            state.get("story_title", ""),
            state.get("story_summary", ""),
            state.get("story_text", ""),
            " ".join(state.get("characters", [])),
            state.get("setting", ""),
        ]
    ).lower()
    story_tokens = _token_set(story_blob)

    matched = []
    for character in favorite_characters:
        character_text = character.lower()
        character_tokens = _token_set(character_text)
        if character_text in story_blob or story_tokens.intersection(character_tokens):
            matched.append(character)

    return {
        "uses_favorite_character": bool(matched),
        "matched_favorite_characters": matched,
        "favorite_characters": favorite_characters,
    }


def check_story_repetition(
    *,
    theme: str,
    characters: List[str],
    setting: str,
    summary: str,
    recent_stories: List[Dict[str, Any]],
) -> Dict[str, Any]:
    current = _token_set([theme, *characters, setting, summary])
    for story in recent_stories:
        previous = _token_set(
            [
                story.get("theme", ""),
                *(story.get("characters") or []),
                story.get("setting", ""),
                story.get("story_summary") or story.get("summary", ""),
            ]
        )
        if not previous:
            continue
        overlap = len(current & previous) / max(len(current | previous), 1)
        same_theme = theme.lower() == str(story.get("theme", "")).lower()
        if overlap >= 0.42 or same_theme and overlap >= 0.25:
            return {
                "is_repetitive": True,
                "reason": f"Similar to recent story '{story.get('story_title') or story.get('title')}'.",
                "similarity": round(overlap, 2),
                "similar_story_id": story.get("story_id"),
            }
    return {"is_repetitive": False, "reason": "", "similarity": 0.0}


def check_pinecone_story_repetition(state: StoryAgentState) -> Dict[str, Any]:
    candidate = {
        "story_id": state.get("story_id", ""),
        "story_title": state.get("story_title", ""),
        "theme": state.get("selected_theme", ""),
        "characters": state.get("characters", []),
        "setting": state.get("setting", ""),
        "story_summary": state.get("story_summary", ""),
    }
    matches = find_similar_stories(state["child_id"], candidate, limit=3)
    if not matches:
        return {"is_repetitive": False, "reason": "", "similarity": 0.0}

    top = matches[0]
    score = float(top.get("similarity_score") or 0.0)
    if score >= 0.85:
        return {
            "is_repetitive": True,
            "reason": f"Similar to Pinecone story '{top.get('story_title')}'.",
            "similarity": round(score, 2),
            "similar_story_id": top.get("story_id"),
        }
    return {
        "is_repetitive": False,
        "reason": "",
        "similarity": round(score, 2),
        "similar_story_id": top.get("story_id"),
    }


def _validate_story(state: StoryAgentState) -> Dict[str, Any]:
    profile = state["child_profile"]
    story_text = state.get("story_text", "")
    story_blob = " ".join(
        [
            state.get("story_title", ""),
            state.get("story_summary", ""),
            story_text,
            state.get("selected_theme", ""),
        ]
    ).lower()

    issues = []
    word_count = _story_word_count(story_text)
    age = int(profile.get("age") or 6)
    max_words = 170 if age <= 5 else 260
    min_words = 80 if age <= 5 else 120

    if word_count < min_words:
        issues.append(f"Story is short for age {age}: {word_count} words.")
    if word_count > max_words:
        issues.append(f"Story is long for age {age}: {word_count} words.")

    avoided = [topic for topic in profile.get("topics_to_avoid", []) if str(topic).lower() in story_blob]
    if avoided:
        issues.append(f"Story mentions avoided topic(s): {', '.join(avoided)}.")

    interest_result = story_uses_child_interest(state)
    if not interest_result["uses_interest"]:
        missing_interests = ", ".join(interest_result.get("missing_interests", []))
        issues.append(f"Story must include these child interest(s): {missing_interests}.")

    favorite_character_result = story_uses_favorite_character_type(state)
    if not favorite_character_result["uses_favorite_character"]:
        favorite_character_types = ", ".join(favorite_character_result.get("favorite_characters", []))
        issues.append(f"Story should include at least one favorite character type: {favorite_character_types}.")

    sensitive_hits = sorted(topic for topic in SENSITIVE_TOPICS if topic in story_blob)
    repetition = check_pinecone_story_repetition(state)
    if not repetition["is_repetitive"]:
        repetition = check_story_repetition(
            theme=state.get("selected_theme", ""),
            characters=state.get("characters", []),
            setting=state.get("setting", ""),
            summary=state.get("story_summary", ""),
            recent_stories=state.get("recent_stories", []),
        )
    if repetition["is_repetitive"]:
        issues.append(repetition["reason"])

    approval_required = bool(sensitive_hits)
    approval_reason = (
        f"Sensitive topic detected: {', '.join(sensitive_hits)}"
        if sensitive_hits
        else "Parent approval required before sending."
    )

    return {
        "validation_passed": not issues,
        "validation_issues": issues,
        "repetition_result": repetition,
        "approval_required": approval_required,
        "approval_reason": approval_reason,
    }


@traceable(name="load_child_profile_node", run_type="chain", metadata={"component": "story_graph"})
def load_profile_node(state: StoryAgentState) -> Dict[str, Any]:
    child_id = state.get("child_id") or "demo-child"
    return {"child_id": child_id, "child_profile": load_child_profile(child_id)}


@traceable(name="load_story_history_node", run_type="chain", metadata={"component": "story_graph"})
def load_history_node(state: StoryAgentState) -> Dict[str, Any]:
    return {"recent_stories": get_recent_stories(state["child_id"], limit=10)}


@traceable(name="load_mem0_memory_node", run_type="chain", metadata={"component": "story_graph"})
def load_mem0_memory_node(state: StoryAgentState) -> Dict[str, Any]:
    query = (
        "child story preferences, favorite character types, favorite themes, "
        "parent feedback, reading level, story length, topics to avoid"
    )
    return {"mem0_memories": search_child_memory(state["child_id"], query, limit=5)}


@traceable(name="choose_theme_node", run_type="chain", metadata={"component": "story_graph"})
def choose_theme_node(state: StoryAgentState) -> Dict[str, Any]:
    profile = state["child_profile"]
    requested_theme = state.get("selected_theme")
    if requested_theme:
        return {"selected_theme": requested_theme}

    recent_themes = {
        str(story.get("theme", "")).lower()
        for story in state.get("recent_stories", [])[:7]
    }
    candidates = list(dict.fromkeys(profile.get("parent_goals", []) + THEME_POOL))
    for theme in candidates:
        if str(theme).lower() not in recent_themes:
            return {"selected_theme": str(theme)}
    day_index = datetime.now().timetuple().tm_yday % len(THEME_POOL)
    return {"selected_theme": THEME_POOL[day_index]}


@traceable(name="generate_story_node", run_type="chain", metadata={"component": "story_graph"})
def generate_story_node(state: StoryAgentState) -> Dict[str, Any]:
    payload = _generate_story_payload(state)
    story_id = state.get("story_id") or f"story-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    return {
        "story_id": story_id,
        "story_title": str(payload.get("title", "Today's Story")),
        "story_text": str(payload.get("story", "")),
        "story_summary": str(payload.get("summary", "")),
        "characters": list(payload.get("characters", [])),
        "setting": str(payload.get("setting", "")),
        "parent_note": str(payload.get("parent_note", "")),
        "generation_source": str(payload.get("_generation_source", "unknown")),
        "generation_error": str(payload.get("_generation_error", "")),
        "llm_usage": payload.get("_llm_usage", {}),
        "llm_model": str(payload.get("_llm_model", LLM_MODEL)),
        "status": "draft_generated",
    }


@traceable(name="revise_story_node", run_type="chain", metadata={"component": "story_graph"})
def revise_story_node(state: StoryAgentState) -> Dict[str, Any]:
    retry_count = state.get("retry_count", 0) + 1
    feedback_parts = []
    if state.get("parent_feedback"):
        feedback_parts.append(state["parent_feedback"])
    if state.get("validation_issues"):
        feedback_parts.append("Fix validation issues: " + "; ".join(state["validation_issues"]))
    revised_state = {**state, "parent_feedback": " ".join(feedback_parts), "retry_count": retry_count}
    payload = _generate_story_payload(revised_state, revision=True)
    return {
        "story_title": str(payload.get("title", "Today's Story")),
        "story_text": str(payload.get("story", "")),
        "story_summary": str(payload.get("summary", "")),
        "characters": list(payload.get("characters", [])),
        "setting": str(payload.get("setting", "")),
        "parent_note": str(payload.get("parent_note", "")),
        "generation_source": str(payload.get("_generation_source", "unknown")),
        "generation_error": str(payload.get("_generation_error", "")),
        "llm_usage": payload.get("_llm_usage", {}),
        "llm_model": str(payload.get("_llm_model", LLM_MODEL)),
        "retry_count": retry_count,
        "status": "draft_revised",
    }


@traceable(name="validate_story_node", run_type="chain", metadata={"component": "story_graph"})
def validate_story_node(state: StoryAgentState) -> Dict[str, Any]:
    return _validate_story(state)


def route_after_validation(state: StoryAgentState) -> str:
    if not state.get("validation_passed") and state.get("retry_count", 0) < 2:
        return "revise"
    return "approval"


@traceable(name="approval_pending_node", run_type="chain", metadata={"component": "story_graph"})
def approval_pending_node(state: StoryAgentState) -> Dict[str, Any]:
    if state.get("validation_passed"):
        reason = "Story passed validation and is ready for parent approval."
    else:
        reason = "Validation needs parent review: " + "; ".join(state.get("validation_issues", []))
    return {
        "status": "awaiting_parent_approval",
        "approval_required": True,
        "approval_reason": state.get("approval_reason") or reason,
    }


@traceable(name="human_review_interrupt_node", run_type="chain", metadata={"component": "story_graph"})
def human_review_interrupt_node(state: StoryAgentState) -> Dict[str, Any]:
    from langgraph.types import interrupt

    review_payload = {
        "story_id": state.get("story_id"),
        "story_title": state.get("story_title"),
        "theme": state.get("selected_theme"),
        "approval_reason": state.get("approval_reason"),
        "validation_issues": state.get("validation_issues", []),
        "allowed_decisions": ["approve", "revise", "reject"],
    }
    decision_payload = interrupt(review_payload)
    if isinstance(decision_payload, str):
        decision_payload = {"decision": decision_payload, "feedback": ""}

    decision = str(decision_payload.get("decision", "reject")).lower()
    feedback = str(decision_payload.get("feedback", ""))
    include_audio = bool(decision_payload.get("include_audio", False))
    return {
        "parent_decision": decision,
        "parent_feedback": feedback,
        "include_audio": include_audio,
        "approval_payload": review_payload,
        "status": "parent_decision_received",
    }


def route_parent_decision(state: StoryAgentState) -> str:
    decision = state.get("parent_decision", "").lower()
    if decision == "approve":
        return "send"
    if decision == "revise":
        return "revise"
    return "reject"


@traceable(name="parent_review_node", run_type="chain", metadata={"component": "story_graph"})
def parent_review_node(state: StoryAgentState) -> Dict[str, Any]:
    return {"status": "parent_decision_received"}


@traceable(name="reject_story_node", run_type="chain", metadata={"component": "story_graph"})
def reject_story_node(state: StoryAgentState) -> Dict[str, Any]:
    return {
        "status": "rejected_by_parent",
        "email_status": "not_sent",
    }


@traceable(name="generate_illustration_node", run_type="chain", metadata={"component": "story_graph"})
def generate_illustration_node(state: StoryAgentState) -> Dict[str, Any]:
    prompt = build_illustration_prompt(state)
    result = generate_openai_image(
        prompt,
        state.get("story_title", "Today's Story"),
        state.get("story_id", ""),
    )
    return {
        "illustration_prompt": prompt,
        "illustration_url": result.get("image_url", ""),
        "illustration_path": result.get("image_path", ""),
        "illustration_status": result.get("status", "unknown"),
        "illustration_error": result.get("reason") or result.get("error", ""),
        "illustration_result": result,
        "status": "illustration_checked",
    }


@traceable(name="send_email_node", run_type="chain", metadata={"component": "story_graph"})
def send_email_node(state: StoryAgentState) -> Dict[str, Any]:
    profile = state["child_profile"]
    subject = f"Today's Story: {state['story_title']}"
    body = format_story_email(
        child_name=profile.get("child_name", "your child"),
        title=state["story_title"],
        theme=state["selected_theme"],
        story_text=state["story_text"],
        parent_note=state.get("parent_note"),
    )
    html_body = format_story_email_html(
        child_name=profile.get("child_name", "your child"),
        title=state["story_title"],
        theme=state["selected_theme"],
        story_text=state["story_text"],
        parent_note=state.get("parent_note"),
        illustration_url=state.get("illustration_url"),
        illustration_cid="story-illustration" if state.get("illustration_path") else None,
    )
    story_pdf_path = create_story_pdf(
        child_name=profile.get("child_name", "your child"),
        title=state["story_title"],
        theme=state["selected_theme"],
        story_text=state["story_text"],
        parent_note=state.get("parent_note"),
        story_id=state["story_id"],
        illustration_path=state.get("illustration_path"),
    )
    attachment_paths = [story_pdf_path]
    audio_result: Dict[str, Any] = {"status": "not_requested", "audio_path": ""}
    if state.get("include_audio"):
        audio_result = generate_story_audio(
            title=state["story_title"],
            story_text=state["story_text"],
            parent_note=state.get("parent_note", ""),
            story_id=state["story_id"],
        )
        if audio_result.get("audio_path"):
            attachment_paths.append(audio_result["audio_path"])
        else:
            return {
                "email_result": {
                    "status": "blocked_missing_audio",
                    "message": "Email was not sent because audio narration was requested but no MP3 was generated.",
                    "story_id": state["story_id"],
                    "audio_status": audio_result.get("status", "unknown"),
                    "audio_error": audio_result.get("reason", ""),
                },
                "email_status": "not_sent",
                "story_pdf_path": story_pdf_path,
                "audio_result": audio_result,
                "audio_status": audio_result.get("status", "unknown"),
                "audio_path": "",
                "status": "email_failed",
            }
    result = send_story_email(
        to_email=profile.get("parent_email", ""),
        subject=subject,
        body=body,
        html_body=html_body,
        inline_image_path=state.get("illustration_path"),
        attachment_paths=attachment_paths,
        story_id=state["story_id"],
        approved=state.get("parent_decision") == "approve",
    )
    result = {
        **result,
        "audio_status": audio_result.get("status", "unknown"),
        "audio_path": audio_result.get("audio_path", ""),
        "audio_error": audio_result.get("reason", ""),
    }
    if result.get("status") in {"sent", "mock_sent"}:
        from src.story_storage import log_email_status

        log_email_status(
            {
                "status": "send_details",
                "message": "Post-send attachment and audio details.",
                "story_id": state["story_id"],
                "audio_status": result["audio_status"],
                "audio_path": result["audio_path"],
                "audio_error": result["audio_error"],
                "attachments": result.get("attachments", ""),
                "attachment_names": result.get("attachment_names", ""),
                "attachment_count": result.get("attachment_count", ""),
            }
        )
    return {
        "email_result": result,
        "email_status": result["status"],
        "story_pdf_path": story_pdf_path,
        "audio_result": audio_result,
        "audio_status": audio_result.get("status", "unknown"),
        "audio_path": audio_result.get("audio_path", ""),
        "status": "email_sent" if result["status"] in {"sent", "mock_sent"} else "email_failed",
    }


@traceable(name="save_history_node", run_type="chain", metadata={"component": "story_graph"})
def save_history_node(state: StoryAgentState) -> Dict[str, Any]:
    mem0_saved = remember_child_fact(
        state["child_id"],
        (
            f"Story sent for child_id {state['child_id']}: theme '{state['selected_theme']}', "
            f"title '{state['story_title']}', characters {', '.join(state.get('characters', []))}, "
            f"setting '{state.get('setting', '')}'. Parent note: {state.get('parent_note', '')}"
        ),
    )
    record = save_story_history(
        state["child_id"],
        {
            "story_id": state["story_id"],
            "story_title": state["story_title"],
            "theme": state["selected_theme"],
            "characters": state.get("characters", []),
            "setting": state.get("setting", ""),
            "story_summary": state.get("story_summary", ""),
            "story_text": state["story_text"],
            "story_pdf_path": state.get("story_pdf_path", ""),
            "audio_path": state.get("audio_path", ""),
            "audio_status": state.get("audio_status", ""),
            "parent_note": state.get("parent_note", ""),
            "illustration_prompt": state.get("illustration_prompt", ""),
            "illustration_url": state.get("illustration_url", ""),
            "illustration_path": state.get("illustration_path", ""),
            "illustration_status": state.get("illustration_status", ""),
            "email_status": state.get("email_status", "unknown"),
            "mem0_saved": mem0_saved,
        },
    )
    return {"status": "completed", "story_id": record["story_id"]}


_checkpointer: Optional[Any] = None
_story_graph: Optional[Any] = None


def _get_checkpointer():
    global _checkpointer
    if _checkpointer is None:
        from langgraph.checkpoint.memory import MemorySaver

        _checkpointer = MemorySaver()
    return _checkpointer


def _thread_config(thread_id: str) -> Dict[str, Any]:
    return {"configurable": {"thread_id": thread_id}}


def _extract_interrupts(result: Any) -> List[Any]:
    if not isinstance(result, dict):
        return []
    interrupts = result.get("__interrupt__", [])
    if not isinstance(interrupts, list):
        interrupts = list(interrupts)
    return interrupts


def _state_from_checkpoint(graph: Any, thread_id: str, result: Any) -> StoryAgentState:
    state = dict(graph.get_state(_thread_config(thread_id)).values or {})
    state["graph_thread_id"] = thread_id
    interrupts = _extract_interrupts(result)
    if interrupts:
        interrupt_value = getattr(interrupts[0], "value", None)
        if interrupt_value is None and isinstance(interrupts[0], dict):
            interrupt_value = interrupts[0].get("value")
        state["approval_payload"] = interrupt_value or {}
        state["status"] = "awaiting_parent_approval"
    return state


def build_story_graph():
    global _story_graph
    if _story_graph is not None:
        return _story_graph

    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(StoryAgentState)
    graph.add_node("load_profile", load_profile_node)
    graph.add_node("load_mem0_memory", load_mem0_memory_node)
    graph.add_node("load_history", load_history_node)
    graph.add_node("choose_theme", choose_theme_node)
    graph.add_node("generate_story", generate_story_node)
    graph.add_node("validate_story", validate_story_node)
    graph.add_node("revise_story", revise_story_node)
    graph.add_node("approval_pending", approval_pending_node)
    graph.add_node("human_review", human_review_interrupt_node)
    graph.add_node("generate_illustration", generate_illustration_node)
    graph.add_node("send_email", send_email_node)
    graph.add_node("save_history", save_history_node)
    graph.add_node("reject_story", reject_story_node)

    graph.add_edge(START, "load_profile")
    graph.add_edge("load_profile", "load_mem0_memory")
    graph.add_edge("load_mem0_memory", "load_history")
    graph.add_edge("load_history", "choose_theme")
    graph.add_edge("choose_theme", "generate_story")
    graph.add_edge("generate_story", "validate_story")
    graph.add_conditional_edges(
        "validate_story",
        route_after_validation,
        {"revise": "revise_story", "approval": "approval_pending"},
    )
    graph.add_edge("revise_story", "validate_story")
    graph.add_edge("approval_pending", "human_review")
    graph.add_conditional_edges(
        "human_review",
        route_parent_decision,
        {"send": "generate_illustration", "revise": "revise_story", "reject": "reject_story"},
    )
    graph.add_edge("generate_illustration", "send_email")
    graph.add_edge("send_email", "save_history")
    graph.add_edge("save_history", END)
    graph.add_edge("reject_story", END)

    _story_graph = graph.compile(checkpointer=_get_checkpointer())
    return _story_graph


def build_draft_graph():
    return build_story_graph()


def build_review_graph():
    return build_story_graph()


@traceable(name="generate_story_draft", run_type="chain", metadata={"component": "story_agent", "workflow": "draft"})
def generate_story_draft(child_id: str = "demo-child", selected_theme: Optional[str] = None) -> StoryAgentState:
    thread_id = f"story-{uuid.uuid4().hex}"
    initial: StoryAgentState = {"child_id": child_id, "retry_count": 0, "graph_thread_id": thread_id}
    if selected_theme:
        initial["selected_theme"] = selected_theme
    graph = build_story_graph()
    result = graph.invoke(initial, _thread_config(thread_id))
    return _state_from_checkpoint(graph, thread_id, result)


@traceable(name="apply_parent_decision", run_type="chain", metadata={"component": "story_agent", "workflow": "resume"})
def apply_parent_decision(
    state: StoryAgentState,
    decision: str,
    feedback: str = "",
    include_audio: bool = False,
) -> StoryAgentState:
    from langgraph.types import Command

    thread_id = state.get("graph_thread_id")
    if not thread_id:
        raise ValueError("Missing graph_thread_id; cannot resume checkpointed graph.")

    graph = build_story_graph()
    resume_payload = {"decision": decision.lower(), "feedback": feedback, "include_audio": include_audio}
    result = graph.invoke(Command(resume=resume_payload), _thread_config(thread_id))
    final_state = _state_from_checkpoint(graph, thread_id, result)
    final_state["graph_thread_id"] = thread_id
    return final_state


@traceable(name="send_approved_story_now", run_type="chain", metadata={"component": "story_agent", "workflow": "approve_send"})
def send_approved_story_now(
    state: StoryAgentState,
    include_audio: bool = False,
) -> StoryAgentState:
    approved_state: StoryAgentState = {
        **state,
        "parent_decision": "approve",
        "include_audio": include_audio,
        "status": "parent_decision_received",
    }
    if not (approved_state.get("illustration_path") or approved_state.get("illustration_url")):
        approved_state = {**approved_state, **generate_illustration_node(approved_state)}
    if not (approved_state.get("illustration_path") or approved_state.get("illustration_url")):
        reason = approved_state.get("illustration_error") or "A story illustration is required before sending."
        return {
            **approved_state,
            "email_status": "not_sent",
            "email_result": {
                "status": "blocked_missing_image",
                "message": f"Email was not sent because image generation did not produce an illustration: {reason}",
                "story_id": approved_state.get("story_id", ""),
            },
            "status": "email_failed",
        }
    email_state = send_email_node(approved_state)
    final_state: StoryAgentState = {**approved_state, **email_state}
    if final_state.get("email_status") in {"sent", "mock_sent"}:
        final_state = {**final_state, **save_history_node(final_state)}
    return final_state


@traceable(name="generate_and_send_daily_story", run_type="chain", metadata={"component": "story_agent", "workflow": "daily_send"})
def generate_and_send_daily_story(
    child_id: str = "demo-child",
    selected_theme: Optional[str] = None,
) -> StoryAgentState:
    draft_state = generate_story_draft(child_id, selected_theme=selected_theme)
    final_state = apply_parent_decision(draft_state, "approve")
    final_state["scheduled_send"] = True
    return final_state
