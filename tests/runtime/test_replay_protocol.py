"""Tests for replay protocol dataclasses."""

from __future__ import annotations


def test_replay_integrity_report_serializes_camel_case():
    from miqi.runtime.replay_protocol import ReplayIntegrityCheck, ReplayIntegrityReport

    report = ReplayIntegrityReport(
        thread_id="thread-1",
        session_id="client-a:default",
        ok=False,
        checks=[
            ReplayIntegrityCheck(
                name="providerHistoryMatchesLedger",
                ok=False,
                severity="error",
                message="Provider history differs from ledger reconstruction",
                details={"historyCount": 3, "ledgerCount": 2},
            ),
        ],
    )

    assert report.to_dict() == {
        "threadId": "thread-1",
        "sessionId": "client-a:default",
        "ok": False,
        "checks": [
            {
                "name": "providerHistoryMatchesLedger",
                "ok": False,
                "severity": "error",
                "message": "Provider history differs from ledger reconstruction",
                "details": {"historyCount": 3, "ledgerCount": 2},
            }
        ],
    }


def test_replay_document_serializes_stably():
    from miqi.runtime.replay_protocol import ReplayDocumentView

    doc = ReplayDocumentView(
        version=1,
        thread_id="thread-1",
        session_id="client-a:default",
        source="stored",
        document_hash="sha256:abc",
        turns=[{"id": "turn-1"}],
        provider_messages=[{"role": "user", "content": "hello"}],
        integrity={"ok": True, "checks": []},
        raw_ledger_items=[],
    )

    assert doc.to_dict()["documentHash"] == "sha256:abc"
    assert doc.to_dict()["providerMessages"][0]["content"] == "hello"


def test_replay_diff_serializes_camel_case():
    from miqi.runtime.replay_protocol import ReplayDiffView

    diff = ReplayDiffView(
        same_hash=False,
        left_hash="sha256:aaa",
        right_hash="sha256:bbb",
        differences=[
            {"path": "threadId", "left": "a", "right": "b"},
        ],
    )

    data = diff.to_dict()
    assert data["sameHash"] is False
    assert data["leftHash"] == "sha256:aaa"
    assert data["rightHash"] == "sha256:bbb"
    assert data["differences"][0]["path"] == "threadId"
