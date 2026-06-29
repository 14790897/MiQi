"""Tests for deterministic replay document helpers."""

from __future__ import annotations


def test_stable_json_is_key_sorted_and_repeatable():
    from miqi.runtime.replay_document import stable_hash, stable_json

    left = {"b": 2, "a": {"d": 4, "c": 3}}
    right = {"a": {"c": 3, "d": 4}, "b": 2}

    assert stable_json(left) == stable_json(right)
    assert stable_hash(left) == stable_hash(right)
    assert stable_hash(left).startswith("sha256:")


def test_diff_documents_reports_hash_match():
    from miqi.runtime.replay_document import diff_replay_documents

    doc = {"version": 1, "threadId": "thread-1", "turns": []}
    diff = diff_replay_documents(doc, dict(doc))

    assert diff.same_hash is True
    assert diff.differences == []


def test_diff_documents_reports_changed_provider_messages():
    from miqi.runtime.replay_document import diff_replay_documents

    left = {
        "version": 1,
        "threadId": "thread-1",
        "providerMessages": [{"role": "user", "content": "one"}],
        "turns": [],
    }
    right = {
        "version": 1,
        "threadId": "thread-1",
        "providerMessages": [{"role": "user", "content": "two"}],
        "turns": [],
    }

    diff = diff_replay_documents(left, right)

    assert diff.same_hash is False
    assert any(item["path"] == "providerMessages" for item in diff.differences)


def test_with_document_hash_adds_deterministic_hash():
    from miqi.runtime.replay_document import with_document_hash

    payload = {
        "version": 1,
        "threadId": "thread-1",
        "sessionId": "client-a:default",
        "source": "stored",
        "turns": [{"turn_id": "turn-1"}],
        "providerMessages": [{"role": "user", "content": "hello"}],
        "integrity": {"ok": True, "checks": []},
        "rawLedgerItems": [],
    }

    doc = with_document_hash(payload)
    assert doc["documentHash"].startswith("sha256:")

    # Same payload → same hash
    doc2 = with_document_hash(dict(payload))
    assert doc["documentHash"] == doc2["documentHash"]


def test_canonical_replay_payload_includes_all_keys():
    from miqi.runtime.replay_document import canonical_replay_payload

    payload = canonical_replay_payload(
        thread_id="thread-1",
        session_id="client-a:default",
        source="stored",
        turns=[{"turn_id": "turn-1"}],
        provider_messages=[{"role": "user", "content": "hello"}],
        integrity={"ok": True, "checks": []},
    )

    assert payload["version"] == 1
    assert payload["threadId"] == "thread-1"
    assert payload["source"] == "stored"
    assert payload["rawLedgerItems"] == []


def test_document_hash_excludes_itself():
    from miqi.runtime.replay_document import stable_hash, with_document_hash

    payload = {
        "version": 1,
        "threadId": "thread-1",
        "turns": [],
        "providerMessages": [],
        "integrity": {"ok": True, "checks": []},
        "sessionId": "s",
        "source": "stored",
    }

    doc = with_document_hash(payload)
    # Hash should be the same as hashing the payload without hash
    expected = stable_hash(payload)
    assert doc["documentHash"] == expected
