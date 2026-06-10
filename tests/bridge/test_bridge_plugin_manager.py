"""Tests for bridge PluginManager initialization — ensures discover()
is awaited properly in async contexts without RuntimeWarning."""

import warnings


def test_discover_awaited_in_async_context_no_runtime_warning():
    """Reproduce the bridge _run() pattern: asyncio.run() wraps an async
    function that awaits discover(). Must NOT produce 'never awaited' warnings.

    This is the fixed pattern — the old code used get_event_loop().run_until_complete()
    inside an already-running loop, which silently dropped the coroutine.
    """
    import asyncio
    import tempfile
    from pathlib import Path

    from miqi.skills.plugin_manager import PluginManager

    with tempfile.TemporaryDirectory() as tmp:
        user_dir = Path(tmp) / "user"
        user_dir.mkdir()
        system_dir = Path(tmp) / "system"
        system_dir.mkdir()

        async def _bridge_like_init():
            """Mimic handle_chat_send's _run() initialization block."""
            pm = PluginManager(
                user_plugins_dir=user_dir,
                system_plugins_dir=system_dir,
                workspace=Path(tmp),
            )
            # This is the critical line — must await directly
            discovered = await pm.discover()
            return discovered

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            result = asyncio.run(_bridge_like_init())

        runtime_warnings = [
            x for x in w
            if "never awaited" in str(x.message)
        ]
        assert len(runtime_warnings) == 0, (
            f"RuntimeWarning detected: {[str(x.message) for x in runtime_warnings]}"
        )
        assert isinstance(result, list)
