"""SQLAlchemy models. Importing this package registers every table on Base.metadata
(used by Alembic autogenerate and by tests)."""

from app.models.agents import Agent, AgentVersion, ProviderCredential
from app.models.channels import Channel
from app.models.conversations import Conversation, Message
from app.models.identity import (
    EmailVerificationToken,
    Invitation,
    MagicLinkToken,
    Membership,
    OAuthAccount,
    Organization,
    PasswordResetToken,
    Session,
    User,
)
from app.models.inbox import Handoff
from app.models.knowledge import Chunk, Document, KnowledgeBase
from app.models.platform import (
    ApiKey,
    AuditLog,
    Quota,
    Subscription,
    UsageRecord,
    WebhookDelivery,
    WebhookEndpoint,
)
from app.models.tools import Tool, ToolRun

__all__ = [
    "Agent",
    "AgentVersion",
    "ApiKey",
    "AuditLog",
    "Channel",
    "Chunk",
    "Conversation",
    "Document",
    "EmailVerificationToken",
    "Handoff",
    "Invitation",
    "KnowledgeBase",
    "MagicLinkToken",
    "Membership",
    "Message",
    "OAuthAccount",
    "Organization",
    "PasswordResetToken",
    "ProviderCredential",
    "Quota",
    "Session",
    "Subscription",
    "Tool",
    "ToolRun",
    "UsageRecord",
    "User",
    "WebhookDelivery",
    "WebhookEndpoint",
]
