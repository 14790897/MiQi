"""
auth.py - WeCom AI Bot connection management

Manages the global WSClient instance (botId + secret authentication).
The WebSocket long connection is shared across all tool modules.
"""

import asyncio
import logging
import os
from typing import Callable, Coroutine

from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# Lazy-initialized WSClient singleton
_ws_client = None
_ws_lock = asyncio.Lock()


def get_bot_id() -> str:
    v = os.getenv("WECOM_BOT_ID", "")
    if not v or v.startswith("aib5xg2K_xxx"):
        raise EnvironmentError(
            "WECOM_BOT_ID is not configured. "
            "Copy .env.example to .env and fill in your bot credentials "
            "(WeCom Admin → Workbench → Smart Bot → API Mode)."
        )
    return v


def get_bot_secret() -> str:
    v = os.getenv("WECOM_BOT_SECRET", "")
    if not v or v.startswith("your_bot_secret"):
        raise EnvironmentError(
            "WECOM_BOT_SECRET is not configured. "
            "Copy .env.example to .env and fill in your bot secret."
        )
    return v


def get_welcome_message() -> str:
    return os.getenv("WECOM_WELCOME_MESSAGE", "")


async def get_client():
    """Return the shared WSClient instance, connecting on first call."""
    global _ws_client
    if _ws_client is not None and _ws_client.is_connected:
        return _ws_client

    async with _ws_lock:
        # Double-check after acquiring lock
        if _ws_client is not None and _ws_client.is_connected:
            return _ws_client

        from wecom_aibot_sdk import WSClient

        _ws_client = WSClient(
            bot_id=get_bot_id(),
            secret=get_bot_secret(),
        )

        logger.info("Connecting to WeCom AI Bot WebSocket...")
        await _ws_client.connect()
        logger.info("WeCom AI Bot connected and authenticated")
        return _ws_client


async def disconnect_client():
    """Gracefully disconnect the WSClient."""
    global _ws_client
    if _ws_client is not None:
        try:
            await _ws_client.disconnect()
            logger.info("WeCom AI Bot disconnected")
        except Exception as e:
            logger.warning("Error disconnecting: %s", e)
        _ws_client = None
