"""Messaging channels: a common adapter interface + registry (docs/07 §2).

Import side effect: registers every channel adapter on the registry.
"""

from app.channels import (  # noqa: F401  (register on import)
    discord,
    facebook,
    instagram,
    slack,
    telegram,
    whatsapp,
)
from app.channels.base import CHANNELS, BaseChannel, ContactProfile, InboundMessage, get_channel

__all__ = ["CHANNELS", "BaseChannel", "ContactProfile", "InboundMessage", "get_channel"]
