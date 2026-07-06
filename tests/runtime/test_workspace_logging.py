from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from miqi.runtime.workspace_logging import append_workspace_log


def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def test_append_workspace_log_writes_redacted_entry(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"

    append_workspace_log(
        workspace,
        "api_key=sk-secret-value token=ghp_example_token user=alice",
    )

    log_path = workspace / "logs" / f"bridge-{_today_str()}.log"
    assert log_path.exists()

    contents = log_path.read_text(encoding="utf-8")
    assert "user=alice" in contents
    assert "sk-secret-value" not in contents
    assert "ghp_example_token" not in contents
