"""
webhook/handler.py - WeCom AI Bot event callback handler

Listens to WebSocket events from the AI Bot SDK and dispatches them.
No HTTP server needed — all events arrive via the WebSocket long connection.

Events handled:
- event.enter_chat → send welcome message
- message.* → log and optionally forward to Agent via callback
"""

import json
import logging
from typing import Any, Callable, Coroutine

from dotenv import load_dotenv

from wecom_mcp.auth import get_client, get_welcome_message

load_dotenv()
logger = logging.getLogger(__name__)

# Optional message callback: (sender_id, chatid, content, msg_type, frame) -> None
_message_callback: Callable | None = None


def set_message_callback(cb: Callable | None) -> None:
    """Register a callback for incoming messages (e.g. forward to Agent)."""
    global _message_callback
    _message_callback = cb


def _frame_to_dict(frame) -> dict:
    """Convert a WsFrame object to a plain dict."""
    if hasattr(frame, "model_dump"):
        return frame.model_dump()
    if hasattr(frame, "__dict__"):
        return frame.__dict__
    return dict(frame) if isinstance(frame, (dict, list)) else {"result": str(frame)}


async def register_handlers() -> None:
    """Register all event handlers on the shared WSClient.

    Must be called after get_client() has established the connection.
    """
    client = await get_client()

    # ── Connection lifecycle ──
    def on_authenticated():
        logger.info("WeCom AI Bot authenticated successfully")

    def on_disconnected(reason: str):
        logger.warning("WeCom AI Bot disconnected: %s", reason)

    def on_reconnecting(attempt: int):
        logger.info("WeCom AI Bot reconnecting (attempt %d)...", attempt)

    def on_error(error: Exception):
        logger.error("WeCom AI Bot error: %s", error)

    client.on("authenticated", on_authenticated)
    client.on("disconnected", on_disconnected)
    client.on("reconnecting", on_reconnecting)
    client.on("error", on_error)

    # ── Enter chat → welcome message ──
    async def on_enter_chat(frame):
        welcome = get_welcome_message()
        if not welcome:
            return
        try:
            await client.reply_welcome(frame, {
                "msgtype": "text",
                "text": {"content": welcome},
            })
            logger.info("Welcome message sent")
        except Exception as e:
            logger.error("Failed to send welcome message: %s", e)

    client.on("event.enter_chat", on_enter_chat)

    # ── Message handlers ──
    async def on_message(frame):
        """Route all incoming messages to typed handlers and callback."""
        try:
            body = frame.get("body", {})
            headers = frame.get("headers", {})
            msg_type = body.get("msgtype", "text")
            req_id = headers.get("req_id", "")

            # Extract sender info
            from_info = body.get("from", {})
            sender_id = from_info.get("userid", "") if isinstance(from_info, dict) else ""
            chatid = body.get("chatid", "")
            chat_type = body.get("chattype", "single")

            # Extract text content
            content = ""
            if msg_type == "text":
                content = (body.get("text") or {}).get("content", "")
            elif msg_type == "voice":
                content = (body.get("voice") or {}).get("content", "")
            elif msg_type == "mixed":
                # Mixed messages contain a list of items
                items = body.get("mixed", {}).get("content_list", [])
                text_parts = [item.get("text", {}).get("content", "") for item in items if item.get("text")]
                content = "\n".join(text_parts)
            elif msg_type in ("image", "file", "video"):
                # Media messages — extract URL info
                media = body.get(msg_type, {})
                content = json.dumps({
                    "url": media.get("url", ""),
                    "aeskey": media.get("aeskey", ""),
                }, ensure_ascii=False)
            else:
                content = json.dumps(body.get(msg_type, {}), ensure_ascii=False)

            logger.info(
                "Received message | sender=%s | chatid=%s | type=%s | content=%s",
                sender_id, chatid, msg_type, content[:100],
            )

            # Forward to registered callback (e.g. Agent)
            if _message_callback:
                await _message_callback(
                    sender_id=sender_id,
                    chatid=chatid,
                    content=content,
                    msg_type=msg_type,
                    frame=_frame_to_dict(frame),
                )

        except Exception as e:
            logger.error("Error processing incoming message: %s", e, exc_info=True)

    # Register typed message handlers
    for event_name in ("message", "message.text", "message.image", "message.mixed",
                       "message.voice", "message.file"):
        client.on(event_name, on_message)

    logger.info("WebSocket event handlers registered")
