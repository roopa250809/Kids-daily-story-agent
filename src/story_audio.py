import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from dotenv import dotenv_values, load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = PROJECT_ROOT / ".env"
AUDIO_DIR = Path(__file__).resolve().parent.parent / "data" / "story_agent" / "story_audio"
DEFAULT_VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"
DEFAULT_MODEL_ID = "eleven_multilingual_v2"


def _safe_filename(value: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value.strip()).strip("-")
    return clean or "story"


def generate_story_audio(
    *,
    title: str,
    story_text: str,
    parent_note: str,
    story_id: str,
) -> Dict[str, Any]:
    load_dotenv(ENV_PATH, override=False)
    api_key = os.getenv("ELEVENLABS_API_KEY", "").strip()
    if not api_key and "PYTEST_CURRENT_TEST" not in os.environ:
        api_key = str(dotenv_values(ENV_PATH).get("ELEVENLABS_API_KEY", "")).strip()
    if not api_key:
        return {
            "status": "skipped",
            "reason": "ELEVENLABS_API_KEY is not configured.",
            "audio_path": "",
        }

    import httpx

    voice_id = os.getenv("ELEVENLABS_VOICE_ID", DEFAULT_VOICE_ID).strip() or DEFAULT_VOICE_ID
    model_id = os.getenv("ELEVENLABS_MODEL_ID", DEFAULT_MODEL_ID).strip() or DEFAULT_MODEL_ID
    output_format = os.getenv("ELEVENLABS_OUTPUT_FORMAT", "mp3_44100_128").strip() or "mp3_44100_128"
    narration = f"{title}.\n\n{story_text}\n\nParent note: {parent_note}".strip()

    try:
        response = httpx.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            headers={
                "xi-api-key": api_key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            params={"output_format": output_format},
            json={
                "text": narration,
                "model_id": model_id,
            },
            timeout=25,
        )
        response.raise_for_status()
    except Exception as exc:
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        response_text = getattr(getattr(exc, "response", None), "text", "")
        reason = str(exc)
        if status_code:
            reason = f"ElevenLabs HTTP {status_code}: {response_text[:500] or reason}"
        return {
            "status": "failed",
            "reason": reason,
            "audio_path": "",
            "voice_id": voice_id,
            "model_id": model_id,
        }

    if not response.content:
        return {
            "status": "failed",
            "reason": "ElevenLabs returned an empty audio file.",
            "audio_path": "",
            "voice_id": voice_id,
            "model_id": model_id,
        }

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    path = AUDIO_DIR / f"{_safe_filename(story_id)}-{stamp}.mp3"
    path.write_bytes(response.content)
    return {
        "status": "generated",
        "audio_path": str(path),
        "voice_id": voice_id,
        "model_id": model_id,
        "output_format": output_format,
    }
