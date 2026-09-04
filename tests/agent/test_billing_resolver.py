"""Slurm MCP 计费握手测试（issue #927）。

覆盖：无 Desktop 通道 fail-closed / 决议放行与阻止 / 超时 / 作业 ID
回传 / 非 slurm 服务器不受影响 / 注入参数不传给 MCP 服务端。
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from miqi.agent.billing_resolver import (
    billing_charge_emitter_for,
    is_slurm_server,
    pending_session_for_charge,
    request_charge,
    resolve_charge,
    set_billing_charge_emitter,
)
from miqi.agent.tools.mcp import MCPToolWrapper, _extract_job_id


@pytest.fixture(autouse=True)
def _clean_emitters():
    """每个测试后清理会话发射器，避免跨测试串扰。"""
    yield
    for key in list(billing_charge_emitter_for.__globals__["_emitters"].keys()):
        set_billing_charge_emitter(key, None)


class _FakeMCPResult:
    def __init__(self, text: str):
        from mcp import types

        self.content = [types.TextContent(type="text", text=text)]


class _FakeSession:
    """记录调用参数的假 MCP session。"""

    def __init__(self, result_text: str = "ok"):
        self._result = result_text
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call_tool(self, name: str, arguments: dict[str, Any], **extra):
        self.calls.append((name, dict(arguments)))
        return _FakeMCPResult(self._result)


def _make_wrapper(server_name: str, session: _FakeSession, tool_name: str = "submit_job"):
    return MCPToolWrapper(
        session,
        server_name,
        SimpleNamespace(name=tool_name, description="submit a job", inputSchema=None),
    )


class TestServerMatching:
    def test_slurm_names_match(self):
        assert is_slurm_server("slurm")
        assert is_slurm_server("my-slurm-cluster")
        assert is_slurm_server("SLURM-PROD")

    def test_other_servers_do_not_match(self):
        assert not is_slurm_server("filesystem")
        assert not is_slurm_server("")


class TestResolver:
    async def test_no_emitter_blocks_with_channel_error(self):
        decision = await request_charge(
            session_key="desktop:unknown",
            payload={"charge_id": "c1", "server_name": "slurm", "tool_name": "submit"},
        )
        assert decision["ok"] is False
        assert decision["code"] == "NO_DESKTOP_CHANNEL"
        assert "作业未提交" in decision["message"]

    async def test_resolve_allows_and_blocks(self):
        emitted: list[dict] = []
        set_billing_charge_emitter("desktop:s1", emitted.append)

        # 放行
        task = asyncio.create_task(
            request_charge(
                session_key="desktop:s1",
                payload={"charge_id": "c-allow", "server_name": "slurm", "tool_name": "submit"},
            )
        )
        await asyncio.sleep(0.05)
        assert emitted and emitted[0]["charge_id"] == "c-allow"
        assert emitted[0]["session_key"] == "desktop:s1"
        assert resolve_charge("c-allow", {"ok": True, "balance": 850})
        decision = await task
        assert decision == {"ok": True, "balance": 850}

        # 阻止（余额不足）
        task = asyncio.create_task(
            request_charge(
                session_key="desktop:s1",
                payload={"charge_id": "c-deny", "server_name": "slurm", "tool_name": "submit"},
            )
        )
        await asyncio.sleep(0.05)
        assert resolve_charge("c-deny", {"ok": False, "code": "insufficient", "message": "余额不足"})
        decision = await task
        assert decision["ok"] is False
        assert decision["code"] == "insufficient"

    async def test_resolve_unknown_charge_returns_false(self):
        assert resolve_charge("nope", {"ok": True}) is False

    async def test_pending_session_tracking(self):
        set_billing_charge_emitter("desktop:s2", lambda p: None)
        task = asyncio.create_task(
            request_charge(
                session_key="desktop:s2",
                payload={"charge_id": "c-sess", "server_name": "slurm", "tool_name": "submit"},
            )
        )
        await asyncio.sleep(0.05)
        assert pending_session_for_charge("c-sess") == "desktop:s2"
        resolve_charge("c-sess", {"ok": True})
        await task
        assert pending_session_for_charge("c-sess") is None

    async def test_timeout_fails_closed(self, monkeypatch):
        monkeypatch.setattr("miqi.agent.billing_resolver.CHARGE_RESOLVE_TIMEOUT_S", 0.2)
        set_billing_charge_emitter("desktop:s3", lambda p: None)  # 不决议
        decision = await request_charge(
            session_key="desktop:s3",
            payload={"charge_id": "c-timeout", "server_name": "slurm", "tool_name": "submit"},
        )
        assert decision["ok"] is False
        assert decision["code"] == "CHARGE_TIMEOUT"


class TestMCPWrapper:
    async def test_slurm_charge_allowed_executes_and_enriches(self):
        session = _FakeSession(result_text="Submitted batch job 12345")
        wrapper = _make_wrapper("slurm", session)
        emitted: list[dict] = []

        async def _auto_allow(payload):
            emitted.append(payload)
            resolve_charge(payload["charge_id"], {"ok": True, "balance": 850})

        set_billing_charge_emitter("desktop:s1", _auto_allow)

        output = await wrapper.execute(
            _session_key="desktop:s1",
            _turn_id="turn-1",
            _tool_call_id="call-1",
            script="run.sh",
        )
        assert output == "Submitted batch job 12345"
        # 注入参数不传给 MCP 服务端
        assert session.calls == [("submit_job", {"script": "run.sh"})]
        # 扣费请求 + 作业 ID 回传各一次
        requests = [e for e in emitted if "job_id" not in e]
        enriches = [e for e in emitted if "job_id" in e]
        assert len(requests) == 1
        assert requests[0]["tool_name"] == "submit_job"
        assert "run.sh" in requests[0]["args_summary"]
        assert enriches and enriches[0]["job_id"] == "12345"
        assert enriches[0]["charge_id"] == requests[0]["charge_id"]

    async def test_slurm_charge_denied_blocks_call(self):
        session = _FakeSession()
        wrapper = _make_wrapper("slurm", session)

        async def _auto_deny(payload):
            resolve_charge(payload["charge_id"], {
                "ok": False, "code": "insufficient",
                "message": "积分不足：本次作业需要 10 积分，当前可用 3 积分",
            })

        set_billing_charge_emitter("desktop:s1", _auto_deny)
        output = await wrapper.execute(
            _session_key="desktop:s1", _turn_id="t", _tool_call_id="c", script="run.sh"
        )
        assert "[计费阻止]" in output
        assert "积分不足" in output
        assert session.calls == []  # MCP 未被调用，作业未提交

    async def test_non_slurm_server_skips_charge(self):
        session = _FakeSession(result_text="done")
        wrapper = _make_wrapper("filesystem", session)
        set_billing_charge_emitter("desktop:s1", lambda p: pytest.fail("不应发起计费"))
        output = await wrapper.execute(
            _session_key="desktop:s1", _turn_id="t", _tool_call_id="c", path="/tmp"
        )
        assert output == "done"
        assert session.calls == [("submit_job", {"path": "/tmp"})]

    async def test_missing_channel_blocks_slurm_call(self):
        # 无 emitter（headless）→ fail-closed，不执行 MCP
        session = _FakeSession()
        wrapper = _make_wrapper("slurm", session)
        output = await wrapper.execute(_session_key="desktop:no-channel")
        assert "[计费阻止]" in output
        assert session.calls == []

    async def test_job_id_extraction(self):
        assert _extract_job_id("Submitted batch job 9999") == "9999"
        assert _extract_job_id("JobId=7788 queued") == "7788"
        assert _extract_job_id("no job here") is None
