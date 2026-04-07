"""Tool registry for dynamic tool management."""

import asyncio
from typing import Any

from miqi.agent.tools.base import Tool

# Default timeout for individual tool execution (seconds)
DEFAULT_TOOL_TIMEOUT = 120


class ToolRegistry:
    """
    Registry for agent tools.

    Allows dynamic registration and execution of tools.
    """

    def __init__(self, tool_timeout: float = DEFAULT_TOOL_TIMEOUT):
        self._tools: dict[str, Tool] = {}
        self.tool_timeout = tool_timeout

    def register(self, tool: Tool) -> None:
        """Register a tool."""
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        """Unregister a tool by name."""
        self._tools.pop(name, None)

    def get(self, name: str) -> Tool | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def has(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools

    def get_definitions(self) -> list[dict[str, Any]]:
        """Get all tool definitions in OpenAI format."""
        return [tool.to_schema() for tool in self._tools.values()]

    async def execute(self, name: str, params: dict[str, Any], **extra) -> str:
        """
        Execute a tool by name with given parameters.

        Args:
            name: Tool name.
            params: Tool parameters.
            **extra: Extra keyword arguments forwarded to tool.execute()
                     (e.g. ``_on_progress`` for MCP progress callbacks).

        Returns:
            Tool execution result as string.

        Raises:
            KeyError: If tool not found.
        """
        hint = "\n\n[Analyze the error above and try a different approach.]"

        tool = self._tools.get(name)
        if not tool:
            return f"Error: Tool '{name}' not found. Available: {', '.join(self.tool_names)}"

        try:
            errors = tool.validate_params(params)
            if errors:
                return f"Error: Invalid parameters for tool '{name}': " + "; ".join(errors) + hint
            # Per-tool timeout takes priority (e.g. MCPToolWrapper exposes its
            # own configured toolTimeout); fall back to the registry-level default.
            timeout = tool.execution_timeout if tool.execution_timeout is not None else self.tool_timeout
            result = await asyncio.wait_for(
                tool.execute(**params, **extra),
                timeout=timeout,
            )
            if isinstance(result, str) and result.startswith("Error"):
                return result + hint
            return result
        except asyncio.TimeoutError:
            return f"Error: Tool '{name}' timed out after {timeout}s" + hint
        except Exception as e:
            return f"Error executing {name}: {str(e)}" + hint

    @property
    def tool_names(self) -> list[str]:
        """Get list of registered tool names."""
        return list(self._tools.keys())

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
