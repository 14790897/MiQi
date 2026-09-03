"""Qraft 平台积分计费闸门（OAuth2 第三方接入指南 /points/deduct）。

产品规则（2026-09-02 确认）：
- 登录后（``<workspace>/.qraft/token.json`` 存在），会话中首次执行工具/技能前
  扣除一次算力积分（默认 30 分/任务），普通对话不扣分；
- 余额不足（业务码 40003）阻止任务执行，任务不跑；
- 每会话（thread_id）只扣一次：内存标记 + ``<workspace>/.qraft/billing.json``
  持久化，应用重启/多运行时实例间不重复扣费；
- 未登录（无 token 文件）不拦不扣 —— 登录收口由平台内置模型改造负责；
- 计费请求失败 fail-closed：阻止任务执行，避免产生无账单的算力消耗。

扣费接口契约（test.forge.miqroera.com OpenAPI v0）：
- POST {baseUrl}/oauth2/points/deduct
  body: {amount:int>0, source:str, resourceType?, project?, memo?}
  业务码：200 成功 / 40001 amount 缺失 / 40002 source 缺失 /
  40003 可用积分不足 / 40101 token 缺失 / 40102 token 无效或过期
  响应 data 为 PointBalanceVO（availablePoints 等，扣后余额）。
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

from loguru import logger

# 默认成本与来源（config.billing 可覆盖）。
DEFAULT_COST_PER_TASK = 30
DEFAULT_SOURCE = "desktop-agent-task"
# 无 token 文件里 baseUrl 字段时的兜底（旧版 token 文件兼容）。
DEFAULT_BASE_URL = "https://test.forge.miqroera.com/api"
# billed 持久化文件最多保留的条目数（防无限增长）。
MAX_BILLED_ENTRIES = 500

# 网络类瞬时错误的退避（秒）。
RETRY_BACKOFF_S = [0.5, 1.0]
# 单次扣费请求的超时（秒）。
DEFAULT_REQUEST_TIMEOUT_S = 8.0
# 整个扣费流程（含重试）的总时限：超时按 fail-closed 阻止任务，
# 避免平台故障时工具调用被闸门拖住近一分钟无反馈。
DEFAULT_DEDUCT_TOTAL_TIMEOUT_S = 20.0
# 平台受信 origin（计费请求只发往这些主机，防 token 文件被篡改后
# 把 Bearer token 发到任意地址）。
TRUSTED_PLATFORM_HOSTS = ("forge.miqroera.com",)
# 跨进程计费锁的陈旧阈值（秒）：持有者崩溃后超过该时长可被窃取。
LOCK_STALE_SECONDS = 30.0


@dataclass
class BillingDecision:
    """一次计费闸门判断的结果。"""

    allowed: bool
    """True = 可以执行工具。"""

    status: str
    """"billed" | "already_billed" | "not_logged_in" | "insufficient"
    | "token_invalid" | "error"."""

    reason: str = ""
    """阻止执行时给模型/用户看的说明文字。"""

    cost: int = 0
    """本次扣除的积分（billed 时有效）。"""

    balance_after: int | None = None
    """扣费后的可用积分（billed 时有效）。"""


class PointsBilling:
    """会话首次工具执行前的积分扣费闸门。

    用法：运行时创建单个实例（共享同一 token/billed 文件），在工具实际
    执行前调用 ``await billing.ensure_billed(thread_id)``；返回
    :class:`BillingDecision`，``allowed=False`` 时用 ``reason`` 替换工具
    执行结果并停止该次执行。
    """

    def __init__(
        self,
        token_file: Path | str,
        billed_file: Path | str,
        *,
        cost: int = DEFAULT_COST_PER_TASK,
        source: str = DEFAULT_SOURCE,
        default_base_url: str = DEFAULT_BASE_URL,
        timeout_s: float = DEFAULT_REQUEST_TIMEOUT_S,
        deduct_total_timeout_s: float = DEFAULT_DEDUCT_TOTAL_TIMEOUT_S,
        # 测试注入：httpx 兼容的异步请求函数 / 事件回调。
        request_fn: Callable[..., Awaitable[Any]] | None = None,
        on_event: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    ) -> None:
        self._token_file = Path(token_file)
        self._billed_file = Path(billed_file)
        self._cost = max(1, int(cost))
        self._source = source
        self._default_base_url = default_base_url
        self._timeout_s = timeout_s
        self._deduct_total_timeout_s = deduct_total_timeout_s
        self._request_fn = request_fn
        self._on_event = on_event
        self._lock = asyncio.Lock()
        self._billed_memory: set[str] = set()
        self._loaded_from_disk = False

    # ── 公开入口 ─────────────────────────────────────────────────────────

    async def ensure_billed(
        self,
        thread_id: str,
        turn_id: str | None = None,
        scope: str | None = None,
        on_event: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    ) -> BillingDecision:
        """保证计费作用域已为本次任务扣费；返回是否放行。

        去重键 = *scope*（会话维度，live 路径传 session_id —— 子代理的
        独立 thread 不重复扣费；KUN 路径无会话概念，退化为 thread_id）。
        未登录（无 token 文件）恒放行且不扣费。
        同作用域并发（并行工具批量）与跨实例（磁盘标记 + 文件锁）都只扣一次。
        *on_event* 为按调用会话的事件回调（共享实例时各会话事件发往
        各自 sink）；缺省回退到实例级回调。
        """
        billing_key = (scope or thread_id).strip()
        if not billing_key:
            return BillingDecision(allowed=True, status="not_logged_in")

        token_payload = self._read_token_file()
        if token_payload is None:
            # 未登录：不拦不扣（登录收口由平台内置模型改造负责）。
            return BillingDecision(allowed=True, status="not_logged_in")

        try:
            async with self._lock:
                if billing_key in self._billed_memory:
                    return BillingDecision(allowed=True, status="already_billed")

                if self._is_billed_on_disk(billing_key):
                    self._billed_memory.add(billing_key)
                    return BillingDecision(allowed=True, status="already_billed")

                # 跨进程锁：两个进程（或两套运行时）共享同一 workspace 时，
                # 检查-扣费-落标记的临界区必须串行，否则两实例可能同时
                # 通过磁盘检查各扣一次。锁文件与 billed 文件同目录。
                await asyncio.to_thread(self._acquire_file_lock)
                try:
                    # 拿锁后重新读盘（可能已被对方写入标记）。
                    if self._load_billed_disk().get(billing_key):
                        self._billed_memory.add(billing_key)
                        self._billed_disk = self._load_billed_disk()
                        self._loaded_from_disk = True
                        return BillingDecision(allowed=True, status="already_billed")

                    decision = await asyncio.wait_for(
                        self._deduct(
                            thread_id, turn_id, token_payload, on_event,
                            billing_key=billing_key,
                        ),
                        timeout=self._deduct_total_timeout_s,
                    )
                    if decision.allowed:
                        self._billed_memory.add(billing_key)
                        self._persist_billed(billing_key, decision)
                    return decision
                finally:
                    await asyncio.to_thread(self._release_file_lock)
        except asyncio.TimeoutError:
            # 扣费流程总时限：fail-closed（与网络错误同语义）。
            await self._emit(
                {
                    "kind": "blocked",
                    "status": "error",
                    "thread_id": thread_id,
                    "turn_id": turn_id,
                    "cost": self._cost,
                    "message": "平台计费服务暂不可用，任务未执行。请稍后重试（网络或服务恢复后重发消息即可）。",
                },
                on_event,
            )
            return BillingDecision(
                allowed=False,
                status="error",
                reason="平台计费服务暂不可用，任务未执行。请稍后重试（网络或服务恢复后重发消息即可）。",
            )

    # ── 跨进程文件锁 ──────────────────────────────────────────────────────

    @property
    def _lock_file(self) -> Path:
        return self._billed_file.with_name(self._billed_file.name + ".lock")

    def _acquire_file_lock(self) -> None:
        """获取计费临界区锁（O_EXCL 创建）；等待至多 ~5s，超时抛异常。

        锁文件带年龄：持有者崩溃后，超过 LOCK_STALE_SECONDS 的锁可被
        窃取（删除重建），不会永久卡死后续计费。
        """
        deadline = time.monotonic() + 5.0
        while True:
            try:
                fd = os.open(self._lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode("ascii"))
                os.close(fd)
                return
            except FileExistsError:
                try:
                    age = time.time() - self._lock_file.stat().st_mtime
                except FileNotFoundError:
                    continue  # 对方刚好释放，立刻重试
                if age > LOCK_STALE_SECONDS:
                    logger.warning("billing: 计费锁已陈旧（{:.0f}s），窃取重建", age)
                    try:
                        self._lock_file.unlink(missing_ok=True)
                    except OSError:
                        pass
                    continue
                if time.monotonic() >= deadline:
                    raise RuntimeError("计费锁等待超时（另一进程正在扣费）")
                time.sleep(0.1)

    def _release_file_lock(self) -> None:
        try:
            self._lock_file.unlink(missing_ok=True)
        except OSError:
            pass

    # ── token 文件 ───────────────────────────────────────────────────────

    def _read_token_file(self) -> dict[str, Any] | None:
        """读取 token 文件；缺失/损坏/非对象时返回 None（视为未登录）。"""
        try:
            raw = json.loads(self._token_file.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except Exception as exc:
            logger.warning("billing: token 文件不可读（{}），按未登录处理", exc)
            return None
        if not isinstance(raw, dict) or not raw.get("accessToken"):
            return None
        return raw

    # ── billed 持久化 ────────────────────────────────────────────────────

    def _load_billed_disk(self) -> dict[str, Any]:
        """读盘，每次返回最新内容（调用方自行决定缓存策略）。"""
        try:
            raw = json.loads(self._billed_file.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                return raw
        except FileNotFoundError:
            pass
        except Exception as exc:
            logger.warning("billing: billed 文件损坏（{}），忽略历史记录", exc)
        return {}

    def _is_billed_on_disk(self, thread_id: str) -> bool:
        if not self._loaded_from_disk:
            self._billed_disk = self._load_billed_disk()
            self._loaded_from_disk = True
        return thread_id in self._billed_disk

    def _persist_billed(self, billing_key: str, decision: BillingDecision) -> None:
        # 合并写盘：多个 PointsBilling 实例（多会话/多进程）共享同一
        # billing.json，各持过期快照时直接整体覆写会互相抹掉标记。
        # 写前重新读盘，把本次标记合并进最新内容。
        fresh = self._load_billed_disk()
        fresh[billing_key] = {
            "deductedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "cost": decision.cost,
            "balanceAfter": decision.balance_after,
        }
        if len(fresh) > MAX_BILLED_ENTRIES:
            for key in list(fresh)[: len(fresh) - MAX_BILLED_ENTRIES]:
                fresh.pop(key, None)
        try:
            self._billed_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._billed_file.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(fresh, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            tmp.replace(self._billed_file)
            # 读缓存同步为合并后的最新内容，避免同实例后续读取用旧快照。
            self._billed_disk = fresh
            self._loaded_from_disk = True
        except Exception as exc:
            # 持久化失败只影响重启后的去重（进程内内存标记仍在），不阻断任务。
            logger.warning("billing: billed 文件写入失败（{}）", exc)

    # ── 扣费请求 ─────────────────────────────────────────────────────────

    async def _deduct(
        self,
        thread_id: str,
        turn_id: str | None,
        token_payload: dict[str, Any],
        on_event: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
        billing_key: str = "",
    ) -> BillingDecision:
        base_url = str(
            token_payload.get("baseUrl") or self._default_base_url
        ).rstrip("/")
        access_token = str(token_payload["accessToken"])

        async def _notify(payload: dict[str, Any]) -> None:
            await self._emit(payload, on_event)

        for attempt in range(3):
            try:
                data = await self._post_deduct(
                    base_url, access_token, thread_id, billing_key
                )
            except _AmbiguousTimeoutError as exc:
                # 歧义超时：服务端可能已受理并扣费，重试会造成双扣。
                # 不重试、不落标记 —— fail-closed 阻止本次任务；用户
                # 重发后若上次已扣费，余额减少会如实反映在下次扣费中。
                logger.error("billing: 扣费请求超时（结果不确定，不重试）")
                await _notify(
                    {
                        "kind": "blocked",
                        "status": "error",
                        "thread_id": thread_id,
                        "turn_id": turn_id,
                        "cost": self._cost,
                        "message": "平台计费响应超时，本次任务未执行。请稍后重试。",
                    }
                )
                return BillingDecision(
                    allowed=False,
                    status="error",
                    reason="平台计费响应超时，本次任务未执行。请稍后重试。",
                )
            except _TokenInvalidError:
                # token 失效：主进程自动刷新会重写 token 文件，重读一次再试；
                # 仍失败则阻止并提示重新登录。
                if attempt == 0:
                    fresh = self._read_token_file()
                    if fresh and fresh.get("accessToken") != access_token:
                        access_token = str(fresh["accessToken"])
                        base_url = str(
                            fresh.get("baseUrl") or self._default_base_url
                        ).rstrip("/")
                        continue
                await _notify(
                    {
                        "kind": "blocked",
                        "status": "token_invalid",
                        "thread_id": thread_id,
                        "turn_id": turn_id,
                        "cost": self._cost,
                        "message": "平台登录已过期，任务无法执行：请到 设置 → Qraft 平台账号 重新登录后重试。",
                    }
                )
                return BillingDecision(
                    allowed=False,
                    status="token_invalid",
                    reason="平台登录已过期，无法执行任务：请到 设置 → Qraft 平台账号 重新登录后重试。",
                )
            except _InsufficientError as exc:
                message = (
                    f"积分不足，任务无法执行：本次任务需要 {self._cost} 积分，"
                    f"当前可用 {exc.available} 积分。请到平台充值后再试。"
                )
                await _notify(
                    {
                        "kind": "blocked",
                        "status": "insufficient",
                        "thread_id": thread_id,
                        "turn_id": turn_id,
                        "cost": self._cost,
                        "balance": exc.available,
                        "message": message,
                    }
                )
                return BillingDecision(
                    allowed=False,
                    status="insufficient",
                    reason=message,
                    balance_after=exc.available,
                )
            except Exception as exc:
                # 网络/服务端错误：退避重试，耗尽后 fail-closed。
                if attempt < 2:
                    await asyncio.sleep(RETRY_BACKOFF_S[attempt])
                    continue
                logger.error("billing: 扣费请求失败（已重试）：{}", exc)
                await _notify(
                    {
                        "kind": "blocked",
                        "status": "error",
                        "thread_id": thread_id,
                        "turn_id": turn_id,
                        "cost": self._cost,
                        "message": "平台计费服务暂不可用，任务未执行。请稍后重试（网络或服务恢复后重发消息即可）。",
                    }
                )
                return BillingDecision(
                    allowed=False,
                    status="error",
                    reason="平台计费服务暂不可用，任务未执行。请稍后重试（网络或服务恢复后重发消息即可）。",
                )
            else:
                balance = data.get("data") or {}
                balance_after = _as_int(balance.get("availablePoints"))
                await _notify(
                    {
                        "kind": "billed",
                        "status": "billed",
                        "thread_id": thread_id,
                        "turn_id": turn_id,
                        "cost": self._cost,
                        "balance": balance_after,
                    }
                )
                logger.info(
                    "billing: 扣费成功 thread={} cost={} balance_after={}",
                    thread_id, self._cost, balance_after,
                )
                return BillingDecision(
                    allowed=True,
                    status="billed",
                    cost=self._cost,
                    balance_after=balance_after,
                )

        # 不可达（循环内必 return）。
        return BillingDecision(allowed=False, status="error", reason="平台计费服务暂不可用。")

    async def _post_deduct(
        self, base_url: str, access_token: str, thread_id: str, billing_key: str = ""
    ) -> dict[str, Any]:
        """POST /oauth2/points/deduct；业务码转异常。

        安全约束（CWE-319/918）：token 文件在 workspace 信任域内仍可能
        被篡改/写坏，请求前校验 baseUrl 必须是受信平台的 https 地址，
        且显式禁用重定向——Bearer token 绝不发往非平台主机。
        """
        try:
            parsed_url = urllib.parse.urlparse(base_url)
        except ValueError:
            raise _TokenInvalidError() from None
        if (
            parsed_url.scheme != "https"
            or not parsed_url.hostname
            or not any(
                parsed_url.hostname == host
                or parsed_url.hostname.endswith("." + host)
                for host in TRUSTED_PLATFORM_HOSTS
            )
        ):
            logger.error("billing: 拒绝非受信平台地址的计费请求：{}", base_url)
            raise _TokenInvalidError()

        body = {
            "amount": self._cost,
            "source": self._source,
            "resourceType": "agent-task",
            "memo": f"thread:{thread_id[:64]}",
            # 稳定幂等键（同一计费作用域的所有尝试一致）：平台侧可据此
            # 原子去重；重试/并发实例发来的同一键只应扣一次。
            "idempotencyKey": f"{self._source}:{billing_key}",
        }
        if self._request_fn is not None:
            resp = await self._request_fn(
                f"{base_url}/oauth2/points/deduct", access_token, body
            )
            # 测试注入返回 (status, parsed_json)；生产走 httpx。
            status, parsed = resp[0], resp[1]
        else:
            import httpx

            try:
                async with httpx.AsyncClient(
                    timeout=self._timeout_s, follow_redirects=False
                ) as client:
                    response = await client.post(
                        f"{base_url}/oauth2/points/deduct",
                        json=body,
                        headers={"Authorization": f"Bearer {access_token}"},
                    )
            except httpx.TimeoutException as exc:
                # 超时=结果不确定（服务端可能已扣费）：转歧义异常，不重试。
                raise _AmbiguousTimeoutError() from exc
            status, parsed = response.status_code, _safe_json(response.text)

        if status in (401, 403) or (
            isinstance(parsed, dict) and parsed.get("code") in (40101, 40102)
        ):
            raise _TokenInvalidError()
        code = parsed.get("code") if isinstance(parsed, dict) else None
        if code == 40003:
            available = None
            data = parsed.get("data") if isinstance(parsed, dict) else None
            if isinstance(data, dict):
                available = _as_int(data.get("availablePoints"))
            raise _InsufficientError(available)
        if status >= 400:
            raise RuntimeError(f"扣费接口 HTTP {status}")
        if not isinstance(parsed, dict) or code != 200:
            message = parsed.get("message") if isinstance(parsed, dict) else None
            raise RuntimeError(f"扣费失败：{message or parsed or '未知业务错误'}")
        return parsed

    async def _emit(
        self,
        payload: dict[str, Any],
        on_event: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    ) -> None:
        callback = on_event or self._on_event
        if callback is None:
            return
        try:
            await callback(payload)
        except Exception:
            logger.exception("billing: 事件回调异常")


class _TokenInvalidError(Exception):
    """access_token 缺失/无效/过期（40101/40102）。"""


class _AmbiguousTimeoutError(Exception):
    """扣费请求超时——服务端是否已受理未知，重试会造成双扣。"""


class _InsufficientError(Exception):
    """可用积分不足（40003）。"""

    def __init__(self, available: int | None):
        super().__init__("insufficient points")
        self.available = available


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_json(text: str) -> Any:
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return None
