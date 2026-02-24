"""Chat channels module with plugin architecture."""

from featherflow.channels.base import BaseChannel
from featherflow.channels.manager import ChannelManager

__all__ = ["BaseChannel", "ChannelManager"]
