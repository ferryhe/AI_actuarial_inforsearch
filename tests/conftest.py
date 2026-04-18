"""
pytest configuration and fixtures for ai_actuarial tests.
"""
import pytest
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


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
    """Generate a mock guest token."""
    import hashlib
    import time
    token_data = f"guest:{time.time()}"
    return hashlib.sha256(token_data.encode()).hexdigest()


@pytest.fixture
def admin_token():
    """Generate a mock admin token."""
    import hashlib
    import time
    token_data = f"admin:{time.time()}"
    return hashlib.sha256(token_data.encode()).hexdigest()
