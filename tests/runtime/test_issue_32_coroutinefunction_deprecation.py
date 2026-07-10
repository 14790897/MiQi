"""Regression coverage for issue #32 coroutine function checks."""

from pathlib import Path


def test_runtime_uses_inspect_coroutinefunction_not_asyncio_deprecated_api():
    root = Path(__file__).parent.parent.parent
    files = [
        root / "miqi" / "runtime" / "session.py",
        root / "miqi" / "runtime" / "task_runner.py",
    ]

    for path in files:
        source = path.read_text(encoding="utf-8")
        assert "asyncio.iscoroutinefunction" not in source
        assert "inspect.iscoroutinefunction" in source
