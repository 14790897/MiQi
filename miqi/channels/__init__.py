"""Chat channels module with plugin architecture."""

from miqi.channels.base import BaseChannel
from miqi.channels.manager import ChannelManager

__all__ = ["BaseChannel", "ChannelManager"]
