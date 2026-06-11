"""Tests for runtime tool registry factory (Phase 22)."""

import pytest


def test_runtime_tool_registry_factory_registers_core_tools(fake_config, tmp_path):
    """The factory registers exec, filesystem, spawn, plan, and office tools."""
    from unittest.mock import MagicMock

    from miqi.runtime.tool_registry_factory import create_runtime_tool_registry

    # Create minimal PlanTracker mock so plan tools register
    plan_tracker = MagicMock()

    registry = create_runtime_tool_registry(
        config=fake_config,
        workspace=tmp_path,
        approval_callback=None,
        sandbox_manager=None,
        plan_tracker=plan_tracker,
    )

    names = set(registry.tool_names)

    # Core tools always registered
    assert "exec" in names
    assert "read_file" in names
    assert "write_file" in names
    assert "list_dir" in names
    assert "edit_file" in names

    # Web tools
    assert "web_search" in names
    assert "web_fetch" in names

    # Paper tools
    assert "paper_search" in names
    assert "paper_get" in names
    assert "paper_download" in names

    # Skill manage
    assert "skill_manage" in names

    # Office document tools
    assert "docx_read" in names
    assert "docx_write" in names
    assert "pptx_read" in names
    assert "pptx_write" in names
    assert "xlsx_read" in names
    assert "xlsx_write" in names

    # Plan tools (require plan_tracker)
    assert "plan_create" in names
    assert "plan_update" in names


def test_tool_registry_factory_spawn_requires_subagent_manager(fake_config, tmp_path):
    """Spawn tool is only registered when subagent_manager is provided."""
    from miqi.runtime.tool_registry_factory import create_runtime_tool_registry

    registry = create_runtime_tool_registry(
        config=fake_config,
        workspace=tmp_path,
    )

    names = set(registry.tool_names)
    assert "spawn" not in names


def test_tool_registry_factory_optional_tools(fake_config, tmp_path):
    """Optional tools are registered when their dependencies are provided."""
    from unittest.mock import MagicMock

    from miqi.runtime.tool_registry_factory import create_runtime_tool_registry

    registry = create_runtime_tool_registry(
        config=fake_config,
        workspace=tmp_path,
        memory_store=MagicMock(),
        trace_store=MagicMock(),
        session_manager=MagicMock(),
        bus=MagicMock(),
        subagent_manager=MagicMock(),
        cron_service=MagicMock(),
        plan_tracker=MagicMock(),
    )

    names = set(registry.tool_names)

    assert "memory" in names
    assert "task_begin" in names
    assert "task_end" in names
    assert "trace_search" in names
    assert "session_search" in names
    assert "message" in names
    assert "spawn" in names
    assert "cron" in names
    assert "plan_create" in names
    assert "plan_update" in names


def test_tool_registry_factory_registration_order_is_stable(fake_config, tmp_path):
    """Tool registration order must be deterministic for model tool specs."""
    from unittest.mock import MagicMock

    from miqi.runtime.tool_registry_factory import create_runtime_tool_registry

    plan_tracker = MagicMock()
    registry1 = create_runtime_tool_registry(
        config=fake_config, workspace=tmp_path, plan_tracker=plan_tracker,
    )
    registry2 = create_runtime_tool_registry(
        config=fake_config, workspace=tmp_path, plan_tracker=plan_tracker,
    )

    assert registry1.tool_names == registry2.tool_names
