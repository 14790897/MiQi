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


# ── Phase 32: Office doc write tools enforce workspace boundary ──────────────
#   even with the default restrict_to_workspace=False.


@pytest.mark.asyncio
async def test_factory_docx_write_rejects_outside_workspace_default_config(
    fake_config, tmp_path,
):
    """With default config (restrict_to_workspace=False), docx_write
    must still reject an absolute path outside workspace."""
    from miqi.runtime.tool_registry_factory import create_runtime_tool_registry

    registry = create_runtime_tool_registry(
        config=fake_config, workspace=tmp_path,
    )
    tool = registry.get("docx_write")
    assert tool is not None

    outside = tmp_path.parent / "outside_d.docx"
    result = await tool.execute(file_path=str(outside), content="test")
    assert "Permission denied" in result
    assert not outside.exists()


@pytest.mark.asyncio
async def test_factory_pptx_write_rejects_outside_workspace_default_config(
    fake_config, tmp_path,
):
    """Default config: pptx_write rejects absolute path outside workspace."""
    from miqi.runtime.tool_registry_factory import create_runtime_tool_registry

    registry = create_runtime_tool_registry(
        config=fake_config, workspace=tmp_path,
    )
    tool = registry.get("pptx_write")
    assert tool is not None

    outside = tmp_path.parent / "outside_p.pptx"
    result = await tool.execute(file_path=str(outside), slides=[])
    assert "Permission denied" in result
    assert not outside.exists()


@pytest.mark.asyncio
async def test_factory_xlsx_write_rejects_outside_workspace_default_config(
    fake_config, tmp_path,
):
    """Default config: xlsx_write rejects absolute path outside workspace."""
    from miqi.runtime.tool_registry_factory import create_runtime_tool_registry

    registry = create_runtime_tool_registry(
        config=fake_config, workspace=tmp_path,
    )
    tool = registry.get("xlsx_write")
    assert tool is not None

    outside = tmp_path.parent / "outside_x.xlsx"
    result = await tool.execute(file_path=str(outside), sheets={})
    assert "Permission denied" in result
    assert not outside.exists()


@pytest.mark.asyncio
async def test_factory_docx_write_relative_path_inside_workspace_default_config(
    fake_config, tmp_path,
):
    """Default config: docx_write relative path succeeds inside workspace."""
    from miqi.runtime.tool_registry_factory import create_runtime_tool_registry

    registry = create_runtime_tool_registry(
        config=fake_config, workspace=tmp_path,
    )
    tool = registry.get("docx_write")
    assert tool is not None

    result = await tool.execute(file_path="report.docx", content="# Hi\nTest")
    assert "Created:" in result
    assert (tmp_path / "report.docx").exists()


@pytest.mark.asyncio
async def test_factory_docx_write_path_traversal_rejected_default_config(
    fake_config, tmp_path,
):
    """Default config: docx_write rejects ../ path traversal."""
    from miqi.runtime.tool_registry_factory import create_runtime_tool_registry

    registry = create_runtime_tool_registry(
        config=fake_config, workspace=tmp_path,
    )
    tool = registry.get("docx_write")
    assert tool is not None

    result = await tool.execute(file_path="../escape.docx", content="test")
    assert "Permission denied" in result
    assert not (tmp_path.parent / "escape.docx").exists()


def test_write_file_semantics_unchanged(fake_config, tmp_path):
    """write_file must NOT gain the office-write default-boundary behavior.

    write_file's path enforcement is controlled by restrict_to_workspace
    config, NOT hardcoded to workspace.  Phase 32 only changes office tools.
    """
    from miqi.runtime.tool_registry_factory import create_runtime_tool_registry

    registry = create_runtime_tool_registry(
        config=fake_config, workspace=tmp_path,
    )
    tool = registry.get("write_file")
    assert tool is not None

    # write_file's allowed_dir is None by default (restrict_to_workspace=False)
    assert tool._allowed_dir is None, (
        "write_file._allowed_dir must be None by default — "
        "restrict_to_workspace controls it, not Phase 32"
    )
