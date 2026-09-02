"""PointsBilling — 平台积分计费闸门单元测试。

覆盖：未登录放行 / 扣费成功与持久化 / 内存+磁盘去重 / 余额不足阻止 /
token 失效重读恢复 / 网络重试与 fail-closed / 并发只扣一次 / 事件回调。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from miqi.kun_runtime.billing import PointsBilling

COST = 30


def _write_token(tmp_path: Path, *, access: str = "tok-123", base_url: str | None = None) -> Path:
    token_file = tmp_path / ".qraft" / "token.json"
    token_file.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {"accessToken": access, "expiresAt": 4102444800000}
    if base_url is not None:
        payload["baseUrl"] = base_url
    token_file.write_text(json.dumps(payload), encoding="utf-8")
    return token_file


def _ok_response(available: int = 270) -> tuple[int, dict[str, Any]]:
    return 200, {"code": 200, "message": "ok", "data": {"availablePoints": available}}


def _make_billing(
    tmp_path: Path,
    request_fn=None,
    *,
    cost: int = COST,
    on_event=None,
) -> PointsBilling:
    return PointsBilling(
        token_file=tmp_path / ".qraft" / "token.json",
        billed_file=tmp_path / ".qraft" / "billing.json",
        cost=cost,
        request_fn=request_fn,
        on_event=on_event,
    )


class TestNotLoggedIn:
    async def test_no_token_file_allows_without_request(self, tmp_path):
        requests: list[Any] = []

        async def request_fn(url, access_token, body):
            requests.append((url, access_token, body))
            return _ok_response()

        billing = _make_billing(tmp_path, request_fn)
        decision = await billing.ensure_billed("thread-1")
        assert decision.allowed is True
        assert decision.status == "not_logged_in"
        assert requests == []

    async def test_broken_token_file_treated_as_not_logged_in(self, tmp_path):
        token_file = tmp_path / ".qraft" / "token.json"
        token_file.parent.mkdir(parents=True)
        token_file.write_text("{not json", encoding="utf-8")
        billing = _make_billing(tmp_path)
        decision = await billing.ensure_billed("thread-1")
        assert decision.allowed is True
        assert decision.status == "not_logged_in"


class TestDeductSuccess:
    async def test_deducts_once_and_persists(self, tmp_path):
        _write_token(tmp_path, base_url="https://test.forge.miqroera.com/api")
        requests: list[Any] = []

        async def request_fn(url, access_token, body):
            requests.append((url, access_token, body))
            return _ok_response(270)

        billing = _make_billing(tmp_path, request_fn)
        decision = await billing.ensure_billed("thread-1", turn_id="turn-9")
        assert decision.allowed is True
        assert decision.status == "billed"
        assert decision.cost == COST
        assert decision.balance_after == 270

        url, access_token, body = requests[0]
        assert url == "https://test.forge.miqroera.com/api/oauth2/points/deduct"
        assert access_token == "tok-123"
        assert body["amount"] == COST
        assert body["source"] == "desktop-agent-task"
        assert body["memo"].startswith("thread:thread-1")

        # 持久化文件记录
        billed = json.loads((tmp_path / ".qraft" / "billing.json").read_text(encoding="utf-8"))
        assert "thread-1" in billed
        assert billed["thread-1"]["cost"] == COST
        assert billed["thread-1"]["balanceAfter"] == 270

    async def test_second_call_same_thread_no_second_request(self, tmp_path):
        _write_token(tmp_path)
        requests: list[Any] = []

        async def request_fn(url, access_token, body):
            requests.append(body)
            return _ok_response()

        billing = _make_billing(tmp_path, request_fn)
        first = await billing.ensure_billed("thread-1")
        second = await billing.ensure_billed("thread-1")
        assert first.status == "billed"
        assert second.allowed is True
        assert second.status == "already_billed"
        assert len(requests) == 1

    async def test_fresh_instance_reuses_disk_marker(self, tmp_path):
        _write_token(tmp_path)
        requests: list[Any] = []

        async def request_fn(url, access_token, body):
            requests.append(body)
            return _ok_response()

        first = _make_billing(tmp_path, request_fn)
        await first.ensure_billed("thread-1")

        # 新实例（模拟应用重启/另一运行时实例）
        second = _make_billing(tmp_path, request_fn)
        decision = await second.ensure_billed("thread-1")
        assert decision.allowed is True
        assert decision.status == "already_billed"
        assert len(requests) == 1

    async def test_concurrent_first_calls_deduct_once(self, tmp_path):
        _write_token(tmp_path)
        requests: list[Any] = []
        started = asyncio.Event()

        async def request_fn(url, access_token, body):
            started.set()
            await asyncio.sleep(0.05)
            requests.append(body)
            return _ok_response()

        billing = _make_billing(tmp_path, request_fn)
        results = await asyncio.gather(
            billing.ensure_billed("thread-1"),
            billing.ensure_billed("thread-1"),
            billing.ensure_billed("thread-1"),
        )
        statuses = {r.status for r in results}
        assert "billed" in statuses
        assert all(r.allowed for r in results)
        assert len(requests) == 1

    async def test_custom_cost_and_source(self, tmp_path):
        _write_token(tmp_path)
        requests: list[Any] = []

        async def request_fn(url, access_token, body):
            requests.append(body)
            return _ok_response(50)

        billing = _make_billing(tmp_path, request_fn, cost=50)
        decision = await billing.ensure_billed("thread-1")
        assert decision.allowed is True
        assert requests[0]["amount"] == 50


class TestInsufficient:
    async def test_insufficient_blocks_with_reason(self, tmp_path):
        _write_token(tmp_path)
        events: list[dict] = []

        async def request_fn(url, access_token, body):
            return 200, {"code": 40003, "message": "可用积分不足", "data": {"availablePoints": 5}}

        async def on_event(payload):
            events.append(payload)

        billing = _make_billing(tmp_path, request_fn, on_event=on_event)
        decision = await billing.ensure_billed("thread-1")
        assert decision.allowed is False
        assert decision.status == "insufficient"
        assert "30" in decision.reason
        assert "5" in decision.reason
        # 未持久化（没扣成）
        assert not (tmp_path / ".qraft" / "billing.json").exists()
        assert events[0]["kind"] == "blocked"
        assert events[0]["status"] == "insufficient"

    async def test_insufficient_does_not_stick(self, tmp_path):
        """被阻止的会话没有扣费标记：余额恢复后同一会话再次尝试可成功。"""
        _write_token(tmp_path)
        calls: list[Any] = []

        async def request_fn(url, access_token, body):
            calls.append(body)
            if len(calls) == 1:
                return 200, {"code": 40003, "message": "可用积分不足", "data": {"availablePoints": 5}}
            return _ok_response(240)

        billing = _make_billing(tmp_path, request_fn)
        first = await billing.ensure_billed("thread-1")
        second = await billing.ensure_billed("thread-1")
        assert first.allowed is False
        assert second.allowed is True
        assert second.status == "billed"
        assert len(calls) == 2


class TestTokenInvalid:
    async def test_token_invalid_with_fresh_file_recovers(self, tmp_path):
        token_file = _write_token(tmp_path, access="stale-token")
        calls: list[Any] = []

        async def request_fn(url, access_token, body):
            calls.append(access_token)
            if access_token == "stale-token":
                # 模拟主进程自动刷新重写 token 文件
                payload = json.loads(token_file.read_text(encoding="utf-8"))
                payload["accessToken"] = "fresh-token"
                token_file.write_text(json.dumps(payload), encoding="utf-8")
                return 200, {"code": 40102, "message": "access_token 无效或已过期"}
            return _ok_response()

        billing = _make_billing(tmp_path, request_fn)
        decision = await billing.ensure_billed("thread-1")
        assert decision.allowed is True
        assert decision.status == "billed"
        assert calls == ["stale-token", "fresh-token"]

    async def test_token_invalid_without_recovery_blocks(self, tmp_path):
        _write_token(tmp_path, access="stale-token")

        async def request_fn(url, access_token, body):
            return 200, {"code": 40102, "message": "access_token 无效或已过期"}

        billing = _make_billing(tmp_path, request_fn)
        decision = await billing.ensure_billed("thread-1")
        assert decision.allowed is False
        assert decision.status == "token_invalid"
        assert "重新登录" in decision.reason


class TestNetworkErrors:
    async def test_transient_error_retries_then_succeeds(self, tmp_path):
        _write_token(tmp_path)
        calls: list[Any] = []

        async def request_fn(url, access_token, body):
            calls.append(body)
            if len(calls) == 1:
                raise RuntimeError("connection reset")
            return _ok_response()

        billing = _make_billing(tmp_path, request_fn)
        decision = await billing.ensure_billed("thread-1")
        assert decision.allowed is True
        assert decision.status == "billed"
        assert len(calls) == 2

    async def test_persistent_error_fails_closed(self, tmp_path):
        _write_token(tmp_path)
        events: list[dict] = []

        async def request_fn(url, access_token, body):
            raise RuntimeError("connection reset")

        async def on_event(payload):
            events.append(payload)

        billing = _make_billing(tmp_path, request_fn, on_event=on_event)
        decision = await billing.ensure_billed("thread-1")
        assert decision.allowed is False
        assert decision.status == "error"
        assert "计费服务" in decision.reason
        assert events[0]["kind"] == "blocked"

    async def test_server_error_fails_closed(self, tmp_path):
        _write_token(tmp_path)

        async def request_fn(url, access_token, body):
            return 500, None

        billing = _make_billing(tmp_path, request_fn)
        decision = await billing.ensure_billed("thread-1")
        assert decision.allowed is False
        assert decision.status == "error"

    async def test_business_error_fails_closed(self, tmp_path):
        _write_token(tmp_path)

        async def request_fn(url, access_token, body):
            return 200, {"code": 500, "message": "服务端异常"}

        billing = _make_billing(tmp_path, request_fn)
        decision = await billing.ensure_billed("thread-1")
        assert decision.allowed is False
        assert decision.status == "error"


class TestEventAndBaseUrl:
    async def test_billed_event_carries_balance(self, tmp_path):
        _write_token(tmp_path)
        events: list[dict] = []

        async def request_fn(url, access_token, body):
            return _ok_response(270)

        async def on_event(payload):
            events.append(payload)

        billing = _make_billing(tmp_path, request_fn, on_event=on_event)
        await billing.ensure_billed("thread-1", turn_id="turn-7")
        assert events[0]["kind"] == "billed"
        assert events[0]["status"] == "billed"
        assert events[0]["cost"] == COST
        assert events[0]["balance"] == 270
        assert events[0]["turn_id"] == "turn-7"

    async def test_token_file_base_url_used_over_default(self, tmp_path):
        _write_token(tmp_path, base_url="https://prod.forge.miqroera.com/api")
        urls: list[str] = []

        async def request_fn(url, access_token, body):
            urls.append(url)
            return _ok_response()

        billing = _make_billing(tmp_path, request_fn)
        await billing.ensure_billed("thread-1")
        assert urls[0].startswith("https://prod.forge.miqroera.com/api/oauth2/points/deduct")

    async def test_missing_base_url_falls_back_to_default(self, tmp_path):
        _write_token(tmp_path)  # 旧版 token 文件无 baseUrl
        urls: list[str] = []

        async def request_fn(url, access_token, body):
            urls.append(url)
            return _ok_response()

        billing = _make_billing(tmp_path, request_fn)
        await billing.ensure_billed("thread-1")
        assert urls[0].startswith("https://test.forge.miqroera.com/api/oauth2/points/deduct")


class TestSessionScope:
    async def test_same_session_different_threads_deduct_once(self, tmp_path):
        """子代理独立 thread 但同一会话：只扣一次（去重键 = scope）。"""
        _write_token(tmp_path)
        requests: list[Any] = []

        async def request_fn(url, access_token, body):
            requests.append(body)
            return _ok_response(270)

        billing = _make_billing(tmp_path, request_fn)
        first = await billing.ensure_billed("thread-main", scope="desktop:sess-1")
        sub = await billing.ensure_billed("thread-subagent", scope="desktop:sess-1")
        assert first.status == "billed"
        assert sub.status == "already_billed"
        assert len(requests) == 1
        # memo 记录实际 thread，便于平台侧审计
        assert requests[0]["memo"].startswith("thread:thread-main")

    async def test_different_sessions_deduct_separately(self, tmp_path):
        _write_token(tmp_path)
        requests: list[Any] = []

        async def request_fn(url, access_token, body):
            requests.append(body)
            return _ok_response(270)

        billing = _make_billing(tmp_path, request_fn)
        first = await billing.ensure_billed("thread-1", scope="desktop:sess-1")
        second = await billing.ensure_billed("thread-2", scope="desktop:sess-2")
        assert first.status == "billed"
        assert second.status == "billed"
        assert len(requests) == 2

    async def test_scope_dedup_persists_across_instances(self, tmp_path):
        _write_token(tmp_path)
        requests: list[Any] = []

        async def request_fn(url, access_token, body):
            requests.append(body)
            return _ok_response()

        await _make_billing(tmp_path, request_fn).ensure_billed("thread-1", scope="desktop:sess-1")
        decision = await _make_billing(tmp_path, request_fn).ensure_billed(
            "thread-9", scope="desktop:sess-1"
        )
        assert decision.status == "already_billed"
        assert len(requests) == 1


class TestTokenFileHardening:
    async def test_non_object_token_json_treated_as_not_logged_in(self, tmp_path):
        for payload in ('[]', '"just-a-string"', '42'):
            token_file = tmp_path / ".qraft" / "token.json"
            token_file.parent.mkdir(parents=True, exist_ok=True)
            token_file.write_text(payload, encoding="utf-8")
            billing = _make_billing(tmp_path)
            decision = await billing.ensure_billed("thread-1")
            assert decision.allowed is True
            assert decision.status == "not_logged_in"


class TestBaseUrlHardening:
    async def test_non_https_base_url_rejected(self, tmp_path):
        _write_token(tmp_path, base_url="http://evil.example.com/api")
        urls: list[str] = []

        async def request_fn(url, access_token, body):
            urls.append(url)
            return _ok_response()

        billing = _make_billing(tmp_path, request_fn)
        decision = await billing.ensure_billed("thread-1")
        assert decision.allowed is False
        assert decision.status == "token_invalid"
        assert urls == []  # 请求根本不会发出去

    async def test_untrusted_host_rejected(self, tmp_path):
        _write_token(tmp_path, base_url="https://evil.example.com/api")
        urls: list[str] = []

        async def request_fn(url, access_token, body):
            urls.append(url)
            return _ok_response()

        billing = _make_billing(tmp_path, request_fn)
        decision = await billing.ensure_billed("thread-1")
        assert decision.allowed is False
        assert urls == []

    async def test_trusted_host_allowed(self, tmp_path):
        _write_token(tmp_path, base_url="https://test.forge.miqroera.com/api")
        urls: list[str] = []

        async def request_fn(url, access_token, body):
            urls.append(url)
            return _ok_response()

        billing = _make_billing(tmp_path, request_fn)
        decision = await billing.ensure_billed("thread-1")
        assert decision.allowed is True
        assert urls == ["https://test.forge.miqroera.com/api/oauth2/points/deduct"]


class TestDeductTotalTimeout:
    async def test_slow_deduct_hits_total_timeout_fails_closed(self, tmp_path):
        _write_token(tmp_path)

        async def slow_request_fn(url, access_token, body):
            await asyncio.sleep(5.0)
            return _ok_response()

        billing = _make_billing(
            tmp_path, slow_request_fn, cost=COST,
        )
        billing._deduct_total_timeout_s = 0.3
        decision = await billing.ensure_billed("thread-1")
        assert decision.allowed is False
        assert decision.status == "error"
        assert "计费服务" in decision.reason


class TestConcurrentInstances:
    async def test_second_instance_write_preserves_first_markers(self, tmp_path):
        """合并写盘：两个实例先后扣费，后写者不得抹掉先写者的标记。"""
        _write_token(tmp_path)

        async def request_fn(url, access_token, body):
            return _ok_response(270)

        first = _make_billing(tmp_path, request_fn)
        second = _make_billing(tmp_path, request_fn)
        await first.ensure_billed("thread-1")
        # second 已加载过（可能过期）的读缓存；其写盘必须合并磁盘最新内容
        assert second._is_billed_on_disk("thread-1")  # 先触发读缓存
        await second.ensure_billed("thread-2")

        billed = json.loads((tmp_path / ".qraft" / "billing.json").read_text(encoding="utf-8"))
        assert "thread-1" in billed  # first 的标记仍在
        assert "thread-2" in billed

        # 新实例重放：thread-1 不重复扣费
        third = _make_billing(tmp_path, request_fn)
        assert (await third.ensure_billed("thread-1")).status == "already_billed"
