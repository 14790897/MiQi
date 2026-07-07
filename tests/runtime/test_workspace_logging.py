from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from miqi.runtime.workspace_logging import (
    append_workspace_log,
    append_workspace_log_json,
    _redact_message,
)


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


def test_redact_json_quoted_key_value() -> None:
    """JSON-style quoted pairs like "api_key": "sk-secret" must redact the value."""
    msg = '{"api_key": "sk-secret-123", "name": "test"}'
    redacted = _redact_message(msg)
    assert "sk-secret-123" not in redacted
    assert '"name": "test"' in redacted


def test_redact_multi_word_authorization() -> None:
    """Authorization: Bearer <token> — the full two-word value must be redacted."""
    msg = "Authorization: Bearer sk-abc123xyz"
    redacted = _redact_message(msg)
    assert "sk-abc123xyz" not in redacted
    assert "Bearer" not in redacted or "[REDACTED]" in redacted


def test_redact_screaming_snake_case_env_var() -> None:
    """SCREAMING_SNAKE_CASE env var names like OPENAI_API_KEY=sk-xxx must be matched."""
    msg = "OPENAI_API_KEY=sk-proj-abc123 OTHER_VAR=hello"
    redacted = _redact_message(msg)
    assert "sk-proj-abc123" not in redacted
    assert "OTHER_VAR=hello" in redacted


def test_session_key_persisted_in_log_entry(tmp_path: Path) -> None:
    """session_key parameter must appear in the written log line."""
    workspace = tmp_path / "workspace"

    append_workspace_log(
        workspace,
        "tool call executed",
        source="tool",
        session_key="desktop:default:abc123",
    )

    log_path = workspace / "logs" / f"tool-{_today_str()}.log"
    assert log_path.exists()

    contents = log_path.read_text(encoding="utf-8")
    assert "session=desktop:default:abc123" in contents
    assert "tool call executed" in contents


def test_session_key_omitted_when_none(tmp_path: Path) -> None:
    """When session_key is None, the entry must not contain a session= field."""
    workspace = tmp_path / "workspace"

    append_workspace_log(workspace, "bridge started", source="bridge")

    log_path = workspace / "logs" / f"bridge-{_today_str()}.log"
    contents = log_path.read_text(encoding="utf-8")
    assert "session=" not in contents


def test_deep_json_redaction(tmp_path: Path) -> None:
    """Nested dict/list values inside JSON payloads must also be redacted."""
    workspace = tmp_path / "workspace"

    payload = {
        "source": "tool",
        "action": "api_call",
        "headers": {"Authorization": "Bearer sk-secret-nested"},
        "body": {"api_key": "sk-body-secret", "query": "hello"},
        "tags": ["token=ghp_list_secret", "safe_tag"],
    }

    append_workspace_log_json(workspace, payload)

    log_path = workspace / "logs" / f"tool-{_today_str()}.jsonl"
    assert log_path.exists()

    record = json.loads(log_path.read_text(encoding="utf-8").strip())
    # Nested secret in headers must be redacted
    assert "sk-secret-nested" not in json.dumps(record)
    # Nested secret in body must be redacted
    assert "sk-body-secret" not in json.dumps(record)
    # Secret inside list element must be redacted
    assert "ghp_list_secret" not in json.dumps(record)
    # Non-secret values survive
    assert record["action"] == "api_call"
    assert "safe_tag" in record["tags"]
