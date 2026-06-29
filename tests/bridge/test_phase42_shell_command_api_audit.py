"""Phase 42 audit tests for Codex-style thread/shellCommand."""

from __future__ import annotations

from pathlib import Path

import pytest


class _CaptureSend:
    def __init__(self):
        self.messages: list[dict] = []

    def send(self, data: dict) -> None:
        self.messages.append(data)


def _dispatch_legacy(_req_id: str, _method: str, _params: dict) -> None:
    pass


@pytest.mark.asyncio
async def test_phase42_thread_shell_command_registered():
    from miqi.bridge.loop import BridgeRuntimeLoop

    loop = BridgeRuntimeLoop(
        send_func=_CaptureSend().send,
        dispatch_legacy_func=_dispatch_legacy,
    )
    await loop._init_app_server()
    assert "thread/shellCommand" in loop.app_server._methods
    await loop.app_server.stop()


def test_phase42_new_runtime_modules_do_not_import_bridge_server():
    paths = [
        Path("miqi/runtime/shell_command_app_handlers.py"),
    ]
    for path in paths:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        assert "import miqi.bridge.server" not in text
        assert "from miqi.bridge" not in text


def test_phase42_run_user_shell_command_not_reserved_in_task_runner():
    text = Path("miqi/runtime/task_runner.py").read_text(encoding="utf-8")
    assert "RunUserShellCommand, UserInputAnswer" not in text
    assert "is reserved for future use" in text
    assert "RunUserShellCommand is reserved for future use" not in text


def test_phase42_no_registry_execute_bypass_for_user_shell_command():
    text = Path("miqi/runtime/task_runner.py").read_text(encoding="utf-8")
    assert ".tools.execute(" not in text
    assert "tool_runtime.execute_one" in text
