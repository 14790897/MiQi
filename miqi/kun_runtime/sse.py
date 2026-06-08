"""Server-Sent Events encoder for KUN runtime events.

Produces the same SSE format as KUN ``server/routes/``:

.. code-block:: text

    id: <seq>
    event: <kind>
    data: <json>

Empty line terminates each event.
"""

from __future__ import annotations

import json
from typing import Any


def encode_sse(event: dict[str, Any]) -> str:
    """Encode a single runtime event dict as an SSE message.

    Returns a string ready to write to an HTTP response body:

        id: 1
        event: turn_started
        data: {"seq":1,...}

    """
    seq = event.get("seq", "")
    kind = event.get("kind", "message")
    data = json.dumps(event, ensure_ascii=False, default=str)
    return f"id: {seq}\nevent: {kind}\ndata: {data}\n\n"


def encode_sse_comment(text: str) -> str:
    """Encode a comment (e.g. keepalive) as an SSE comment line."""
    return f": {text}\n\n"


def encode_stream_final() -> str:
    """Encode the terminal ``[DONE]`` marker that signals end-of-stream."""
    return "data: [DONE]\n\n"
