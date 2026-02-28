"""MCP client: connects to MCP servers and wraps their tools for runtime use."""

import asyncio
import uuid
from contextlib import AsyncExitStack
from typing import Any

import httpx
from loguru import logger

from featherflow.agent.tools.base import Tool
from featherflow.agent.tools.registry import ToolRegistry

# Track active progress callbacks keyed by progress_token string
_progress_callbacks: dict[str, Any] = {}


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

        progress_token = None
        if _on_progress:
            progress_token = str(uuid.uuid4())
            _progress_callbacks[progress_token] = _on_progress

        try:
            result = await asyncio.wait_for(
                self._session.call_tool(
                    self._original_name,
                    arguments=kwargs,
                    progress_token=progress_token,
                ),
                timeout=self._tool_timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("MCP tool '{}' timed out after {}s", self._name, self._tool_timeout)
            return f"(MCP tool call timed out after {self._tool_timeout}s)"
        finally:
            if progress_token:
                _progress_callbacks.pop(progress_token, None)

        parts = []
        for block in result.content:
            if isinstance(block, types.TextContent):
                parts.append(block.text)
            else:
                parts.append(str(block))
        return "\n".join(parts) or "(no output)"


async def _handle_progress_notification(notification) -> None:
    """Handle MCP notifications/progress from servers."""
    token = str(notification.progress_token) if notification.progress_token else None
    if token and token in _progress_callbacks:
        cb = _progress_callbacks[token]
        await cb(notification.progress, notification.total)


async def connect_mcp_servers(
    mcp_servers: dict, registry: ToolRegistry, stack: AsyncExitStack
) -> None:
    """Connect to configured MCP servers and register their tools."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    for name, cfg in mcp_servers.items():
        try:
            if cfg.command:
                params = StdioServerParameters(
                    command=cfg.command, args=cfg.args, env=cfg.env or None
                )
                read, write = await stack.enter_async_context(stdio_client(params))
            elif cfg.url:
                from mcp.client.streamable_http import streamable_http_client
                # Build an httpx client with custom headers if needed.
                # Do NOT enter it as a separate context — streamable_http_client
                # manages its own lifecycle when a client is provided.
                http_client = (
                    httpx.AsyncClient(headers=cfg.headers, follow_redirects=True)
                    if cfg.headers
                    else None
                )
                read, write, _ = await stack.enter_async_context(
                    streamable_http_client(cfg.url, http_client=http_client)
                )
            else:
                logger.warning("MCP server '{}': no command or url configured, skipping", name)
                continue

            try:
                session = await stack.enter_async_context(
                    ClientSession(
                        read, write,
                        progress_notification_handler=_handle_progress_notification,
                    )
                )
            except TypeError:
                logger.debug(
                    "MCP server '{}': SDK does not support progress_notification_handler, "
                    "progress reporting disabled", name
                )
                session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()

            tools = await session.list_tools()
            for tool_def in tools.tools:
                wrapper = MCPToolWrapper(session, name, tool_def, tool_timeout=cfg.tool_timeout)
                registry.register(wrapper)
                logger.debug("MCP: registered tool '{}' from server '{}'", wrapper.name, name)

            logger.info("MCP server '{}': connected, {} tools registered", name, len(tools.tools))
        except Exception as e:
            logger.error("MCP server '{}': failed to connect: {}", name, e)
