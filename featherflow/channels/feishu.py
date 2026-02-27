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

        # Capture values for the thread closure
        app_id = self.config.app_id
        app_secret = self.config.app_secret
        on_msg = self._on_message_receive

        def _run_ws() -> None:
            """
            Run the Feishu WebSocket client in a dedicated thread with its
            own event loop.

            lark_oapi/ws/client.py stores a module-level global variable
            ``loop`` that is captured once at import time.  Every internal
            method (start, _connect, _receive_message_loop, _ping_loop, …)
            references that same global ``loop``.  If the module was first
            imported while the main asyncio loop was already running, ``loop``
            points to the main loop, and ALL internal operations fail with
            "This event loop is already running" or "Future attached to a
            different loop".

            The only viable fix is to **monkey-patch** that module-level
            ``loop`` to a fresh event loop created in this thread, then call
            ``start()`` normally so all internal code paths use it.
            """
            import lark_oapi as _lark
            import lark_oapi.ws.client as _ws_mod

            # 1. Create a brand-new loop for this thread
            _new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(_new_loop)

            # 2. Monkey-patch the module-level loop so every internal use
            #    (run_until_complete, create_task, etc.) targets THIS loop
            _ws_mod.loop = _new_loop

            # 3. Build handler & client inside this thread
            _handler = (
                _lark.EventDispatcherHandler.builder("", "")
                .register_p2_im_message_receive_v1(on_msg)
                .build()
            )
            _ws = _lark.ws.Client(
                app_id,
                app_secret,
                event_handler=_handler,
                log_level=_lark.LogLevel.INFO,
            )
            self._ws_client = _ws

            # 4. start() is blocking — it uses the (now-patched) module loop
            _ws.start()

        self._ws_thread = threading.Thread(
            target=_run_ws,
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
                            "msg_type": msg.message_type,
                            "message_id": msg.message_id,
                        },
                    ),
                    self._loop,
                )
        except Exception as e:
            logger.error("Feishu _on_message_receive error: {}", e)
