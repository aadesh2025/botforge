"""Facebook Messenger channel adapter (Meta Messenger Platform).

Private DMs to a Facebook Page. Public post comments are a different product with
different webhook fields and reply semantics — see docs/DECISIONS.md ADR-037.
"""

from __future__ import annotations

from typing import Any

from app.channels.base import ContactProfile, register
from app.channels.meta_messaging import MetaMessagingChannel
from app.core.logging import get_logger

log = get_logger("channels.facebook")


class FacebookChannel(MetaMessagingChannel):
    type = "facebook"
    webhook_object = "page"
    profile_fields = ("first_name", "last_name", "profile_pic")

    def profile_from_graph(self, data: dict[str, Any]) -> ContactProfile:
        name = " ".join(
            str(p) for p in (data.get("first_name"), data.get("last_name")) if p
        ).strip()
        return ContactProfile(
            display_name=name or None,
            avatar_url=str(data["profile_pic"]) if data.get("profile_pic") else None,
            extra={"psid": str(data["id"])} if data.get("id") else {},
        )


register(FacebookChannel())
