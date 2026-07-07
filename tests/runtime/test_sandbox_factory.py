"""Tests for runtime sandbox manager construction."""


def test_create_sandbox_manager_from_config_enabled(fake_config):
    from miqi.runtime.sandbox_factory import create_sandbox_manager_from_config

    manager = create_sandbox_manager_from_config(
        config=fake_config,
        workspace=fake_config.workspace_path,
    )

    assert manager is not None
    assert manager.workspace == fake_config.workspace_path
    assert manager.enabled is True


def test_create_sandbox_manager_from_config_disabled(fake_config):
    from miqi.runtime.sandbox_factory import create_sandbox_manager_from_config

    fake_config.tools.sandbox.enabled = False

    manager = create_sandbox_manager_from_config(
        config=fake_config,
        workspace=fake_config.workspace_path,
    )

    assert manager is None
