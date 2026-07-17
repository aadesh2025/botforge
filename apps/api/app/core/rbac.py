"""Role-based access control — the permission matrix from docs/02 §6."""

from __future__ import annotations

from app.core.errors import AppError

# Capability keys used across modules.
ORG_MANAGE = "org:manage"  # manage org settings / billing / delete
MEMBERS_MANAGE = "members:manage"  # invite, change roles, remove
AGENTS_WRITE = "agents:write"  # create/edit/delete agents
KB_MANAGE = "kb:manage"  # manage knowledge bases
TOOLS_MANAGE = "tools:manage"  # tools / channels / API keys
ANALYTICS_VIEW = "analytics:view"
READ = "read"  # read agents / KB
INBOX_HANDLE = "inbox:handle"

ROLES = ("owner", "admin", "editor", "viewer", "operator")

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "owner": {
        ORG_MANAGE, MEMBERS_MANAGE, AGENTS_WRITE, KB_MANAGE,
        TOOLS_MANAGE, ANALYTICS_VIEW, READ, INBOX_HANDLE,
    },
    "admin": {
        MEMBERS_MANAGE, AGENTS_WRITE, KB_MANAGE,
        TOOLS_MANAGE, ANALYTICS_VIEW, READ, INBOX_HANDLE,
    },
    "editor": {AGENTS_WRITE, KB_MANAGE, TOOLS_MANAGE, ANALYTICS_VIEW, READ, INBOX_HANDLE},
    "viewer": {ANALYTICS_VIEW, READ},
    "operator": {ANALYTICS_VIEW, READ, INBOX_HANDLE},
}

# Roles that can be assigned via member management (owner is set only via transfer).
ASSIGNABLE_ROLES = ("admin", "editor", "viewer", "operator")


def has_permission(role: str, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, set())


def require_permission(role: str, permission: str) -> None:
    if not has_permission(role, permission):
        raise AppError("org.forbidden", "You don't have permission to do that.", 403)
