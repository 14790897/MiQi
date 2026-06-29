from __future__ import annotations

import pytest

from miqi.runtime.app_server import AppServerError
from miqi.runtime.turn_request_models import (
    ThreadCompactStartParams,
    ThreadInjectItemsParams,
    TurnInterruptParams,
    TurnStartParams,
    TurnSteerParams,
    validate_turn_params,
)


def test_turn_start_accepts_camel_case_and_normalizes_input_items():
    params = validate_turn_params(
        TurnStartParams,
        {
            "threadId": "thread-1",
            "clientUserMessageId": "client-msg-1",
            "input": [{"type": "text", "text": "hello"}],
            "model": "test-model",
        },
    )

    assert params.thread_id == "thread-1"
    assert params.client_user_message_id == "client-msg-1"
    assert params.input_items == [{"type": "text", "text": "hello"}]
    assert params.content == "hello"
    assert params.settings_overrides == {"model": "test-model"}


def test_turn_start_accepts_existing_snake_case_aliases():
    params = validate_turn_params(
        TurnStartParams,
        {
            "thread_id": "thread-1",
            "client_user_message_id": "client-msg-1",
            "input": [{"type": "text", "text": "hello"}],
        },
    )

    assert params.thread_id == "thread-1"
    assert params.client_user_message_id == "client-msg-1"


def test_turn_start_rejects_input_without_text_content():
    with pytest.raises(AppServerError) as exc:
        validate_turn_params(
            TurnStartParams,
            {
                "threadId": "thread-1",
                "input": [{"type": "image", "url": "https://example.com/image.png"}],
            },
        )

    assert exc.value.code == "INVALID_PARAMS"


def test_turn_interrupt_accepts_aliases():
    params = validate_turn_params(
        TurnInterruptParams,
        {"thread_id": "thread-1", "turn_id": "turn-1"},
    )

    assert params.thread_id == "thread-1"
    assert params.turn_id == "turn-1"


def test_turn_steer_accepts_expected_turn_alias():
    params = validate_turn_params(
        TurnSteerParams,
        {
            "thread_id": "thread-1",
            "expected_turn_id": "turn-1",
            "input": [{"type": "text", "text": "steer"}],
        },
    )

    assert params.thread_id == "thread-1"
    assert params.expected_turn_id == "turn-1"
    assert params.content == "steer"


def test_thread_compact_start_requires_thread_id():
    with pytest.raises(AppServerError) as exc:
        validate_turn_params(ThreadCompactStartParams, {})

    assert exc.value.code == "INVALID_PARAMS"


def test_thread_inject_items_requires_non_empty_items():
    with pytest.raises(AppServerError) as exc:
        validate_turn_params(ThreadInjectItemsParams, {"threadId": "thread-1", "items": []})

    assert exc.value.code == "INVALID_PARAMS"


def test_thread_inject_items_accepts_items():
    params = validate_turn_params(
        ThreadInjectItemsParams,
        {
            "threadId": "thread-1",
            "items": [{"type": "message", "role": "assistant", "content": "context"}],
        },
    )

    assert params.thread_id == "thread-1"
    assert params.items == [{"type": "message", "role": "assistant", "content": "context"}]
