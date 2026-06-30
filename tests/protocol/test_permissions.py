"""Tests for miqi.protocol.permissions."""

from miqi.protocol.permissions import (
    FileSystemAccessMode,
    FileSystemPathRule,
    FileSystemSandboxPolicy,
    NetworkSandboxPolicy,
    SandboxPermissions,
)


def test_file_system_access_mode():
    assert FileSystemAccessMode.READ.value == "read"
    assert FileSystemAccessMode.WRITE.value == "write"
    assert FileSystemAccessMode.NONE.value == "none"


def test_file_system_path_rule():
    rule = FileSystemPathRule(
        path="/home/user/project",
        mode=FileSystemAccessMode.WRITE,
    )
    assert rule.path == "/home/user/project"
    assert rule.recursive is True


def test_file_system_path_rule_non_recursive():
    rule = FileSystemPathRule(
        path="/tmp/log.txt",
        mode=FileSystemAccessMode.READ,
        recursive=False,
    )
    assert rule.recursive is False


def test_file_system_sandbox_policy():
    policy = FileSystemSandboxPolicy(
        rules=[
            FileSystemPathRule(path="/workspace", mode=FileSystemAccessMode.WRITE),
        ],
        default_mode=FileSystemAccessMode.READ,
    )
    assert len(policy.rules) == 1
    assert policy.deny_hidden is True
    assert policy.deny_git is False


def test_file_system_sandbox_policy_defaults():
    policy = FileSystemSandboxPolicy()
    assert policy.rules == []
    assert policy.default_mode == FileSystemAccessMode.READ


def test_network_sandbox_policy():
    assert NetworkSandboxPolicy.ALLOW_ALL.value == "allow_all"
    assert NetworkSandboxPolicy.BLOCK_ALL.value == "block_all"
    assert NetworkSandboxPolicy.ALLOW_LIST.value == "allow_list"


def test_sandbox_permissions():
    perms = SandboxPermissions(
        filesystem=FileSystemSandboxPolicy(),
        network=NetworkSandboxPolicy.ALLOW_ALL,
        timeout_ms=30_000,
    )
    assert perms.timeout_ms == 30_000


def test_sandbox_permissions_defaults():
    perms = SandboxPermissions()
    assert perms.filesystem.default_mode == FileSystemAccessMode.READ
    assert perms.network == NetworkSandboxPolicy.ALLOW_ALL
    assert perms.env_passthrough == []
