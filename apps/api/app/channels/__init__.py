"""Messaging channels: a common adapter interface + registry (docs/07 §2).

Import side effect: registers every channel adapter on the registry.
"""

from app.channels import discord, slack, telegram, whatsapp  # noqa: F401  (register on import)
from app.channels.base import CHANNELS, BaseChannel, InboundMessage, get_channel

__all__ = ["CHANNELS", "BaseChannel", "InboundMessage", "get_channel"]
