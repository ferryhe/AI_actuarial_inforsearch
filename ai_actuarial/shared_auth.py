from __future__ import annotations

import hashlib
import secrets
from typing import Any

PERMISSIONS: frozenset[str] = frozenset(
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
        "logs.system.read",
        "export.read",
        "tokens.manage",
        "chat.view",
        "chat.query",
        "chat.conversations",
        "users.manage",
    }
)

PUBLIC_PERMISSIONS_WHEN_AUTH_DISABLED: frozenset[str] = frozenset(
    {
        "stats.read",
        "files.read",
        "files.download",
        "catalog.read",
        "markdown.read",
        "chat.view",
        "chat.query",
        "chat.conversations",
        "tasks.view",
        "tasks.run",
        "tasks.stop",
        "config.read",
        "config.write",
        "schedule.write",
        "catalog.write",
        "markdown.write",
        "files.delete",
        "export.read",
        "logs.task.read",
    }
)

GROUP_PERMISSIONS: dict[str, frozenset[str]] = {
    "registered": frozenset(
        {
            "stats.read",
            "files.read",
            "catalog.read",
            "markdown.read",
            "chat.view",
            "chat.query",
            "chat.conversations",
        }
    ),
    "premium": frozenset(
        {
            "stats.read",
            "files.read",
            "files.download",
            "catalog.read",
            "markdown.read",
            "chat.view",
            "chat.query",
            "chat.conversations",
        }
    ),
    "reader": frozenset(
        {
            "stats.read",
            "files.read",
            "files.download",
            "catalog.read",
            "markdown.read",
            "chat.view",
            "chat.query",
            "chat.conversations",
        }
    ),
    "operator": frozenset(
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
        }
    ),
    "operator_ai": frozenset(
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
            "chat.view",
            "chat.query",
            "chat.conversations",
        }
    ),
    "admin": frozenset(PERMISSIONS),
}

AI_CHAT_QUOTA: dict[str, int] = {
    "anonymous": 2,
    "registered": 10,
    "premium": 100,
    "reader": 50,
    "operator": 0,
    "operator_ai": 100,
    "admin": 10000,
}

VALID_USER_ROLES: tuple[str, ...] = (
    "registered",
    "premium",
    "operator",
    "operator_ai",
    "admin",
)


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
    return GROUP_PERMISSIONS.get((group_name or "").strip().lower(), frozenset())


DUMMY_PASSWORD_HASH: str = hash_password("__timing_sentinel__")
