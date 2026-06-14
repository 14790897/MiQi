"""Tests for miqi.runtime.feature_runtime."""

from __future__ import annotations

from miqi.runtime.feature_runtime import FeatureRuntime


def test_feature_runtime_lists_default_features():
    fr = FeatureRuntime()
    page = fr.list_features()
    assert len(page["data"]) > 0
    keys = [f["key"] for f in page["data"]]
    assert "runtime.session" in keys
    assert "desktop.next" in keys

    # Every row must include the announcement key
    for row in page["data"]:
        assert "announcement" in row


def test_feature_runtime_stable_features_have_null_display_metadata():
    """Stable features: displayName, description, announcement are all None."""
    fr = FeatureRuntime()
    page = fr.list_features()
    stable_rows = [f for f in page["data"] if f["stage"] == "stable"]
    assert len(stable_rows) > 0
    for row in stable_rows:
        assert row["displayName"] is None, f"{row['key']} displayName must be None"
        assert row["description"] is None, f"{row['key']} description must be None"
        assert row["announcement"] is None, f"{row['key']} announcement must be None"


def test_feature_runtime_beta_features_may_have_display_metadata():
    """Beta/underDevelopment features may carry displayName/description."""
    fr = FeatureRuntime()
    page = fr.list_features()
    non_stable = [f for f in page["data"] if f["stage"] != "stable"]
    assert len(non_stable) > 0
    # At least some non-stable features have display metadata
    display_names = [f["displayName"] for f in non_stable]
    assert any(d is not None for d in display_names), (
        "Expected at least one beta/underDevelopment feature to have a displayName"
    )


def test_feature_runtime_override_changes_enabled():
    fr = FeatureRuntime()
    # desktop.next is disabled by default
    assert fr.is_enabled("desktop.next") is False

    ignored = fr.set_enablement({"desktop.next": True})
    assert ignored == []
    assert fr.is_enabled("desktop.next") is True

    # runtime.session is enabled by default
    assert fr.is_enabled("runtime.session") is True
    fr.set_enablement({"runtime.session": False})
    assert fr.is_enabled("runtime.session") is False


def test_feature_runtime_ignores_invalid_keys():
    fr = FeatureRuntime()
    ignored = fr.set_enablement({
        "nonexistent.feature": True,
        "runtime.session": False,
        "also.invalid.key": False,
    })
    assert "nonexistent.feature" in ignored
    assert "also.invalid.key" in ignored
    assert "runtime.session" not in ignored
    # Valid key was still applied
    assert fr.is_enabled("runtime.session") is False


def test_feature_runtime_paginates_deterministically():
    fr = FeatureRuntime()
    page1 = fr.list_features(limit=3)
    assert len(page1["data"]) == 3
    assert page1["nextCursor"] is not None

    page2 = fr.list_features(cursor=page1["nextCursor"], limit=3)
    assert len(page2["data"]) == 3

    # Should be no overlap
    keys1 = {f["key"] for f in page1["data"]}
    keys2 = {f["key"] for f in page2["data"]}
    assert keys1.isdisjoint(keys2)

    # Second call with same params returns same result
    page1b = fr.list_features(limit=3)
    assert page1b["data"] == page1["data"]


def test_feature_runtime_unknown_key_is_disabled():
    fr = FeatureRuntime()
    assert fr.is_enabled("completely.unknown.feature") is False
