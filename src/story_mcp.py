import os
from typing import Any, Dict, List, Optional


GMAIL_APPROVAL_QUERY_TEMPLATE = (
    'subject:"Story approval" "{story_id}" newer_than:2d'
)


async def load_remote_mcp_tools() -> List[Any]:
    """
    Load tools from an existing remote MCP server.

    This project does not create an MCP server. If STORY_AGENT_MCP_URL is set,
    the agent can call tools exposed by that server, such as Google's Gmail MCP
    tools: search_threads and get_thread.
    """
    server_url = os.getenv("STORY_AGENT_MCP_URL")
    if not server_url:
        return []

    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient
    except ImportError as exc:
        raise RuntimeError(
            "Install langchain-mcp-adapters to call remote MCP tools."
        ) from exc

    client = MultiServerMCPClient(
        {
            "gmail": {
                "transport": "http",
                "url": server_url,
            }
        }
    )
    return await client.get_tools()


async def call_mcp_tool(tool_name: str, payload: Dict[str, Any]) -> Any:
    tools = await load_remote_mcp_tools()
    matching = [tool for tool in tools if tool.name.endswith(tool_name) or tool.name == tool_name]
    if not matching:
        available = ", ".join(tool.name for tool in tools) or "none"
        raise RuntimeError(f"MCP tool '{tool_name}' not found. Available tools: {available}")
    return await matching[0].ainvoke(payload)


async def check_gmail_mcp_for_parent_decision(story_id: str) -> Optional[Dict[str, str]]:
    """
    Optional Gmail MCP approval reader.

    Expected parent reply examples:
    APPROVE story-20260614120000
    REVISE story-20260614120000 Make it shorter and include soccer.
    REJECT story-20260614120000
    """
    if not os.getenv("STORY_AGENT_MCP_URL"):
        return None

    query = GMAIL_APPROVAL_QUERY_TEMPLATE.format(story_id=story_id)
    search_result = await call_mcp_tool("search_threads", {"query": query})

    threads = search_result if isinstance(search_result, list) else search_result.get("threads", [])
    if not threads:
        return None

    thread_id = threads[0].get("id") or threads[0].get("thread_id")
    if not thread_id:
        return None

    thread = await call_mcp_tool("get_thread", {"thread_id": thread_id})
    thread_text = str(thread)
    upper_text = thread_text.upper()

    if "APPROVE" in upper_text:
        return {"decision": "approve", "feedback": "", "source": "gmail_mcp"}
    if "REVISE" in upper_text:
        feedback = thread_text.split("REVISE", 1)[-1].strip()
        return {"decision": "revise", "feedback": feedback, "source": "gmail_mcp"}
    if "REJECT" in upper_text:
        return {"decision": "reject", "feedback": "", "source": "gmail_mcp"}
    return None
