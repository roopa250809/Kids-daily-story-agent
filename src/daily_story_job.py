import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.story_agent import generate_and_send_daily_story
from src.story_storage import (
    get_daily_delivery_record,
    load_child_profile,
    save_daily_delivery_record,
)


LOCAL_TZ = ZoneInfo(os.getenv("STORY_AGENT_TIMEZONE", "America/Chicago"))


def _today_key() -> str:
    return datetime.now(LOCAL_TZ).date().isoformat()


def run_daily_story(child_id: str, theme: str = "", force: bool = False) -> dict:
    date_key = _today_key()
    existing = get_daily_delivery_record(child_id, date_key)
    if existing and not force:
        return {
            "status": "skipped",
            "reason": f"Daily story already handled for {date_key}.",
            "existing_status": existing.get("status"),
            "story_id": existing.get("story_id"),
            "date": date_key,
        }

    profile = load_child_profile(child_id)
    state = generate_and_send_daily_story(child_id, selected_theme=theme or None)
    email_result = state.get("email_result", {})
    record = save_daily_delivery_record(
        {
            "child_id": child_id,
            "date": date_key,
            "preferred_story_time": profile.get("preferred_story_time", "8:30 PM"),
            "status": state.get("status", "unknown"),
            "email_status": state.get("email_status", "unknown"),
            "story_id": state.get("story_id", ""),
            "story_title": state.get("story_title", ""),
            "theme": state.get("selected_theme", ""),
            "message": email_result.get("message", ""),
        }
    )
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate and email the daily child story.")
    parser.add_argument("--child-id", default="demo-child")
    parser.add_argument("--theme", default="")
    parser.add_argument("--force", action="store_true", help="Send even if today's job already ran.")
    args = parser.parse_args()

    result = run_daily_story(args.child_id, theme=args.theme, force=args.force)
    print(json.dumps(result, indent=2))

    if result.get("status") in {"email_failed", "failed"}:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
