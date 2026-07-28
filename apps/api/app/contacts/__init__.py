"""Contact identity resolution, shared by every inbound path (channels + widget)."""

from app.contacts.service import resolve_contact, upsert_contact

__all__ = ["resolve_contact", "upsert_contact"]
