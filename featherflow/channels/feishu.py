"""Feishu (Lark) channel — WebSocket long-connection inbound, HTTP API outbound."""

from __future__ import annotations

import asyncio
import json
import threading
from typing import Any

from loguru import logger

from featherflow.bus.events import OutboundMessage
from featherflow.bus.queue import MessageBus
from featherflow.channels.base import BaseChannel
from featherflow.config.schema import FeishuChannelConfig


class FeishuChannel(BaseChannel):
    """
    Feishu channel using lark-oapi WebSocket long connection.

    - **Inbound**: Feishu server pushes events over WebSocket (no public IP needed).
    - **Outbound**: Feishu HTTP API via lark-oapi Client (for progress/hint messages).

    Main agent responses should be sent via the feishu-mcp MCP tool
    ``mcp_feishu_send_message`` / ``mcp_feishu_reply_message`` so that the
    agent itself controls formatting and threading.
    """

    name = "feishu"

    def __init__(self, config: FeishuChannelConfig, bus: MessageBus):
        super().__init__(config, bus)
        self.config: FeishuChannelConfig = config
        self._ws_thread: threading.Thread | None = None
        self._ws_client: Any = None   # lark.ws.Client — assigned on start()
        self._api_client: Any = None  # lark.Client   — assigned on start()
        self._loop: asyncio.AbstractEventLoop | None = None

    # ------------------------------------------------------------------
    # BaseChannel interface
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the WebSocket long connection in a daemon background thread."""
        import lark_oapi as lark

        self._loop = asyncio.get_event_loop()
        self._running = True

        # HTTP API client reused for all outbound sends
        self._api_client = (
            lark.Client.builder()
            .app_id(self.config.app_id)
            .app_secret(self.config.app_secret)
            .build()
        )

        # Register event handler for incoming @bot / DM messages
        handler = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(self._on_message_receive)
            .build()
        )

        # WebSocket client — .start() is blocking, so run in a daemon thread
        self._ws_client = lark.ws.Client(
            self.config.app_id,
            self.config.app_secret,
            event_handler=handler,
            log_level=lark.LogLevel.INFO,
        )

        self._ws_thread = threading.Thread(
            target=self._ws_client.start,
            daemon=True,
            name="feishu-ws",
        )
        self._ws_thread.start()
        logger.info("Feishu WebSocket long connection started (app_id={}...)", self.config.app_id[:12])

        # Keep the async coroutine alive until stopped
        while self._running:
            await asyncio.sleep(1)

    async def stop(self) -> None:
        """Stop the channel. The daemon WS thread will exit with the process."""
        self._running = False
        logger.info("Feishu channel stopped")

    async def send(self, msg: OutboundMessage) -> None:
        """
        Send a message to the Feishu chat via the HTTP API.

        Used for progress updates and tool hints (controlled by
        ``channels.sendProgress`` / ``channels.sendToolHints`` config).
        """
        if not self._api_client:
            return
        try:
            import lark_oapi as lark

            content_json = json.dumps({"text": msg.content}, ensure_ascii=False)
            request = (
                lark.im.v1.CreateMessageRequest.builder()
                .receive_id_type("chat_id")
                .request_body(
                    lark.im.v1.CreateMessageRequestBody.builder()
                    .receive_id(msg.chat_id)
                    .msg_type("text")
                    .content(content_json)
                    .build()
                )
                .build()
            )
            # run_in_executor so we don't block the event loop
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self._api_client.im.v1.message.create(request),
            )
        except Exception as e:
            logger.error("Feishu send error: {}", e)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_message_receive(self, data: Any) -> None:
        """
        lark-oapi event callback (runs in the WS daemon thread).

        Parses the Feishu message event and forwards it to the MessageBus
        via ``asyncio.run_coroutine_threadsafe`` so it executes on the
        main event loop.
        """
        try:
            msg = data.event.message
            sender = data.event.sender

            chat_id: str = msg.chat_id or ""
            sender_id: str = sender.sender_id.open_id or ""

            # Feishu message content is JSON-encoded, e.g. {"text": "hello"}
            raw: str = msg.content or "{}"
            try:
                text: str = json.loads(raw).get("text", raw).strip()
            except json.JSONDecodeError:
                text = raw.strip()

            if not text:
                return

            if self._loop and self._loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    self._handle_message(
                        sender_id=sender_id,
                        chat_id=chat_id,
                        content=text,
                        metadata={
                            "msg_type": msg.msg_type,
                            "message_id": msg.message_id,
                        },
                    ),
                    self._loop,
                )
        except Exception as e:
            logger.error("Feishu _on_message_receive error: {}", e)
