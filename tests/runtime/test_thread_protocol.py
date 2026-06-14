"""Tests for Codex-style thread protocol serialization types."""

from miqi.runtime.thread_protocol import (
    ThreadItemView,
    ThreadStatusView,
    ThreadView,
    TurnView,
    page_items,
)


def test_thread_status_serializes_codex_style():
    assert ThreadStatusView("idle").to_dict() == {"type": "idle"}
    assert ThreadStatusView("running").to_dict() == {"type": "running"}
    assert ThreadStatusView("archived").to_dict() == {"type": "archived"}


def test_thread_view_serializes_camel_case_fields():
    thread = ThreadView(
        id="thread-1",
        session_id="client:default",
        status=ThreadStatusView("idle"),
        name="Example",
        parent_thread_id="parent-1",
        forked_from_id="source-1",
        archived=False,
        ephemeral=False,
        turns=[],
        created_at=1.0,
        updated_at=2.0,
        items_view="notLoaded",
    )
    data = thread.to_dict()
    assert data["id"] == "thread-1"
    assert data["sessionId"] == "client:default"
    assert data["parentThreadId"] == "parent-1"
    assert data["forkedFromId"] == "source-1"
    assert data["itemsView"] == "notLoaded"
    assert data["status"]["type"] == "idle"
    assert data["turns"] == []


def test_turn_view_summary_items():
    turn = TurnView(
        id="turn-1",
        thread_id="thread-1",
        status="completed",
        items_view="summary",
        items=[
            ThreadItemView(type="userMessage", id="u1", payload={
                "content": [{"type": "text", "text": "hello"}],
            }),
            ThreadItemView(type="agentMessage", id="a1", payload={
                "text": "hi",
            }),
        ],
        started_at=1.0,
        completed_at=2.0,
    )
    data = turn.to_dict()
    assert data["threadId"] == "thread-1"
    assert data["items"][0]["type"] == "userMessage"
    assert data["items"][1]["text"] == "hi"
    assert data["startedAt"] == 1.0
    assert data["completedAt"] == 2.0


def test_turn_view_none_timestamps_omitted():
    turn = TurnView(
        id="turn-1",
        thread_id="t1",
        status="incomplete",
        items_view="notLoaded",
        items=[],
        started_at=None,
        completed_at=None,
    )
    data = turn.to_dict()
    assert "startedAt" not in data
    assert "completedAt" not in data


def test_page_items_desc_uses_numeric_cursor():
    values = ["t1", "t2", "t3", "t4"]
    page = page_items(values, limit=2, cursor=None, sort_direction="desc")
    assert page.data == ["t4", "t3"]
    assert page.next_cursor == "2"
    assert page.backwards_cursor == "0"


def test_page_items_asc_uses_numeric_cursor():
    values = ["a", "b", "c", "d", "e"]
    page = page_items(values, limit=3, cursor=None, sort_direction="asc")
    assert page.data == ["a", "b", "c"]
    assert page.next_cursor == "3"
    assert page.backwards_cursor == "0"


def test_page_items_with_cursor():
    values = ["a", "b", "c", "d", "e"]
    page = page_items(values, limit=2, cursor="2", sort_direction="asc")
    assert page.data == ["c", "d"]
    assert page.next_cursor == "4"


def test_page_items_limit_max_200():
    values = ["x"] * 300
    page = page_items(values, limit=500, cursor=None, sort_direction="asc")
    assert len(page.data) == 200  # capped


def test_page_serializes_codex_style():
    from miqi.runtime.thread_protocol import Page
    page = Page(data=["a", "b"], next_cursor="2", backwards_cursor="0")
    d = page.to_dict()
    assert d == {"data": ["a", "b"], "nextCursor": "2", "backwardsCursor": "0"}
