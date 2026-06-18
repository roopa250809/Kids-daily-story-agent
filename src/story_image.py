import asyncio
import base64
import json
import mimetypes
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


IMAGE_DIR = Path(__file__).resolve().parent.parent / "data" / "generated_images"


def build_illustration_prompt(state: Dict[str, Any]) -> str:
    profile = state.get("child_profile", {})
    story_title = state.get("story_title", "Today's Story")
    child_age = profile.get("age", 6)
    gender = str(profile.get("gender", "prefer not to say")).strip().lower()
    interests = ", ".join(profile.get("interests", [])[:4])
    avoided_topics = ", ".join(profile.get("topics_to_avoid", [])[:4])
    characters = ", ".join(state.get("characters", [])[:4])
    gender_instruction = ""
    if gender in {"girl", "boy"}:
        gender_instruction = (
            f"If the child appears in the scene, depict the child as a {gender} around age {child_age}. "
        )
    else:
        gender_instruction = "If the child appears in the scene, keep the child visually gender-neutral. "

    return (
        "Create a warm, child-safe storybook illustration for a personalized children's story. "
        f"Story title: {story_title}. "
        f"Theme: {state.get('selected_theme', '')}. "
        f"Setting: {state.get('setting', '')}. "
        f"Characters: {characters}. "
        f"Child age: {child_age}. "
        f"Child gender: {gender}. "
        f"{gender_instruction}"
        f"Child interests to gently include: {interests}. "
        f"Avoid: {avoided_topics}. "
        "Style: cozy bedtime picture book, soft colors, friendly expressions, no text in the image, "
        "no scary imagery, no violence, no copyrighted characters."
    )


def _find_url(value: Any) -> Optional[str]:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
        return _find_url(parsed)
    if isinstance(value, dict):
        for key in ("image_url", "url", "preview_url", "output_url"):
            item = value.get(key)
            if isinstance(item, str) and item.startswith(("http://", "https://")):
                if "/v1/images/generations" not in item:
                    return item
        for item in value.values():
            found = _find_url(item)
            if found:
                return found
    if isinstance(value, list):
        for item in value:
            found = _find_url(item)
            if found:
                return found
    return None


def _find_base64(value: Any) -> Optional[str]:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return value if len(value) > 1000 and re.fullmatch(r"[A-Za-z0-9+/=\s]+", value) else None
        return _find_base64(parsed)
    if isinstance(value, dict):
        for key in ("b64_json", "image_base64", "base64", "result"):
            item = value.get(key)
            if isinstance(item, str) and len(item) > 100:
                return item
        for item in value.values():
            found = _find_base64(item)
            if found:
                return found
    if isinstance(value, list):
        for item in value:
            found = _find_base64(item)
            if found:
                return found
    return None


def _save_image_base64(image_base64: str, story_id: str) -> str:
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    safe_story_id = re.sub(r"[^a-zA-Z0-9_.-]+", "-", story_id or "story")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    path = IMAGE_DIR / f"{safe_story_id}-{stamp}.png"
    path.write_bytes(base64.b64decode(image_base64))
    return str(path)


def _save_image_url(image_url: str, story_id: str) -> str:
    import httpx

    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    safe_story_id = re.sub(r"[^a-zA-Z0-9_.-]+", "-", story_id or "story")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    path = IMAGE_DIR / f"{safe_story_id}-{stamp}.png"
    response = httpx.get(image_url, timeout=60)
    response.raise_for_status()
    path.write_bytes(response.content)
    return str(path)


async def _generate_image_mcp_async(prompt: str, title: str, story_id: str) -> Dict[str, Any]:
    server_url = os.getenv("OPENAI_IMAGE_MCP_URL")
    if not server_url:
        return {"status": "skipped", "reason": "OPENAI_IMAGE_MCP_URL is not configured."}

    from langchain_mcp_adapters.client import MultiServerMCPClient

    transport = os.getenv("OPENAI_IMAGE_MCP_TRANSPORT", "streamable_http")
    tool_name = os.getenv("OPENAI_IMAGE_MCP_TOOL_NAME", "generate_image")
    client = MultiServerMCPClient(
        {
            "openai_image": {
                "transport": transport,
                "url": server_url,
            }
        }
    )
    tools = await client.get_tools()
    matching_tools = [
        tool for tool in tools
        if tool.name == tool_name or tool.name.endswith(tool_name)
    ]
    if not matching_tools:
        return {
            "status": "failed",
            "reason": f"OpenAI image MCP tool '{tool_name}' was not found.",
            "available_tools": [tool.name for tool in tools],
        }

    result = await matching_tools[0].ainvoke(
        {
            "prompt": prompt,
            "title": title,
            "model": os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2"),
            "size": os.getenv("OPENAI_IMAGE_SIZE", "1024x1024"),
            "quality": os.getenv("OPENAI_IMAGE_QUALITY", "low"),
        }
    )
    image_url = _find_url(result) or ""
    image_base64 = _find_base64(result)
    image_path = ""
    if image_base64:
        image_path = _save_image_base64(image_base64, story_id)
    elif image_url:
        image_path = _save_image_url(image_url, story_id)
    return {
        "status": "generated" if image_url or image_path else "generated_without_image",
        "image_url": image_url,
        "image_path": image_path,
        "raw_result": result,
        "source": "openai_image_mcp",
    }


def _generate_image_api(prompt: str, story_id: str) -> Dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {
            "status": "skipped",
            "reason": "OPENAI_API_KEY is not configured and no OpenAI Image MCP URL was set.",
        }

    import httpx

    payload = {
        "model": os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2"),
        "prompt": prompt,
        "size": os.getenv("OPENAI_IMAGE_SIZE", "1024x1024"),
        "quality": os.getenv("OPENAI_IMAGE_QUALITY", "low"),
        "n": 1,
    }
    response = httpx.post(
        "https://api.openai.com/v1/images/generations",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=90,
    )
    response.raise_for_status()
    result = response.json()
    image_base64 = _find_base64(result)
    image_url = _find_url(result) or ""
    image_path = ""
    if image_base64:
        image_path = _save_image_base64(image_base64, story_id)
    elif image_url:
        image_path = _save_image_url(image_url, story_id)
    return {
        "status": "generated" if image_url or image_path else "generated_without_image",
        "image_url": image_url,
        "image_path": image_path,
        "raw_result": {"model": payload["model"], "size": payload["size"], "quality": payload["quality"]},
        "source": "openai_images_api",
    }


def generate_openai_image(prompt: str, title: str, story_id: str) -> Dict[str, Any]:
    mcp_url = os.getenv("OPENAI_IMAGE_MCP_URL")
    api_key = os.getenv("OPENAI_API_KEY")
    mcp_result: Optional[Dict[str, Any]] = None

    if mcp_url:
        try:
            mcp_result = asyncio.run(_generate_image_mcp_async(prompt, title, story_id))
            if mcp_result.get("status") == "generated" and (
                mcp_result.get("image_url") or mcp_result.get("image_path")
            ):
                return mcp_result
        except Exception as exc:
            mcp_result = {
                "status": "failed",
                "reason": "OpenAI image MCP generation failed.",
                "error": str(exc),
                "image_url": "",
                "image_path": "",
                "source": "openai_image_mcp",
            }

    if api_key:
        try:
            api_result = _generate_image_api(prompt, story_id)
            if mcp_result:
                api_result["mcp_fallback_reason"] = (
                    mcp_result.get("error")
                    or mcp_result.get("reason")
                    or f"MCP returned status {mcp_result.get('status', 'unknown')}."
                )
            return api_result
        except Exception as exc:
            return {
                "status": "failed",
                "reason": "OpenAI image generation failed.",
                "error": str(exc),
                "image_url": "",
                "image_path": "",
                "mcp_result": mcp_result or {},
            }

    if mcp_result:
        return mcp_result

    return {
        "status": "skipped",
        "reason": "OPENAI_API_KEY is not configured and no OpenAI Image MCP URL was set.",
        "image_url": "",
        "image_path": "",
    }


def image_mime_parts(path: str) -> tuple[str, str]:
    mime_type, _ = mimetypes.guess_type(path)
    if not mime_type:
        return "image", "png"
    maintype, subtype = mime_type.split("/", 1)
    return maintype, subtype
