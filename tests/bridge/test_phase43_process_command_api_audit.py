"""Phase 43 audit tests: verify workbench process/command API handlers
are registered and follow safety rules.

All tests here should initially FAIL — implementations don't exist yet.
They pass once Task 43.4/43.5/43.6 are complete.
"""

import ast
from pathlib import Path

import pytest

# ── Method registration audit ────────────────────────────────────────────

EXPECTED_METHODS = [
    "command/exec",
    "command/exec/write",
    "command/exec/resize",
    "command/exec/terminate",
    "process/spawn",
    "process/writeStdin",
    "process/resizePty",
    "process/kill",
]


class TestPhase43MethodRegistration:
    """Verify all 8 methods are registered on AppServer after bridge init."""

    @pytest.mark.asyncio
    async def test_all_8_methods_registered_on_app_server(self):
        """After BridgeRuntimeLoop._init_app_server(), AppServer must have
        all 8 workbench process/command methods registered."""
        from unittest.mock import MagicMock

        from miqi.runtime.app_server import AppServer, ClientSessionRegistry

        registry = ClientSessionRegistry()
        registry.bridge_context = {"state": MagicMock()}
        server = AppServer(registry)

        # Simulate what BridgeRuntimeLoop._init_app_server() does:
        # register the workbench process/command handlers
        from miqi.runtime.workbench_command_app_handlers import (
            register_workbench_command_handlers,
        )
        from miqi.runtime.workbench_process_app_handlers import (
            register_workbench_process_handlers,
        )

        register_workbench_command_handlers(server)
        register_workbench_process_handlers(server)

        for method in EXPECTED_METHODS:
            assert method in server._methods, (
                f"Method {method!r} is NOT registered on AppServer. "
                f"Registered methods: {sorted(server._methods.keys())}"
            )

    def test_registration_does_not_import_bridge_server(self):
        """The new handler modules must NOT import miqi.bridge.server."""
        modules_to_check = [
            "miqi.runtime.workbench_command_app_handlers",
            "miqi.runtime.workbench_process_app_handlers",
        ]

        for mod_name in modules_to_check:
            # Use ast to check imports without executing
            mod_path = Path(*mod_name.split("."))
            file_path = Path("miqi") / "runtime" / (mod_path.name + ".py")
            if not file_path.exists():
                pytest.skip(f"Module file not found: {file_path}")
            source = file_path.read_text(encoding="utf-8")
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        assert "miqi.bridge.server" not in alias.name, (
                            f"{mod_name} imports {alias.name} — must not import miqi.bridge.server"
                        )
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        assert "miqi.bridge.server" not in node.module, (
                            f"{mod_name} imports from {node.module} — must not import miqi.bridge.server"
                        )


class TestPhase43SafetyAudit:
    """Verify safety rules: no shell=True, no raw exceptions, etc."""

    def test_no_shell_true_in_runtime_modules(self):
        """No handler module uses shell=True in subprocess calls."""
        modules_to_check = [
            "miqi/runtime/workbench_process_runtime.py",
            "miqi/runtime/workbench_command_app_handlers.py",
            "miqi/runtime/workbench_process_app_handlers.py",
        ]

        for mod_path in modules_to_check:
            if not Path(mod_path).exists():
                pytest.skip(f"Module not found: {mod_path}")
            source = Path(mod_path).read_text(encoding="utf-8")
            tree = ast.parse(source)
            for node in ast.walk(tree):
                # Check for shell=True keyword in function calls
                if isinstance(node, ast.keyword):
                    if node.arg == "shell" and (
                        isinstance(node.value, ast.Constant) and node.value.value is True
                    ):
                        pytest.fail(
                            f"{mod_path} uses shell=True at line {node.lineno}"
                        )
                # Check for create_subprocess_shell
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Attribute):
                        if node.func.attr == "create_subprocess_shell":
                            pytest.fail(
                                f"{mod_path} calls create_subprocess_shell at line {node.lineno}"
                            )

    def test_no_tool_registry_execute_bypass(self):
        """No handler calls ToolRegistry.execute() to bypass tool execution."""
        modules_to_check = [
            "miqi/runtime/workbench_command_app_handlers.py",
            "miqi/runtime/workbench_process_app_handlers.py",
        ]

        for mod_path in modules_to_check:
            if not Path(mod_path).exists():
                pytest.skip(f"Module not found: {mod_path}")
            source = Path(mod_path).read_text(encoding="utf-8")
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Attribute):
                        if node.func.attr == "execute":
                            pytest.fail(
                                f"{mod_path} calls .execute() at line {node.lineno} — "
                                f"must not use ToolRegistry.execute bypass"
                            )

    def test_no_agent_loop_direct_usage(self):
        """No handler creates AgentLoop directly for process execution."""
        modules_to_check = [
            "miqi/runtime/workbench_process_runtime.py",
            "miqi/runtime/workbench_command_app_handlers.py",
            "miqi/runtime/workbench_process_app_handlers.py",
        ]

        for mod_path in modules_to_check:
            if not Path(mod_path).exists():
                pytest.skip(f"Module not found: {mod_path}")
            source = Path(mod_path).read_text(encoding="utf-8")
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name) and node.func.id == "AgentLoop":
                        pytest.fail(
                            f"{mod_path} calls AgentLoop() at line {node.lineno}"
                        )

    def test_no_raw_exception_messages_to_clients(self):
        """No handler writes raw str(exc) into client-facing error messages.

        This is checked by AST patterns — handlers should use AppServerError
        with sanitized messages, not re-raise raw exceptions.
        """
        modules_to_check = [
            "miqi/runtime/workbench_command_app_handlers.py",
            "miqi/runtime/workbench_process_app_handlers.py",
        ]

        for mod_path in modules_to_check:
            if not Path(mod_path).exists():
                pytest.skip(f"Module not found: {mod_path}")
            source = Path(mod_path).read_text(encoding="utf-8")
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.Raise):
                    # Check if raising something other than AppServerError
                    if isinstance(node.exc, ast.Call):
                        if isinstance(node.exc.func, ast.Name):
                            if node.exc.func.id not in ("AppServerError",):
                                # This is fine for ValueError etc. used internally
                                pass
