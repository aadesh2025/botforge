"""Webhook verification shared by every Meta-based channel.

WhatsApp Cloud API, Facebook Messenger, and Instagram Messaging all sit behind the same
Meta app, so they all use the same two handshakes: an ``X-Hub-Signature-256`` HMAC on
every delivery, and a one-time ``hub.challenge`` GET when the webhook is subscribed.
One implementation, three adapters — a divergence here would be a silent auth hole.
"""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Mapping
from typing import Any


def verify_signature(secret: str | None, headers: Mapping[str, str], body: bytes) -> bool:
    """Constant-time check of Meta's ``X-Hub-Signature-256`` header.

    No app secret configured (dev / not-yet-provisioned) → accept, matching how the other
    adapters degrade when a secret is absent. Configure ``app_secret`` in production.
    """
    if not secret:
        return True
    provided = headers.get("x-hub-signature-256", "")
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, provided)


def verify_challenge(channel: Any, query: Mapping[str, str]) -> str | None:
    """Meta's GET subscription handshake → echo ``hub.challenge`` on a token match."""
    if query.get("hub.mode") == "subscribe" and query.get("hub.verify_token") == channel.config.get(
        "verify_token"
    ):
        return query.get("hub.challenge")
    return None
