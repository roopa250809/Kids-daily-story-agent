import os
from typing import Any, Dict

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP


load_dotenv(override=True)

mcp = FastMCP(
    "openai-image-mcp",
    host=os.getenv("OPENAI_IMAGE_MCP_HOST", "127.0.0.1"),
    port=int(os.getenv("OPENAI_IMAGE_MCP_PORT", "3001")),
    streamable_http_path="/mcp",
)


def _call_openai_images(payload: Dict[str, Any]) -> Dict[str, Any]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {"status": "failed", "reason": "OPENAI_API_KEY is not configured."}

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    response = httpx.post(
        "https://api.openai.com/v1/images/generations",
        headers=headers,
        json=payload,
        timeout=90,
    )

    response.raise_for_status()
    return response.json()


@mcp.tool()
def generate_image(
    prompt: str,
    title: str = "",
    model: str = "",
    size: str = "",
    quality: str = "",
) -> Dict[str, Any]:
    """Generate one child-safe story illustration with OpenAI Images API."""
    payload = {
        "model": model or os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2"),
        "prompt": prompt,
        "size": size or os.getenv("OPENAI_IMAGE_SIZE", "1024x1024"),
        "quality": quality or os.getenv("OPENAI_IMAGE_QUALITY", "low"),
        "n": 1,
    }
    result = _call_openai_images(payload)
    if result.get("status") == "failed":
        return result

    first = (result.get("data") or [{}])[0]
    return {
        "status": "generated",
        "title": title,
        "model": payload["model"],
        "size": payload["size"],
        "quality": payload["quality"],
        "image_base64": first.get("b64_json", ""),
        "image_url": first.get("url", ""),
        "source": "local_openai_image_mcp",
    }


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
