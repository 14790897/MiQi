"""Message bus module for decoupled channel-agent communication."""

from featherflow.bus.events import InboundMessage, OutboundMessage
from featherflow.bus.queue import MessageBus

__all__ = ["MessageBus", "InboundMessage", "OutboundMessage"]
