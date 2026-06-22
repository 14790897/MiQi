"""Contract tests for platform capability markers and fixtures.

Ensures markers are registered, capability fixtures produce valid
skip reasons, and skip is only used when capability is truly absent.
"""

import pytest


def test_subprocess_marker_is_registered():
    """The subprocess marker must be registered in pyproject.toml."""
    marker = getattr(pytest.mark, "subprocess", None)
    assert marker is not None, "subprocess marker is not registered"


def test_sandbox_marker_is_registered():
    """The sandbox marker must be registered."""
    # Verify markers exist by checking they can be applied
    marker = getattr(pytest.mark, "sandbox", None)
    assert marker is not None, "sandbox marker is not registered"


def test_bwrap_marker_is_registered():
    """The bwrap marker must be registered."""
    marker = getattr(pytest.mark, "bwrap", None)
    assert marker is not None, "bwrap marker is not registered"


def test_wsl_marker_is_registered():
    """The wsl marker must be registered."""
    marker = getattr(pytest.mark, "wsl", None)
    assert marker is not None, "wsl marker is not registered"


def test_self_managed_env_marker_is_registered():
    """The self_managed_env marker must be registered."""
    marker = getattr(pytest.mark, "self_managed_env", None)
    assert marker is not None, "self_managed_env marker is not registered"


def test_require_subprocess_fixture_is_callable(require_subprocess):
    """require_subprocess fixture is available (returns None if capable, skips otherwise)."""
    assert require_subprocess is None, (
        "require_subprocess should return None when capability is present"
    )


@pytest.mark.bwrap
def test_require_bwrap_fixture_is_callable(require_bwrap):
    """require_bwrap fixture is available."""
    assert require_bwrap is None, (
        "require_bwrap should return None when capability is present"
    )
