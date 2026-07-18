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

# ── API-key scopes ────────────────────────────────────────────────────────────────
# Scopes are coarse tiers issued on API keys. Each tier grants the permission set of a
# role; the key's *effective* role is the tier bounded by (never exceeding) the creating
# member's role — least privilege wins. `admin` deliberately maps to the `admin` role, not
# `owner`, so an API key can never perform owner-only actions (e.g. deleting the org).
SCOPES = ("read", "write", "admin")
_SCOPE_TIER_ROLE = {"read": "viewer", "write": "editor", "admin": "admin"}
_ROLE_RANK = {"viewer": 1, "operator": 1, "editor": 2, "admin": 3, "owner": 4}


def scope_effective_role(creator_role: str, scopes: list[str]) -> str:
    """The role an API key acts as: its scope tier, capped by the creating member's role.

    No scopes ⇒ the key acts with the creator's full role (backward compatible). Unknown
    scope strings are treated as the ``write`` tier unless they clearly denote read-only.
    """
    if not scopes:
        return creator_role
    tier = "read"
    for raw in scopes:
        s = raw.strip().lower()
        if s in ("admin", "*", "owner"):
            tier = "admin"
            break
        if s == "read" or s.endswith(":read"):
            continue
        # any non-read scope ("write", "agents:write", "tools:manage", …) grants the write tier
        if tier != "admin":
            tier = "write"
    scope_role = _SCOPE_TIER_ROLE[tier]
    # Least privilege: never grant more than the creating member already has.
    if _ROLE_RANK.get(scope_role, 4) <= _ROLE_RANK.get(creator_role, 0):
        return scope_role
    return creator_role


def has_permission(role: str, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(role, set())


def require_permission(role: str, permission: str) -> None:
    if not has_permission(role, permission):
        raise AppError("org.forbidden", "You don't have permission to do that.", 403)
