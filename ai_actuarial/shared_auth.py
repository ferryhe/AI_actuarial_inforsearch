from __future__ import annotations

import hashlib
import secrets
from typing import Any

# ============================================================
# Permission Definitions
# ============================================================

# All available permissions in the system
PERMISSIONS: frozenset[str] = frozenset(
    {
        "stats.read",          # View dashboard stats
        "files.read",          # Browse files (no download)
        "files.download",      # Download files
        "files.delete",        # Delete files
        "catalog.read",        # Read catalog/KB list
        "catalog.write",      # Write catalog/KB
        "markdown.read",      # Read markdown content
        "markdown.write",     # Write markdown content
        "config.read",        # Read system config
        "config.write",       # Write system config
        "schedule.write",    # Manage scheduled tasks
        "tasks.view",        # View tasks (list/details)
        "tasks.run",         # Run/create tasks
        "tasks.stop",        # Stop tasks
        "logs.task.read",    # Read task logs
        "logs.system.read",  # Read system logs
        "export.read",       # Export data
        "tokens.manage",    # Manage API tokens
        "chat.view",        # View chat interface
        "chat.query",       # Send chat messages
        "chat.conversations", # Manage conversations
        "users.manage",     # Manage users
    }
)

# Permissions for anonymous users (when auth is disabled)
# Only read-only, no downloads, limited chat
PUBLIC_PERMISSIONS_WHEN_AUTH_DISABLED: frozenset[str] = frozenset(
    {
        "stats.read",
        "files.read",
        "catalog.read",
        "markdown.read",
        "tasks.view",
        "chat.view",
        "chat.query",
    }
)

# ============================================================
# Group Permissions (new design)
# ============================================================

# Guest: Can browse but not download, limited chat
# - Dashboard, catalog, knowledge base lists
# - Chat with 5 message limit
# - No file downloads, no write operations
# NOTE: tasks.view grants API access to task list/detail endpoints.
# The "no task details click" restriction is enforced FRONTEND-only.
GUEST_PERMISSIONS: frozenset[str] = frozenset(
    {
        "stats.read",
        "files.read",
        "catalog.read",
        "markdown.read",
        "tasks.view",
        "chat.view",
        "chat.query",
    }
)

# Registered: Guest + file download, more chat quota
REGISTERED_PERMISSIONS: frozenset[str] = frozenset(
    {
        "stats.read",
        "files.read",
        "files.download",   # Can download files
        "catalog.read",
        "markdown.read",
        "tasks.view",
        "chat.view",
        "chat.query",
        "chat.conversations",
    }
)

# Premium: Registered + full task viewing (can click into details)
# Cannot perform any operations
PREMIUM_PERMISSIONS: frozenset[str] = frozenset(
    {
        "stats.read",
        "files.read",
        "files.download",
        "catalog.read",
        "markdown.read",
        "tasks.view",        # Full view (can click into details)
        "chat.view",
        "chat.query",
        "chat.conversations",
    }
)

# Operator: Premium + all write operations
# Can do almost everything except user management and system logs
OPERATOR_PERMISSIONS: frozenset[str] = frozenset(
    {
        "stats.read",
        "files.read",
        "files.download",
        "files.delete",
        "catalog.read",
        "catalog.write",
        "markdown.read",
        "markdown.write",
        "config.read",
        "config.write",
        "schedule.write",
        "tasks.view",
        "tasks.run",
        "tasks.stop",
        "logs.task.read",
        "export.read",
        "tokens.manage",      # API token management
        "chat.view",
        "chat.query",
        "chat.conversations",
    }
)

# Admin: Full access to everything
ADMIN_PERMISSIONS: frozenset[str] = PERMISSIONS

# ============================================================
# Group Definitions
# ============================================================

GROUP_PERMISSIONS: dict[str, frozenset[str]] = {
    "guest": GUEST_PERMISSIONS,
    "registered": REGISTERED_PERMISSIONS,
    "premium": PREMIUM_PERMISSIONS,
    "operator": OPERATOR_PERMISSIONS,
    "admin": ADMIN_PERMISSIONS,
}

# Chat quota per user group (0 = no access, positive = limit, 999999 = unlimited)
AI_CHAT_QUOTA: dict[str, int] = {
    "guest": 5,           # Limited to 5 messages
    "registered": 20,      # 20 messages
    "premium": 50,        # 50 messages
    "operator": 200,      # 200 messages
    "admin": 999999,     # Unlimited (use large sentinel, not -1; storage treats <=0 as "no access")
    # Legacy role aliases for backwards compatibility
    "anonymous": 5,       # Alias for guest
    "reader": 20,         # Alias for registered
    "operator_ai": 200,   # Alias for operator
}

# Valid user roles
VALID_USER_ROLES: tuple[str, ...] = (
    "guest",
    "registered",
    "premium",
    "operator",
    "admin",
)


# ============================================================
# Token & Password Functions
# ============================================================

def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260_000)
    return f"pbkdf2:sha256:260000:{salt}:{dk.hex()}"


def check_password(password: str, password_hash: str) -> bool:
    try:
        parts = password_hash.split(":")
        if len(parts) != 5 or parts[0] != "pbkdf2":
            return False
        _, algo, iterations, salt, stored = parts
        dk = hashlib.pbkdf2_hmac(algo, password.encode(), salt.encode(), int(iterations))
        return secrets.compare_digest(dk.hex(), stored)
    except Exception:
        return False


def permissions_for_group(group_name: str) -> frozenset[str]:
    return GROUP_PERMISSIONS.get((group_name or "").strip().lower(), GUEST_PERMISSIONS)


DUMMY_PASSWORD_HASH: str = hash_password("__timing_sentinel__")
