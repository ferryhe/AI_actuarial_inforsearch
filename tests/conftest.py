"""
pytest configuration and fixtures for ai_actuarial tests.
"""
import pytest


@pytest.fixture
def sample_task():
    """Sample task for testing."""
    return {
        "id": "test-task-001",
        "name": "Test Task",
        "status": "pending",
        "created_at": "2026-04-19T00:00:00Z",
    }


@pytest.fixture
def sample_user():
    """Sample user for testing."""
    return {
        "id": 1,
        "email": "test@example.com",
        "role": "guest",
        "group_name": "guest",
    }


@pytest.fixture
def guest_token():
    """Generate a deterministic mock guest token."""
    import hashlib
    token_data = "guest:test-fixture"
    return hashlib.sha256(token_data.encode()).hexdigest()


@pytest.fixture
def admin_token():
    """Generate a deterministic mock admin token."""
    import hashlib
    token_data = "admin:test-fixture"
    return hashlib.sha256(token_data.encode()).hexdigest()
