"""Async message queue for decoupled channel-agent communication."""

import asyncio

from loguru import logger

from featherflow.bus.events import InboundMessage, OutboundMessage


class MessageBus:
    """
    Async message bus that decouples chat channels from the agent core.

    Channels push messages to the inbound queue, and the agent processes
    them and pushes responses to the outbound queue.
    """

    def __init__(self, maxsize: int = 1000):
        self.inbound: asyncio.Queue[InboundMessage] = asyncio.Queue(maxsize=maxsize)
        self.outbound: asyncio.Queue[OutboundMessage] = asyncio.Queue(maxsize=maxsize)

    async def publish_inbound(self, msg: InboundMessage) -> None:
        """Publish a message from a channel to the agent.

        If the inbound queue is full, the oldest message is dropped to prevent
        channels from blocking indefinitely.
        """
        try:
            self.inbound.put_nowait(msg)
        except asyncio.QueueFull:
            # Drop the oldest message to make room
            try:
                dropped = self.inbound.get_nowait()
                logger.warning(
                    "Inbound queue full — dropped oldest message from {}:{}",
                    dropped.channel, dropped.chat_id,
                )
            except asyncio.QueueEmpty:
                pass
            self.inbound.put_nowait(msg)

    async def consume_inbound(self) -> InboundMessage:
        """Consume the next inbound message (blocks until available)."""
        return await self.inbound.get()

    async def publish_outbound(self, msg: OutboundMessage) -> None:
        """Publish a response from the agent to channels.

        Uses a timeout to avoid blocking the agent indefinitely if outbound
        consumers stall.
        """
        try:
            await asyncio.wait_for(self.outbound.put(msg), timeout=10.0)
        except asyncio.TimeoutError:
            logger.error(
                "Outbound queue full for 10s — dropping response to {}:{}",
                msg.channel, msg.chat_id,
            )

    async def consume_outbound(self) -> OutboundMessage:
        """Consume the next outbound message (blocks until available)."""
        return await self.outbound.get()

    @property
    def inbound_size(self) -> int:
        """Number of pending inbound messages."""
        return self.inbound.qsize()

    @property
    def outbound_size(self) -> int:
        """Number of pending outbound messages."""
        return self.outbound.qsize()
