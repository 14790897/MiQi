"""MCP client: connects to MCP servers and wraps their tools for runtime use."""

import asyncio
from contextlib import AsyncExitStack
from typing import Any

import httpx
from loguru import logger

from featherflow.agent.tools.base import Tool
from featherflow.agent.tools.registry import ToolRegistry


class MCPToolWrapper(Tool):
    """Wrap a single MCP server tool as a native runtime Tool."""

    def __init__(self, session, server_name: str, tool_def, tool_timeout: int = 30):
        self._session = session
        self._original_name = tool_def.name
        self._name = f"mcp_{server_name}_{tool_def.name}"
        self._description = tool_def.description or tool_def.name
        self._parameters = tool_def.inputSchema or {"type": "object", "properties": {}}
        self._tool_timeout = tool_timeout

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> dict[str, Any]:
        return self._parameters

    async def execute(self, *, _on_progress=None, **kwargs: Any) -> str:
        from mcp import types

        # The mcp SDK calls progress_callback as:
        #   await progress_callback(progress: float, total: float | None)
        # SDK handles progressToken generation internally.
        progress_callback = None
        if _on_progress:
            async def progress_callback(progress: float, total: float | None) -> None:
                await _on_progress(progress, total or 0)

        try:
            result = await asyncio.wait_for(
                self._session.call_tool(
                    self._original_name,
                    arguments=kwargs,
                    progress_callback=progress_callback,
                ),
                timeout=self._tool_timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "MCP tool '{}' timed out after {}s", self._name, self._tool_timeout
            )
            return f"(MCP tool call timed out after {self._tool_timeout}s)"

        parts = []
        for block in result.content:
            if isinstance(block, types.TextContent):
                parts.append(block.text)
            else:
                parts.append(str(block))
        return "\n".join(parts) or "(no output)"


async def _connect_one_server(
    name: str, cfg, registry: ToolRegistry
) -> AsyncExitStack | None:
    """Connect a single MCP server in an isolated context.

    Returns the server's AsyncExitStack on success (caller must keep it alive)
    or None on failure (stack is already closed).

    Running each server in its own asyncio.Task (via gather) ensures that anyio
    cancel-scopes inside the MCP/httpx transports cannot leak into sibling
    connections or the parent task.
    """
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    server_stack = AsyncExitStack()
    await server_stack.__aenter__()

    try:
        if cfg.command:
            params = StdioServerParameters(
                command=cfg.command, args=cfg.args, env=cfg.env or None
            )
            read, write = await server_stack.enter_async_context(stdio_client(params))
        elif cfg.url:
            from mcp.client.streamable_http import streamable_http_client

            http_client = (
                httpx.AsyncClient(headers=cfg.headers, follow_redirects=True)
                if cfg.headers
                else None
            )
            read, write, _ = await server_stack.enter_async_context(
                streamable_http_client(cfg.url, http_client=http_client)
            )
        else:
            logger.warning("MCP server '{}': no command or url configured, skipping", name)
            await server_stack.aclose()
            return None

        session = await server_stack.enter_async_context(ClientSession(read, write))
        await session.initialize()

        tools = await session.list_tools()
        for tool_def in tools.tools:
            wrapper = MCPToolWrapper(session, name, tool_def, tool_timeout=cfg.tool_timeout)
            registry.register(wrapper)
            logger.debug("MCP: registered tool '{}' from server '{}'", wrapper.name, name)

        logger.info("MCP server '{}': connected, {} tools registered", name, len(tools.tools))
        return server_stack  # caller keeps it alive

    except BaseException as e:
        logger.error("MCP server '{}': failed to connect: {}", name, e)
        try:
            await server_stack.aclose()
        except Exception:
            pass
        return None


async def connect_mcp_servers(
    mcp_servers: dict, registry: ToolRegistry, stack: AsyncExitStack
) -> None:
    """Connect to configured MCP servers and register their tools.

    Each server connection runs in its own asyncio.Task so that anyio
    cancel-scopes (used internally by the MCP SDK / httpx) are fully
    isolated.  A failure in one server cannot cancel siblings or the caller.
    """

    async def _task(name: str, cfg):
        return await _connect_one_server(name, cfg, registry)

    tasks = {
        name: asyncio.create_task(_task(name, cfg))
        for name, cfg in mcp_servers.items()
    }

    results = await asyncio.gather(*tasks.values(), return_exceptions=True)

    for name, result in zip(tasks, results):
        if isinstance(result, BaseException):
            logger.error("MCP server '{}': task failed: {}", name, result)
        elif isinstance(result, AsyncExitStack):
            # Transfer cleanup responsibility to the shared stack
            stack.push_async_callback(result.aclose)
