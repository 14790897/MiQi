"""Tests for miqi.execution.hook_runtime."""

import pytest
from miqi.execution.hook_runtime import (
    HookRuntime,
    HookRegistration,
    HookPoint,
)


class FakeContext:
    def __init__(self, tool_name):
        self.tool_name = tool_name


@pytest.mark.asyncio
async def test_register_and_run_hook():
    runtime = HookRuntime()
    calls = []

    async def my_hook(ctx):
        calls.append(ctx.tool_name)

    runtime.register(HookRegistration(
        hook_point=HookPoint.PRE_TOOL_USE,
        tool_pattern="exec",
        callback=my_hook,
    ))

    ctx = FakeContext("exec")
    await runtime.run(HookPoint.PRE_TOOL_USE, ctx)
    assert calls == ["exec"]


@pytest.mark.asyncio
async def test_glob_pattern_matching():
    runtime = HookRuntime()
    calls = []

    async def my_hook(ctx):
        calls.append(ctx.tool_name)

    runtime.register(HookRegistration(
        hook_point=HookPoint.PRE_TOOL_USE,
        tool_pattern="write_*",
        callback=my_hook,
    ))

    await runtime.run(HookPoint.PRE_TOOL_USE, FakeContext("write_file"))
    await runtime.run(HookPoint.PRE_TOOL_USE, FakeContext("read_file"))
    assert calls == ["write_file"]  # read_file doesn't match write_*


@pytest.mark.asyncio
async def test_hook_priority_ordering():
    runtime = HookRuntime()
    order = []

    async def hook_a(ctx):
        order.append("A")

    async def hook_b(ctx):
        order.append("B")

    runtime.register(HookRegistration(
        hook_point=HookPoint.PRE_TOOL_USE,
        tool_pattern="*",
        callback=hook_a,
        priority=200,
    ))
    runtime.register(HookRegistration(
        hook_point=HookPoint.PRE_TOOL_USE,
        tool_pattern="*",
        callback=hook_b,
        priority=100,  # lower = runs first
    ))

    await runtime.run(HookPoint.PRE_TOOL_USE, FakeContext("exec"))
    assert order == ["B", "A"]  # B has lower priority, runs first


@pytest.mark.asyncio
async def test_hook_error_does_not_crash():
    runtime = HookRuntime()
    calls = []

    async def bad_hook(ctx):
        raise RuntimeError("hook failed")

    async def good_hook(ctx):
        calls.append("good")

    runtime.register(HookRegistration(
        hook_point=HookPoint.PRE_TOOL_USE,
        tool_pattern="*",
        callback=bad_hook,
        priority=100,
    ))
    runtime.register(HookRegistration(
        hook_point=HookPoint.PRE_TOOL_USE,
        tool_pattern="*",
        callback=good_hook,
        priority=200,
    ))

    # Should not raise
    await runtime.run(HookPoint.PRE_TOOL_USE, FakeContext("exec"))
    assert calls == ["good"]  # good hook still runs after bad hook fails


@pytest.mark.asyncio
async def test_different_hook_points_separated():
    runtime = HookRuntime()
    pre_calls = []
    post_calls = []

    async def pre_hook(ctx):
        pre_calls.append(ctx.tool_name)

    async def post_hook(ctx):
        post_calls.append(ctx.tool_name)

    runtime.register(HookRegistration(
        hook_point=HookPoint.PRE_TOOL_USE,
        tool_pattern="*",
        callback=pre_hook,
    ))
    runtime.register(HookRegistration(
        hook_point=HookPoint.POST_TOOL_USE,
        tool_pattern="*",
        callback=post_hook,
    ))

    await runtime.run(HookPoint.PRE_TOOL_USE, FakeContext("exec"))
    assert pre_calls == ["exec"]
    assert post_calls == []  # post hooks not triggered on pre run

    await runtime.run(HookPoint.POST_TOOL_USE, FakeContext("exec"))
    assert post_calls == ["exec"]


@pytest.mark.asyncio
async def test_no_matching_hooks():
    runtime = HookRuntime()
    calls = []

    async def my_hook(ctx):
        calls.append(ctx.tool_name)

    runtime.register(HookRegistration(
        hook_point=HookPoint.PRE_TOOL_USE,
        tool_pattern="specific_tool",
        callback=my_hook,
    ))

    await runtime.run(HookPoint.PRE_TOOL_USE, FakeContext("other_tool"))
    assert calls == []  # no match
