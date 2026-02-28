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
        # Per-chat debounce state (keyed by chat_id)
        self._debounce_tasks: dict[str, asyncio.Task] = {}
        self._debounce_buffers: dict[str, list[dict]] = {}

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
            _noop = lambda data: None
            _handler = (
                _lark.EventDispatcherHandler.builder("", "")
                .register_p2_im_message_receive_v1(on_msg)
                .register_p2_im_message_reaction_created_v1(_noop)
                .register_p2_im_message_reaction_deleted_v1(_noop)
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

    # Feishu text message hard limit is 30 720 bytes.
    # We use a conservative character limit (Chinese chars are 3 bytes each).
    _MAX_MSG_CHARS = 8000

    async def send(self, msg: OutboundMessage) -> None:
        """
        Send a message to the Feishu chat via the HTTP API.

        Used for progress updates and tool hints (controlled by
        ``channels.sendProgress`` / ``channels.sendToolHints`` config).
        Long messages are automatically split into chunks.
        """
        if not self._api_client:
            return
        text = msg.content
        # Split into chunks to stay within Feishu's 30 720-byte hard limit.
        chunks = [text[i:i + self._MAX_MSG_CHARS] for i in range(0, max(len(text), 1), self._MAX_MSG_CHARS)]
        for chunk in chunks:
            await self._send_text_chunk(msg.chat_id, chunk)

    async def _send_text_chunk(self, chat_id: str, text: str) -> None:
        """Send a single text chunk via the Feishu HTTP API."""
        try:
            import lark_oapi as lark

            content_json = json.dumps({"text": text}, ensure_ascii=False)
            request = (
                lark.im.v1.CreateMessageRequest.builder()
                .receive_id_type("chat_id")
                .request_body(
                    lark.im.v1.CreateMessageRequestBody.builder()
                    .receive_id(chat_id)
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

    @staticmethod
    def _extract_non_text_content(msg_type: str, content: dict, message_id: str) -> str:
        """Build a descriptive text string for non-text message types.

        The returned text tells the agent what was received and how to
        retrieve the actual file via feishu-mcp tools.
        """
        if msg_type == "file":
            file_key = content.get("file_key", "")
            file_name = content.get("file_name", "unknown")
            file_size = content.get("file_size")
            size_str = f"，大小 {int(file_size)} 字节" if file_size else ""
            return (
                f"[收到文件] 文件名: {file_name}{size_str}\n"
                f"message_id: {message_id}, file_key: {file_key}\n"
                f"请使用 feishu-mcp 的 download_message_file 工具下载该文件 "
                f"(message_id=\"{message_id}\", file_key=\"{file_key}\", type=\"file\")。"
            )

        if msg_type == "image":
            image_key = content.get("image_key", "")
            return (
                f"[收到图片] image_key: {image_key}\n"
                f"message_id: {message_id}\n"
                f"请使用 feishu-mcp 的 download_message_file 工具下载该图片 "
                f"(message_id=\"{message_id}\", file_key=\"{image_key}\", type=\"image\")。"
            )

        if msg_type == "audio":
            file_key = content.get("file_key", "")
            duration = content.get("duration")
            dur_str = f"，时长 {duration}ms" if duration else ""
            return (
                f"[收到语音] file_key: {file_key}{dur_str}\n"
                f"message_id: {message_id}\n"
                f"请使用 feishu-mcp 的 download_message_file 工具下载该语音 "
                f"(message_id=\"{message_id}\", file_key=\"{file_key}\", type=\"audio\")。"
            )

        if msg_type == "video":
            file_key = content.get("file_key", "")
            image_key = content.get("image_key", "")
            duration = content.get("duration")
            dur_str = f"，时长 {duration}ms" if duration else ""
            return (
                f"[收到视频] file_key: {file_key}{dur_str}\n"
                f"message_id: {message_id}\n"
                f"请使用 feishu-mcp 的 download_message_file 工具下载该视频 "
                f"(message_id=\"{message_id}\", file_key=\"{file_key}\", type=\"video\")。"
            )

        if msg_type == "media":
            file_key = content.get("file_key", "")
            file_name = content.get("file_name", "unknown")
            return (
                f"[收到媒体文件] 文件名: {file_name}, file_key: {file_key}\n"
                f"message_id: {message_id}\n"
                f"请使用 feishu-mcp 的 download_message_file 工具下载该文件 "
                f"(message_id=\"{message_id}\", file_key=\"{file_key}\", type=\"file\")。"
            )

        # Fallback for unknown non-text types (sticker, share_chat, etc.)
        return (
            f"[收到 {msg_type} 类型消息]\n"
            f"message_id: {message_id}\n"
            f"请使用 feishu-mcp 的 get_message 工具查看完整消息内容 "
            f"(message_id=\"{message_id}\")。"
        )

    def _on_message_receive(self, data: Any) -> None:
        """
        lark-oapi event callback (runs in the WS daemon thread).

        Parses the Feishu message event and forwards it to the MessageBus
        via ``asyncio.run_coroutine_threadsafe`` so it executes on the
        main event loop.

        Supports text messages (original behaviour) as well as non-text
        messages (file, image, audio, video, media, etc.).  For non-text
        types a descriptive prompt is constructed so the agent knows what
        was received and which feishu-mcp tools to use to fetch the file.
        """
        try:
            msg = data.event.message
            sender = data.event.sender

            chat_id: str = msg.chat_id or ""
            sender_id: str = sender.sender_id.open_id or ""
            message_id: str = msg.message_id or ""
            msg_type: str = msg.message_type or "text"

            raw: str = msg.content or "{}"
            try:
                content_dict: dict = json.loads(raw)
            except json.JSONDecodeError:
                content_dict = {}

            if msg_type == "text":
                # Original text handling — extract "text" field
                text = content_dict.get("text", raw).strip()
                if not text:
                    return
            else:
                # Non-text message — build descriptive text for the agent
                text = self._extract_non_text_content(msg_type, content_dict, message_id)
                if not text:
                    return

            metadata: dict[str, Any] = {
                "msg_type": msg_type,
                "message_id": message_id,
            }
            # Attach raw content for non-text messages so the agent can
            # parse file_key / image_key etc. directly if needed.
            if msg_type != "text":
                metadata["raw_content"] = raw

            if self._loop and self._loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    self._enqueue_debounced(
                        sender_id=sender_id,
                        chat_id=chat_id,
                        content=text,
                        metadata=metadata,
                    ),
                    self._loop,
                )
        except Exception as e:
            logger.error("Feishu _on_message_receive error: {}", e)

    async def _enqueue_debounced(
        self,
        *,
        sender_id: str,
        chat_id: str,
        content: str,
        metadata: dict,
    ) -> None:
        """Debounce rapid messages from the same chat before forwarding to the bus.

        Within the ``reply_delay_ms`` window, all messages from the same chat
        are buffered.  When the window expires the buffered messages are merged
        (content joined with a newline separator) and forwarded as a single
        inbound message.  This prevents the agent from responding to a file
        attachment before the user has finished typing the accompanying text.

        Set ``channels.feishu.replyDelayMs`` to 0 to disable debouncing.
        """
        delay = self.config.reply_delay_ms / 1000.0
        if delay <= 0:
            await self._handle_message(
                sender_id=sender_id,
                chat_id=chat_id,
                content=content,
                metadata=metadata,
            )
            return

        # Append to per-chat buffer
        buf = self._debounce_buffers.setdefault(chat_id, [])
        buf.append({"sender_id": sender_id, "content": content, "metadata": metadata})

        # Cancel any existing timer for this chat
        existing = self._debounce_tasks.get(chat_id)
        if existing and not existing.done():
            existing.cancel()

        async def _fire() -> None:
            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                return  # reset by a later message — do nothing

            msgs = self._debounce_buffers.pop(chat_id, [])
            self._debounce_tasks.pop(chat_id, None)
            if not msgs:
                return

            # Merge: sender + metadata from first message, content joined
            first = msgs[0]
            if len(msgs) == 1:
                merged_content = first["content"]
                merged_metadata = first["metadata"]
            else:
                merged_content = "\n".join(m["content"] for m in msgs)
                # Use metadata of the last message (typically the follow-up text)
                merged_metadata = dict(msgs[-1]["metadata"])
                # Preserve raw_content from any file/image/etc. messages
                raw_list = [
                    m["metadata"]["raw_content"]
                    for m in msgs
                    if m["metadata"].get("raw_content")
                ]
                if raw_list:
                    merged_metadata["raw_contents"] = raw_list

            await self._handle_message(
                sender_id=first["sender_id"],
                chat_id=chat_id,
                content=merged_content,
                metadata=merged_metadata,
            )

        self._debounce_tasks[chat_id] = asyncio.ensure_future(_fire())
