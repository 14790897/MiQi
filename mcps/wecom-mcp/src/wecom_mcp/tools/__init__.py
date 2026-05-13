"""
tools/__init__.py — Tool registry

All MCP tools are exported here; server.py imports directly from this module.
"""

from wecom_mcp.tools.messages import (
    send_message,
    reply_message,
)
from wecom_mcp.tools.media import (
    upload_media,
    download_media,
)

__all__ = [
    # messages
    "send_message",
    "reply_message",
    # media
    "upload_media",
    "download_media",
]
