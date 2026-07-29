"""CRM capture: detect contact details customers share in chat, and resolve identity."""

from app.crm.capture import capture_from_message
from app.crm.extract import find_contact_hints, normalize_email, normalize_phone

__all__ = ["capture_from_message", "find_contact_hints", "normalize_email", "normalize_phone"]
