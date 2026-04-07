"""Message bus module for decoupled channel-agent communication."""

from miqi.bus.events import InboundMessage, OutboundMessage
from miqi.bus.queue import MessageBus

__all__ = ["MessageBus", "InboundMessage", "OutboundMessage"]
