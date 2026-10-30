import asyncio
import os
from pathlib import Path

from mcp import ClientSession
from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client

MCP_SERVER_DIR = Path(
    os.environ.get(
        "FORTYK_MCP_SERVER_DIR",
        str(Path.home() / "40k-mcp-server"),
    )
).expanduser()
MCP_SERVER_ENTRYPOINT = MCP_SERVER_DIR / "build" / "index.js"


def server_parameters() -> StdioServerParameters:
    return StdioServerParameters(
        command=os.environ.get("NODE_BINARY", "node"),
        args=[str(MCP_SERVER_ENTRYPOINT)],
        cwd=str(MCP_SERVER_DIR),
    )


async def call_mcp_tools_batch(tool_requests: list[dict]) -> dict[str, str]:
    """Call multiple 40k MCP tools over one stdio connection."""
    try:
        async with stdio_client(server_parameters()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                async def fetch(request: dict) -> tuple[str, str]:
                    result = await session.call_tool(
                        request["tool"],
                        arguments=request["args"],
                    )
                    text = result.content[0].text if result.content else "No text found."
                    if result.is_error:
                        return request["key"], f"Error from 40k MCP: {text}"
                    return request["key"], text

                responses = await asyncio.gather(
                    *(fetch(request) for request in tool_requests)
                )
                return dict(responses)
    except Exception as error:
        return {"error": f"40k MCP connection failed: {error}"}


async def call_mcp_tool(tool_name: str, arguments: dict) -> str:
    """Call one 40k MCP tool and return its text content."""
    results = await call_mcp_tools_batch(
        [{"key": "result", "tool": tool_name, "args": arguments}]
    )
    if "error" in results:
        return results["error"]
    return results["result"]


async def list_mcp_tools() -> list[str]:
    """Names of the tools the 40k MCP server exposes (for diagnostics)."""
    try:
        async with stdio_client(server_parameters()) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listing = await session.list_tools()
                return sorted(tool.name for tool in listing.tools)
    except Exception as error:
        return [f"40k MCP connection failed: {error}"]
