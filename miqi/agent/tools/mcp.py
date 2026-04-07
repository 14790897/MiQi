"""MCP client: connects to MCP servers and wraps their tools for runtime use."""

import asyncio
from contextlib import AsyncExitStack
from typing import Any

import httpx
from loguru import logger

from miqi.agent.tools.base import Tool
from miqi.agent.tools.registry import ToolRegistry


class MCPToolWrapper(Tool):
    """Wrap a single MCP server tool as a native runtime Tool."""

    def __init__(self, session, server_name: str, tool_def, tool_timeout: int = 30,
                 progress_interval: int = 15):
        self._session = session
        self._server_name = server_name
        self._original_name = tool_def.name
        self._name = f"mcp_{server_name}_{tool_def.name}"
        self._description = tool_def.description or tool_def.name
        self._parameters = tool_def.inputSchema or {"type": "object", "properties": {}}
        self._tool_timeout = tool_timeout
        self._progress_interval = progress_interval

    @property
    def execution_timeout(self) -> float | None:
        """Expose per-MCP-server toolTimeout so ToolRegistry defers to us."""
        # Return a value slightly larger than our own internal wait_for so
        # the outer wrapper never fires before the inner one does.
        return float(self._tool_timeout) + 5

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
        #   await progress_callback(progress_token, progress, total)
        # (SDK added progress_token as the first arg in a recent version)
        progress_callback = None
        if _on_progress:
            async def progress_callback(progress_token: Any, progress: float, total: float | None) -> None:
                await _on_progress(progress, total or 0)

        # Heartbeat: periodically notify the user that a long-running
        # MCP tool is still executing, even if the server sends no
        # progress events.
        heartbeat_task: asyncio.Task | None = None
        if _on_progress and self._progress_interval > 0:
            async def _heartbeat():
                elapsed = 0
                try:
                    while True:
                        await asyncio.sleep(self._progress_interval)
                        elapsed += self._progress_interval
                        await _on_progress(
                            elapsed,
                            0,  # total unknown
                            heartbeat=True,
                        )
                except asyncio.CancelledError:
                    pass
            heartbeat_task = asyncio.create_task(_heartbeat())

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
        finally:
            if heartbeat_task:
                heartbeat_task.cancel()
                try:
                    await heartbeat_task
                except asyncio.CancelledError:
                    pass

        parts = []
        for block in result.content:
            if isinstance(block, types.TextContent):
                parts.append(block.text)
            else:
                parts.append(str(block))
        return "\n".join(parts) or "(no output)"


class MCPGatewayTool(Tool):
    """Entry-point tool for a lazy-loaded MCP server.

    Instead of registering all tools upfront (which inflates the tool list
    sent to the LLM on every call), a single gateway tool per server is
    registered.  When the LLM selects the gateway, all real tools for that
    server are injected into the ToolRegistry for the remainder of the
    current agent-loop run.  After the run completes, ``deactivate()`` is
    called to unregister them, returning to the compact tool list.

    This keeps the per-call tool-definition token cost at ~18 tools
    (12 built-ins + N gateway stubs) instead of 90+.
    """

    def __init__(
        self,
        server_name: str,
        wrappers: list,  # list[MCPToolWrapper]
        registry: ToolRegistry,
        gateway_description: str = "",
    ):
        self._server_name = server_name
        self._wrappers = wrappers
        self._registry = registry
        self._gateway_description = gateway_description
        self._active = False

    @property
    def name(self) -> str:
        return f"use_{self._server_name}"

    @property
    def description(self) -> str:
        base = self._gateway_description or f"激活 {self._server_name} 工具集"
        sample = ", ".join(w._original_name for w in self._wrappers[:6])
        if len(self._wrappers) > 6:
            sample += "..."
        return (
            f"{base}。"
            f"共 {len(self._wrappers)} 个工具（如 {sample}）。"
            "调用此工具并描述你的任务，即可激活该工具集，之后可直接调用其中的具体工具。"
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "需要完成的任务描述，用于激活后的上下文提示",
                }
            },
            "required": ["task"],
        }

    async def execute(self, task: str = "", **kwargs) -> str:  # type: ignore[override]
        """Activate: register all real tools into the shared registry."""
        if not self._active:
            for wrapper in self._wrappers:
                self._registry.register(wrapper)
            self._active = True
            logger.info(
                "MCPGateway: activated '{}' ({} tools loaded)",
                self._server_name, len(self._wrappers),
            )
        tool_lines = "\n".join(
            f"- {w.name}: {(w.description or '')[:80]}"
            for w in self._wrappers
        )
        return (
            f"{self._server_name} 工具集已激活，共 {len(self._wrappers)} 个工具：\n\n"
            f"{tool_lines}\n\n"
            f"任务：{task}\n"
            "请直接调用上述工具完成任务。"
        )

    def deactivate(self) -> None:
        """Unregister all real tools; call after each agent-loop run."""
        if self._active:
            for wrapper in self._wrappers:
                self._registry.unregister(wrapper.name)
            self._active = False
            logger.debug("MCPGateway: deactivated '{}'", self._server_name)

    @property
    def is_active(self) -> bool:
        return self._active


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
        progress_interval = getattr(cfg, "progress_interval_seconds", 15)
        wrappers = [
            MCPToolWrapper(
                session, name, tool_def,
                tool_timeout=cfg.tool_timeout,
                progress_interval=progress_interval,
            )
            for tool_def in tools.tools
        ]

        lazy = getattr(cfg, "lazy", False)
        if lazy:
            # Register a single gateway entry-point tool; real tools are
            # injected into the registry on demand when the gateway executes.
            gateway_desc = getattr(cfg, "description", "") or ""
            gateway = MCPGatewayTool(name, wrappers, registry, gateway_desc)
            registry.register(gateway)
            logger.info(
                "MCP server '{}': connected, {} tools ready (lazy gateway registered)",
                name, len(wrappers),
            )
        else:
            for wrapper in wrappers:
                registry.register(wrapper)
                logger.debug("MCP: registered tool '{}' from server '{}'", wrapper.name, name)
            logger.info("MCP server '{}': connected, {} tools registered", name, len(wrappers))

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
