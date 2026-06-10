"""Tests for miqi.protocol.permissions."""


def test_imports():
    from miqi.protocol.permissions import (  # noqa: F401
        FileSystemAccessMode,
        FileSystemSandboxPolicy,
        NetworkSandboxPolicy,
        SandboxPermissions,
    )
