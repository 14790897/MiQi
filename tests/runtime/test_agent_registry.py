"""Tests for miqi.runtime.agent_registry."""

import pytest
from miqi.runtime.agent_registry import AgentMetadata, AgentRegistry


def test_agent_metadata_creation():
    meta = AgentMetadata(
        name="test-agent",
        display_name="Test Agent",
        description="A test agent",
        system_prompt="You are a test agent.",
        available_tools=["read_file", "exec"],
    )
    assert meta.name == "test-agent"
    assert meta.is_builtin is True
    assert meta.max_iterations == 40


def test_registry_register_and_resolve():
    registry = AgentRegistry()
    meta = registry.resolve("main")
    assert meta.name == "main"
    assert meta.display_name == "MiQi"


def test_registry_has_builtins():
    registry = AgentRegistry()
    agents = registry.list_agents()
    names = {a.name for a in agents}
    assert "main" in names
    assert "code-agent" in names
    assert "doc-agent" in names
    assert "research-agent" in names


def test_registry_register_duplicate_raises():
    registry = AgentRegistry()
    meta = AgentMetadata(
        name="main",
        display_name="Duplicate",
        description="...",
        system_prompt="...",
        available_tools=[],
    )
    with pytest.raises(ValueError, match="already registered"):
        registry.register(meta)


def test_registry_resolve_unknown_raises():
    registry = AgentRegistry()
    with pytest.raises(KeyError, match="Unknown agent type"):
        registry.resolve("nonexistent")


def test_main_agent_has_office_tools():
    registry = AgentRegistry()
    main = registry.resolve("main")
    assert "docx_read" in main.available_tools
    assert "pptx_write" in main.available_tools


def test_code_agent_has_no_office_tools():
    registry = AgentRegistry()
    code = registry.resolve("code-agent")
    assert "docx_write" not in code.available_tools


def test_code_agent_has_fewer_iterations():
    registry = AgentRegistry()
    code = registry.resolve("code-agent")
    assert code.max_iterations == 25


def test_doc_agent_has_fewer_iterations():
    registry = AgentRegistry()
    doc = registry.resolve("doc-agent")
    assert doc.max_iterations == 20


def test_research_agent_has_fewer_iterations():
    registry = AgentRegistry()
    research = registry.resolve("research-agent")
    assert research.max_iterations == 15


def test_all_agents_have_system_prompts():
    registry = AgentRegistry()
    for agent in registry.list_agents():
        assert len(agent.system_prompt) > 50
        assert len(agent.available_tools) > 0


def test_custom_agent_registration():
    registry = AgentRegistry()
    custom = AgentMetadata(
        name="custom-agent",
        display_name="Custom",
        description="A custom agent",
        system_prompt="You are custom.",
        available_tools=["read_file"],
        max_iterations=10,
        model_override="gpt-4",
        is_builtin=False,
    )
    registry.register(custom)
    resolved = registry.resolve("custom-agent")
    assert resolved.model_override == "gpt-4"
    assert resolved.is_builtin is False
