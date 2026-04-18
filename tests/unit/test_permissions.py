"""
Unit tests for permission system in shared_auth.py
"""
import pytest
from ai_actuarial.shared_auth import (
    GUEST_PERMISSIONS,
    REGISTERED_PERMISSIONS,
    PREMIUM_PERMISSIONS,
    OPERATOR_PERMISSIONS,
    ADMIN_PERMISSIONS,
    AI_CHAT_QUOTA,
    permissions_for_group,
    PERMISSIONS,
)


class TestPermissionGroups:
    """Test permission group assignments."""

    def test_guest_has_basic_read_permissions(self):
        """Guest should have read permissions but not write."""
        assert "stats.read" in GUEST_PERMISSIONS
        assert "files.read" in GUEST_PERMISSIONS
        assert "tasks.view" in GUEST_PERMISSIONS
        assert "files.download" not in GUEST_PERMISSIONS
        assert "tasks.run" not in GUEST_PERMISSIONS

    def test_registered_has_download(self):
        """Registered users should have download permission."""
        assert "files.download" in REGISTERED_PERMISSIONS

    def test_premium_has_full_task_view(self):
        """Premium users should have full task access."""
        assert "tasks.view" in PREMIUM_PERMISSIONS
        assert "files.download" in PREMIUM_PERMISSIONS

    def test_operator_has_write_permissions(self):
        """Operator should have most write permissions."""
        assert "tasks.run" in OPERATOR_PERMISSIONS
        assert "tasks.stop" in OPERATOR_PERMISSIONS
        assert "config.write" in OPERATOR_PERMISSIONS
        assert "users.manage" not in OPERATOR_PERMISSIONS  # Operator can't manage users

    def test_admin_has_all_permissions(self):
        """Admin should have all permissions."""
        assert ADMIN_PERMISSIONS == PERMISSIONS

    def test_operator_has_tokens_manage(self):
        """Operator should have tokens.manage permission."""
        assert "tokens.manage" in OPERATOR_PERMISSIONS

    def test_guest_cannot_write(self):
        """Guest should not have any write permissions."""
        write_perms = ["files.delete", "catalog.write", "markdown.write",
                       "config.write", "schedule.write", "tasks.run",
                       "tasks.stop", "logs.system.read", "export.read",
                       "tokens.manage", "users.manage"]
        for perm in write_perms:
            assert perm not in GUEST_PERMISSIONS, f"Guest should not have {perm}"

    def test_registered_cannot_write(self):
        """Registered should not have write permissions."""
        write_perms = ["files.delete", "catalog.write", "markdown.write",
                       "config.write", "schedule.write", "tasks.run",
                       "tasks.stop", "logs.system.read", "export.read",
                       "tokens.manage", "users.manage"]
        for perm in write_perms:
            assert perm not in REGISTERED_PERMISSIONS, f"Registered should not have {perm}"

    def test_premium_cannot_write(self):
        """Premium should not have write permissions."""
        write_perms = ["files.delete", "catalog.write", "markdown.write",
                       "config.write", "schedule.write", "tasks.run",
                       "tasks.stop", "logs.system.read", "export.read",
                       "tokens.manage", "users.manage"]
        for perm in write_perms:
            assert perm not in PREMIUM_PERMISSIONS, f"Premium should not have {perm}"


class TestChatQuota:
    """Test chat quota assignments."""

    def test_guest_quota_is_limited(self):
        """Guest should have limited chat quota."""
        assert AI_CHAT_QUOTA["guest"] == 5

    def test_admin_quota_is_unlimited(self):
        """Admin should have unlimited quota (large sentinel)."""
        assert AI_CHAT_QUOTA["admin"] > 1000  # Should be 999999

    def test_quota_is_positive_for_all_roles(self):
        """All roles should have positive quota."""
        for role, quota in AI_CHAT_QUOTA.items():
            assert quota > 0, f"Role {role} has non-positive quota: {quota}"

    def test_legacy_aliases_exist(self):
        """Legacy role names should map to new roles."""
        assert AI_CHAT_QUOTA["anonymous"] == AI_CHAT_QUOTA["guest"]
        assert AI_CHAT_QUOTA["reader"] == AI_CHAT_QUOTA["registered"]
        assert AI_CHAT_QUOTA["operator_ai"] == AI_CHAT_QUOTA["operator"]

    def test_quota_tiers_increase(self):
        """Quota should increase from guest to admin."""
        assert AI_CHAT_QUOTA["guest"] < AI_CHAT_QUOTA["registered"]
        assert AI_CHAT_QUOTA["registered"] < AI_CHAT_QUOTA["premium"]
        assert AI_CHAT_QUOTA["premium"] < AI_CHAT_QUOTA["operator"]
        assert AI_CHAT_QUOTA["operator"] < AI_CHAT_QUOTA["admin"]


class TestPermissionsForGroup:
    """Test permissions_for_group function."""

    def test_unknown_group_defaults_to_guest(self):
        """Unknown groups should default to guest permissions."""
        perms = permissions_for_group("unknown_role")
        assert perms == GUEST_PERMISSIONS

    def test_none_group_defaults_to_guest(self):
        """None/empty group should default to guest."""
        perms = permissions_for_group(None)
        assert perms == GUEST_PERMISSIONS
        perms = permissions_for_group("")
        assert perms == GUEST_PERMISSIONS

    def test_valid_groups(self):
        """Valid group names should return correct permissions."""
        assert permissions_for_group("guest") == GUEST_PERMISSIONS
        assert permissions_for_group("registered") == REGISTERED_PERMISSIONS
        assert permissions_for_group("admin") == ADMIN_PERMISSIONS

    def test_group_name_trimmed(self):
        """Group names should be trimmed."""
        perms_guest = permissions_for_group("  guest  ")
        assert perms_guest == GUEST_PERMISSIONS

    def test_group_name_case_insensitive(self):
        """Group names should be case-insensitive."""
        assert permissions_for_group("Guest") == GUEST_PERMISSIONS
        assert permissions_for_group("ADMIN") == ADMIN_PERMISSIONS
