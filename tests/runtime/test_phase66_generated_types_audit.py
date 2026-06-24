from __future__ import annotations

from pathlib import Path

from miqi.runtime.export_app_protocol_ts import DEFAULT_OUTPUT, render_typescript_contract
from miqi.runtime.protocol_snapshot import DEFAULT_SNAPSHOT


def test_generated_typescript_contract_is_up_to_date():
    expected = render_typescript_contract()
    actual = Path(DEFAULT_OUTPUT).read_text(encoding="utf-8")

    assert actual == expected


def test_generated_typescript_contract_is_covered_by_protocol_snapshot():
    assert DEFAULT_SNAPSHOT.name == "app_protocol_snapshot.v1.json"
    assert DEFAULT_SNAPSHOT.exists()
