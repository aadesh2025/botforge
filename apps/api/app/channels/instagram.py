"""Instagram Messaging channel adapter (Meta Messenger Platform).

Instagram DMs to a professional account linked to a Facebook Page. Requires the
``instagram_manage_messages`` permission on the Meta app; profile lookups silently
return nothing without it. Public post comments are a separate product — see
docs/DECISIONS.md ADR-037.
"""

from __future__ import annotations

from typing import Any

from app.channels.base import ContactProfile, register
from app.channels.meta_messaging import MetaMessagingChannel
from app.core.logging import get_logger

log = get_logger("channels.instagram")


class InstagramChannel(MetaMessagingChannel):
    type = "instagram"
    webhook_object = "instagram"
    profile_fields = ("name", "username", "profile_pic")

    def profile_from_graph(self, data: dict[str, Any]) -> ContactProfile:
        extra: dict[str, Any] = {}
        if data.get("username"):
            extra["username"] = str(data["username"])
        if data.get("id"):
            extra["igsid"] = str(data["id"])
        # Fall back to the @handle when the account has no display name set.
        name = data.get("name") or data.get("username")
        return ContactProfile(
            display_name=str(name) if name else None,
            avatar_url=str(data["profile_pic"]) if data.get("profile_pic") else None,
            extra=extra,
        )


register(InstagramChannel())
