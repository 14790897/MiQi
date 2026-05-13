"""
tools/messages.py - WeCom AI Bot messaging utilities

Provides:
- send_message: proactively send a message to a user or group chat
- reply_message: reply to a received message (passive reply via WebSocket frame)

Based on wecom-aibot-sdk WSClient.
"""

import json
import logging
from typing import Any

from wecom_mcp.auth import get_client

logger = logging.getLogger(__name__)


def _build_msg_body(msgtype: str, content: str | dict) -> dict:
    """Build the typed message body from msgtype and raw content string."""
    if isinstance(content, dict):
        content = json.dumps(content, ensure_ascii=False)

    body: dict[str, Any] = {"msgtype": msgtype}

    if msgtype == "text":
        body["text"] = {"content": content}
    elif msgtype == "markdown":
        body["markdown"] = {"content": content}
    elif msgtype in ("image", "voice", "file"):
        body[msgtype] = {"media_id": content}
    elif msgtype == "video":
        try:
            video_data = json.loads(content) if isinstance(content, str) else content
            body["video"] = {
                "media_id": video_data.get("media_id", content),
                "title": video_data.get("title", ""),
                "description": video_data.get("description", ""),
            }
        except (json.JSONDecodeError, TypeError):
            body["video"] = {"media_id": content}
    elif msgtype == "textcard":
        try:
            card_data = json.loads(content) if isinstance(content, str) else content
            body["textcard"] = {
                "title": card_data.get("title", ""),
                "description": card_data.get("description", ""),
                "url": card_data.get("url", ""),
                "btntxt": card_data.get("btntxt", "Details"),
            }
        except (json.JSONDecodeError, TypeError):
            body["text"] = {"content": content}
    elif msgtype == "news":
        try:
            news_data = json.loads(content) if isinstance(content, str) else content
            body["news"] = {
                "articles": news_data.get("articles", news_data)
                if isinstance(news_data, dict)
                else news_data
            }
        except (json.JSONDecodeError, TypeError):
            body["text"] = {"content": content}
    elif msgtype == "template_card":
        try:
            card_data = json.loads(content) if isinstance(content, str) else content
            body["template_card"] = card_data
        except (json.JSONDecodeError, TypeError):
            body["text"] = {"content": content}
    else:
        body["text"] = {"content": content}

    return body


async def send_message(
    chatid: str,
    msgtype: str = "text",
    content: str | dict = "",
) -> dict:
    """
    Proactively send a message to a user (userid) or group chat (chatid).

    Args:
        chatid: Target ID — userid for private chat, chatid for group chat.
        msgtype: Message type: text, markdown, image, file, voice, video,
                 textcard, news, template_card.
        content: Message content. For text/markdown: plain string.
                 For image/voice/file: media_id.
                 For video/textcard/news/template_card: JSON string or dict.

    Returns:
        WebSocket response frame dict.
    """
    client = await get_client()
    body = _build_msg_body(msgtype, content)

    logger.info("Sending message to %s: msgtype=%s", chatid, msgtype)
    result = await client.send_message(chatid, body)
    return _frame_to_dict(result)


async def reply_message(
    req_id: str,
    msgtype: str = "text",
    content: str | dict = "",
) -> dict:
    """
    Reply to a received message (passive reply).

    This is typically called by the webhook message handler with the
    req_id from the incoming WebSocket frame.

    Args:
        req_id: The request ID from the incoming message frame headers.
        msgtype: Message type (same as send_message).
        content: Message content (same as send_message).

    Returns:
        WebSocket response frame dict.
    """
    client = await get_client()
    body = _build_msg_body(msgtype, content)

    logger.info("Replying to req_id=%s: msgtype=%s", req_id, msgtype)
    # Build a minimal frame for the reply
    frame = {
        "cmd": "aibot_respond_msg",
        "headers": {"req_id": req_id},
        "body": body,
    }
    result = await client.reply(frame, body)
    return _frame_to_dict(result)


def _frame_to_dict(frame) -> dict:
    """Convert a WsFrame object to a plain dict for JSON serialization."""
    if hasattr(frame, "model_dump"):
        return frame.model_dump()
    if hasattr(frame, "__dict__"):
        return frame.__dict__
    return dict(frame) if isinstance(frame, (dict, list)) else {"result": str(frame)}
