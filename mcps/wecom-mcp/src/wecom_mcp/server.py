"""
server.py - WeCom AI Bot MCP Server entry point

Registers all tools and starts the MCP Server over stdio.
Also establishes the WebSocket long connection to WeCom AI Bot.

Startup (stdio mode, for MiQi / Claude Desktop / Cursor integration):
  python -m wecom_mcp.server

Example MiQi configuration (mcp.json):
  {
    "wecom-mcp": {
      "command": "python",
      "args": ["-m", "wecom_mcp.server"],
      "env": { "WECOM_BOT_ID": "...", "WECOM_BOT_SECRET": "..." }
    }
  }
"""

import asyncio
import json
import logging
import os
from typing import Any

from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

load_dotenv()

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = Server("wecom-mcp")


# ─────────────────────────────────────────
# Tool definitions (Tool Schema)
# ─────────────────────────────────────────

TOOLS: list[Tool] = [
    # ── Messages ──
    Tool(
        name="send_message",
        description=(
            "Send a message to a WeCom user (private chat) or group chat. "
            "For private chat, chatid is the user's userid. "
            "For group chat, chatid is the group chat ID. "
            "Supports text, markdown, image (media_id), file (media_id), "
            "video (JSON with media_id/title/description), "
            "textcard (JSON with title/description/url), news (JSON with articles), "
            "and template_card (JSON with card_type)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "chatid": {
                    "type": "string",
                    "description": "Target ID: userid for private chat, chatid for group chat.",
                },
                "msgtype": {
                    "type": "string",
                    "enum": ["text", "markdown", "image", "file", "video", "voice", "textcard", "news", "template_card"],
                    "description": "Message type. Default: text.",
                    "default": "text",
                },
                "content": {
                    "type": "string",
                    "description": (
                        "Message content. For text/markdown: plain string. "
                        "For image/voice/file: media_id (from upload_media). "
                        'For video: JSON {"media_id":"...","title":"...","description":"..."}. '
                        'For textcard: JSON {"title":"...","description":"...","url":"...","btntxt":"..."}. '
                        'For news: JSON {"articles":[{"title":"...","url":"...","picurl":"..."}]}. '
                        'For template_card: JSON {"card_type":"text_notice","main_title":{"title":"..."}}.'
                    ),
                },
            },
            "required": ["chatid", "msgtype", "content"],
        },
    ),
    Tool(
        name="reply_message",
        description=(
            "Reply to a received message (passive reply). Use this when handling "
            "an incoming WeCom message to respond in the same conversation thread. "
            "The req_id must come from the incoming message's headers."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "req_id": {
                    "type": "string",
                    "description": "Request ID from the incoming message frame headers.",
                },
                "msgtype": {
                    "type": "string",
                    "enum": ["text", "markdown", "image", "file", "video", "voice", "textcard", "news"],
                    "description": "Message type. Default: text.",
                    "default": "text",
                },
                "content": {
                    "type": "string",
                    "description": "Message content (same format as send_message).",
                },
            },
            "required": ["req_id", "msgtype", "content"],
        },
    ),
    # ── Media ──
    Tool(
        name="upload_media",
        description=(
            "Upload a local file to WeCom as temporary media via WebSocket channel. "
            "Returns media_id which can be used in send_message/reply_message "
            "with msgtype=image/file/voice/video. Media is valid for 3 days."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Absolute path to the local file."},
                "media_type": {
                    "type": "string",
                    "enum": ["image", "voice", "video", "file"],
                    "description": "Media type. Default: file.",
                    "default": "file",
                },
            },
            "required": ["file_path"],
        },
    ),
    Tool(
        name="download_media",
        description=(
            "Download an encrypted media file from a WeCom message. "
            "The SDK handles AES decryption automatically. "
            "Returns the local file path after download."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Encrypted media URL from the message."},
                "save_dir": {
                    "type": "string",
                    "description": "Directory to save the file. Default: current directory.",
                    "default": ".",
                },
                "file_name": {
                    "type": "string",
                    "description": "Desired filename. If empty, auto-detected.",
                    "default": "",
                },
                "aes_key": {
                    "type": "string",
                    "description": "AES key from the message (image.aeskey or file.aeskey).",
                    "default": "",
                },
            },
            "required": ["url"],
        },
    ),
]


# ─────────────────────────────────────────
# MCP handlers
# ─────────────────────────────────────────

@app.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Unified tool call entry point; routes to the corresponding function by tool name."""
    try:
        result = await _dispatch(name, arguments)
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
    except Exception as e:
        logger.error("Tool %s execution failed: %s", name, e, exc_info=True)
        return [TextContent(type="text", text=json.dumps({"error": str(e)}, ensure_ascii=False))]


async def _dispatch(name: str, args: dict) -> Any:
    """Dispatch table: tool name -> function call."""
    from wecom_mcp.tools import messages, media

    dispatch_map = {
        "send_message": lambda: messages.send_message(
            args["chatid"],
            args.get("msgtype", "text"),
            args["content"],
        ),
        "reply_message": lambda: messages.reply_message(
            args["req_id"],
            args.get("msgtype", "text"),
            args["content"],
        ),
        "upload_media": lambda: media.upload_media(
            args["file_path"],
            args.get("media_type", "file"),
        ),
        "download_media": lambda: media.download_media(
            args["url"],
            args.get("save_dir", "."),
            args.get("file_name", ""),
            args.get("aes_key", ""),
        ),
    }

    if name not in dispatch_map:
        raise ValueError(f"Unknown tool: {name}")

    return dispatch_map[name]()


# ─────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────

def main():
    logger.info("WeCom MCP Server starting (stdio mode)...")
    asyncio.run(_run())


async def _run():
    # 1. Establish WebSocket connection to WeCom AI Bot
    from wecom_mcp.auth import get_client, disconnect_client
    from wecom_mcp.webhook.handler import register_handlers

    try:
        await get_client()
        await register_handlers()
    except Exception as e:
        logger.error("Failed to connect to WeCom AI Bot: %s", e)
        logger.error("MCP tools will not work until the connection is established.")

    # 2. Start MCP stdio server
    try:
        async with stdio_server() as (read_stream, write_stream):
            await app.run(read_stream, write_stream, app.create_initialization_options())
    finally:
        await disconnect_client()


if __name__ == "__main__":
    main()
