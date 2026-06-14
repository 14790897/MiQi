"""Tests for miqi.runtime.permission_profile_runtime."""

from __future__ import annotations

from miqi.runtime.permission_profile_runtime import PermissionProfileRuntime


def test_permission_profile_runtime_lists_builtin_profiles():
    pr = PermissionProfileRuntime()
    page = pr.list_profiles()
    assert len(page["data"]) == 3

    ids = {p["id"] for p in page["data"]}
    assert ":read-only" in ids
    assert ":workspace" in ids
    assert ":full-access" in ids


def test_permission_profile_runtime_paginates():
    pr = PermissionProfileRuntime()
    page1 = pr.list_profiles(limit=2)
    assert len(page1["data"]) == 2
    assert page1["nextCursor"] is not None

    page2 = pr.list_profiles(cursor=page1["nextCursor"], limit=2)
    assert len(page2["data"]) == 1  # remaining profile
    assert page2["nextCursor"] is None

    ids1 = {p["id"] for p in page1["data"]}
    ids2 = {p["id"] for p in page2["data"]}
    assert ids1.isdisjoint(ids2)


def test_permission_profile_runtime_contains_workspace_profile():
    pr = PermissionProfileRuntime()
    page = pr.list_profiles()
    workspace = next(p for p in page["data"] if p["id"] == ":workspace")
    assert workspace["source"] == "builtin"
    assert workspace["filesystemMode"] == "workspace-write"
    assert workspace["allowExec"] is True


def test_permission_profile_runtime_shape():
    pr = PermissionProfileRuntime()
    page = pr.list_profiles()
    for profile in page["data"]:
        assert "id" in profile
        assert "description" in profile
        assert "source" in profile
        assert "filesystemMode" in profile
        assert "network" in profile
        assert "allowExec" in profile
        assert "networkAllowed" in profile
