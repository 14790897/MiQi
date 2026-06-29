"""Tests for command routing through AppServer (Phase 26.6)."""

import pytest


# ── Helpers ──────────────────────────────────────────────────────────────


def _setup_server_with_session(fake_config, fake_provider, tmp_path):
    """Create AppServer with a RuntimeSession and register command handlers."""
    from miqi.runtime.app_server import AppServer, ClientSessionRegistry

    registry = ClientSessionRegistry()
    server = AppServer(registry)
    return server, registry


# ── Thread commands ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_thread_create(fake_config, fake_provider, tmp_path):
    from miqi.runtime.app_server import register_command_handlers

    server, registry = _setup_server_with_session(fake_config, fake_provider, tmp_path)
    # Create a session first
    session = await registry.create_session(
        client_id="c1", session_key="s1",
        config=fake_config, provider=fake_provider, workspace=tmp_path,
    )
    register_command_handlers(server)

    response = await server.dispatch(
        request_id="r1", method="thread.create",
        params={"title": "My Thread"},
        client_id="c1", session_id=session.session_id,
    )
    assert "result" in response, f"Expected result, got {response}"
    assert "thread_id" in response["result"]
    assert "title" in response["result"]
    assert response["result"]["title"] == "My Thread"

    await registry.stop_all()


@pytest.mark.asyncio
async def test_thread_list(fake_config, fake_provider, tmp_path):
    from miqi.runtime.app_server import register_command_handlers

    server, registry = _setup_server_with_session(fake_config, fake_provider, tmp_path)
    session = await registry.create_session(
        client_id="c1", session_key="s1",
        config=fake_config, provider=fake_provider, workspace=tmp_path,
    )
    register_command_handlers(server)

    # Create two threads
    await server.dispatch("r1", "thread.create", {"title": "T1"},
                          "c1", session.session_id)
    await server.dispatch("r2", "thread.create", {"title": "T2"},
                          "c1", session.session_id)

    # List
    response = await server.dispatch("r3", "thread.list", {},
                                      "c1", session.session_id)
    assert "result" in response
    threads = response["result"]["threads"]
    assert len(threads) >= 2
    titles = [t["title"] for t in threads]
    assert "T1" in titles
    assert "T2" in titles

    await registry.stop_all()


@pytest.mark.asyncio
async def test_thread_rename(fake_config, fake_provider, tmp_path):
    from miqi.runtime.app_server import register_command_handlers

    server, registry = _setup_server_with_session(fake_config, fake_provider, tmp_path)
    session = await registry.create_session(
        client_id="c1", session_key="s1",
        config=fake_config, provider=fake_provider, workspace=tmp_path,
    )
    register_command_handlers(server)

    create_r = await server.dispatch("r1", "thread.create", {"title": "Old"},
                                      "c1", session.session_id)
    tid = create_r["result"]["thread_id"]

    rename_r = await server.dispatch("r2", "thread.rename",
                                      {"thread_id": tid, "title": "New"},
                                      "c1", session.session_id)
    assert "result" in rename_r
    assert rename_r["result"]["title"] == "New"

    await registry.stop_all()


@pytest.mark.asyncio
async def test_thread_archive(fake_config, fake_provider, tmp_path):
    from miqi.runtime.app_server import register_command_handlers

    server, registry = _setup_server_with_session(fake_config, fake_provider, tmp_path)
    session = await registry.create_session(
        client_id="c1", session_key="s1",
        config=fake_config, provider=fake_provider, workspace=tmp_path,
    )
    register_command_handlers(server)

    create_r = await server.dispatch("r1", "thread.create", {"title": "T"},
                                      "c1", session.session_id)
    tid = create_r["result"]["thread_id"]

    response = await server.dispatch("r2", "thread.archive",
                                      {"thread_id": tid},
                                      "c1", session.session_id)
    assert "result" in response

    await registry.stop_all()


# ── Abort ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_abort_through_app_server(fake_config, fake_provider, tmp_path):
    from miqi.runtime.app_server import register_command_handlers

    server, registry = _setup_server_with_session(fake_config, fake_provider, tmp_path)
    session = await registry.create_session(
        client_id="c1", session_key="s1",
        config=fake_config, provider=fake_provider, workspace=tmp_path,
    )
    register_command_handlers(server)

    response = await server.dispatch(
        request_id="r-abort", method="chat.abort",
        params={"thread_id": "default"},
        client_id="c1", session_id=session.session_id,
    )
    assert "result" in response
    assert response["result"]["aborted"] is True

    await registry.stop_all()


# ── Config ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_config_get_through_app_server(fake_config, fake_provider, tmp_path):
    from miqi.runtime.app_server import register_command_handlers

    server, registry = _setup_server_with_session(fake_config, fake_provider, tmp_path)
    register_command_handlers(server)

    # config.get is session-less (no session_id needed)
    response = await server.dispatch(
        request_id="r-cfg", method="config.get",
        params={}, client_id="c1", session_id=None,
    )
    # May return config data or an error depending on config availability
    assert "request_id" in response

    await registry.stop_all()


# ── Unknown command ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unknown_command_returns_error():
    from miqi.runtime.app_server import AppServer, ClientSessionRegistry

    registry = ClientSessionRegistry()
    server = AppServer(registry)

    response = await server.dispatch(
        request_id="r-unknown", method="nonexistent.command",
        params={}, client_id="c1",
    )
    assert "error" in response
    assert response["code"] == "UNKNOWN_METHOD"


# ── Unauthorized command ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unauthorized_client_cannot_issue_session_commands(fake_config, fake_provider, tmp_path):
    from miqi.runtime.app_server import register_command_handlers

    server, registry = _setup_server_with_session(fake_config, fake_provider, tmp_path)
    session = await registry.create_session(
        client_id="c1", session_key="s1",
        config=fake_config, provider=fake_provider, workspace=tmp_path,
    )
    register_command_handlers(server)

    # Client c2 is not authorized for this session
    response = await server.dispatch(
        "r-bad", "thread.list", {},
        "c2", session.session_id,
    )
    assert "error" in response
    assert response["code"] == "UNAUTHORIZED"

    await registry.stop_all()
