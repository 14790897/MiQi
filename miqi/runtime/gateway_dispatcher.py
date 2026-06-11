"""Gateway runtime dispatcher — routes channel bus messages to RuntimeSession.

Replaces the legacy AgentLoop.run() bus-based message loop for gateways.
Reads InboundMessage from the bus, submits as UserMessage to RuntimeSession,
and publishes responses back via bus.publish_outbound.
"""

from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger


class GatewayRuntimeDispatcher:
    """Routes bus InboundMessage ↔ RuntimeSession UserMessage ↔ bus OutboundMessage.

    Created once at gateway startup. Runs as a background task that drains
    the shared message bus (InboundMessage) and dispatches each through
    RuntimeClient.ask(), then publishes the response back.
    """

    def __init__(
        self,
        *,
        bus: Any,
        channel_manager: Any,
        runtime: Any,  # RuntimeSession
        client: Any,    # RuntimeClient
    ):
        self._bus = bus
        self._channels = channel_manager
        self._runtime = runtime
        self._client = client

    async def run(self):
        """Main dispatch loop — drain inbound bus messages, route to runtime."""
        logger.info("Gateway runtime dispatcher started")
        while True:
            try:
                msg = await asyncio.wait_for(self._bus.consume_inbound(), timeout=1.0)
                asyncio.create_task(self._dispatch(msg))
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                logger.info("Gateway runtime dispatcher stopping")
                break
            except Exception:
                logger.exception("Gateway dispatch error")

    async def _dispatch(self, msg: Any) -> None:
        """Process a single inbound message through the runtime."""
        channel = getattr(msg, "channel", "cli")
        chat_id = getattr(msg, "chat_id", "direct")
        thread_id = f"{channel}:{chat_id}"
        content = getattr(msg, "content", "")

        try:
            response = await self._client.ask(
                content,
                thread_id=thread_id,
            )
            if response:
                from miqi.bus.events import OutboundMessage
                await self._bus.publish_outbound(
                    OutboundMessage(
                        channel=channel,
                        chat_id=chat_id,
                        content=response,
                    )
                )
        except Exception:
            logger.exception("Gateway dispatch failed for thread {}", thread_id)
