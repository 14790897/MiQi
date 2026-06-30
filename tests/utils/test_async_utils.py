"""Tests for miqi.utils.async_utils — safe coroutine execution from sync contexts."""

import asyncio
import warnings

import pytest


def test_run_async_safely_no_running_loop():
    """When no event loop is running, uses asyncio.run()."""
    from miqi.utils.async_utils import run_async_safely

    called = False

    async def _work():
        nonlocal called
        called = True
        return 42

    result = run_async_safely(_work())
    assert result == 42
    assert called


def test_run_async_safely_with_running_loop():
    """When an event loop IS running, dispatches to a thread."""
    from miqi.utils.async_utils import run_async_safely

    async def _outer():
        called = False

        async def _work():
            nonlocal called
            called = True
            return "hello"

        result = run_async_safely(_work())
        assert result == "hello"
        assert called

    asyncio.run(_outer())


def test_run_async_safely_no_runtime_warning():
    """run_async_safely must never produce 'coroutine was never awaited' warnings."""
    import tempfile
    from pathlib import Path

    from miqi.skills.plugin_manager import PluginManager
    from miqi.utils.async_utils import run_async_safely

    with tempfile.TemporaryDirectory() as tmp:
        user_dir = Path(tmp) / "user"
        user_dir.mkdir()
        system_dir = Path(tmp) / "system"
        system_dir.mkdir()

        pm = PluginManager(
            user_plugins_dir=user_dir,
            system_plugins_dir=system_dir,
        )

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = run_async_safely(pm.discover())

        runtime_warnings = [
            x for x in w
            if "never awaited" in str(x.message)
        ]
        assert len(runtime_warnings) == 0, (
            f"RuntimeWarning detected: {[str(x.message) for x in runtime_warnings]}"
        )
        assert isinstance(result, list)


def test_run_async_safely_propagates_exceptions():
    """Exceptions raised by the coroutine propagate to the caller."""
    from miqi.utils.async_utils import run_async_safely

    async def _failing():
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        run_async_safely(_failing())


def test_run_async_safely_with_running_loop_propagates_exceptions():
    """Exceptions also propagate in the running-loop (thread) path."""
    from miqi.utils.async_utils import run_async_safely

    async def _outer():
        async def _failing():
            raise RuntimeError("thread-boom")

        with pytest.raises(RuntimeError, match="thread-boom"):
            run_async_safely(_failing())

    asyncio.run(_outer())
