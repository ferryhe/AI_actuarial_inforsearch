# PR #1: TypeScript Fixes + Security Hardening + Test Infrastructure

## 🎯 Goal
Fix critical TypeScript errors, harden security, and set up testing infrastructure.

---

## 📦 Task 1: Fix TypeScript Errors

### Step 1.1: Install Type Definitions
```bash
cd /opt/AI_actuarial_inforsearch/client
npm install --save-dev @types/react @types/react-dom @types/node
```

### Step 1.2: Fix Tasks.tsx (~200 type errors)
File: `client/src/pages/Tasks.tsx`

Common patterns to fix:
- Add explicit types: `task: any` → `task: Task`
- Fix JSX intrinsic elements: ensure proper React imports
- Add `React.FC` or proper component types

Key areas needing types:
```typescript
// Around line 893
Parameter 'task' implicitly has an 'any' type
→ Add interface Task { id: string; status: string; ... }

// Around line 1040-1041
Parameter 'e' implicitly has an 'any' type  
→ Add MouseEvent or change handler type

// Around line 1074
Parameter 'd' implicitly has an 'any' type
→ Add proper type annotation

// Around line 1082
Parameter 'f' implicitly has an 'any' type
→ Add proper type

// Map callbacks
.map((task: Task, i: number) => ...)
```

### Step 1.3: Fix Users.tsx (~150 type errors)
File: `client/src/pages/Users.tsx`

Common patterns:
```typescript
// Line 86, 90, 94, 103, 109, etc.
Parameter 'prev' implicitly has an 'any' type
→ Add proper state type

Parameter 'u' implicitly has an 'any' type  
→ Add User type

// JSX elements
No interface 'JSX.IntrinsicElements' exists
→ Ensure @types/react is installed and imported correctly

// Line 221, 366, 393
Parameter 'user', 'e', 'entry' implicitly has 'any' type
→ Add explicit types
```

### Step 1.4: Fix other pages (Chat.tsx, FilePreview.tsx, Dashboard.tsx, etc.)
Check remaining files in `client/src/pages/` for type errors.

### Step 1.5: Create shared type definitions
File: `client/src/types/index.ts`
```typescript
export interface Task {
  id: string;
  name: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  created_at: string;
  updated_at: string;
  // Add other fields as needed
}

export interface User {
  id: number;
  email: string;
  role: string;
  group_name: string;
  // Add other fields
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
}
```

---

## 🔒 Task 2: Security Hardening

### Step 2.1: Safe Pickle Unpickler
File: `ai_actuarial/rag/vector_store.py`

Create a safe unpickler to prevent code execution from malicious .pkl files:

```python
import pickle
from pathlib import Path
from typing import Any, List, Dict, Optional

class SafeUnpickler(pickle.Unpickler):
    """Safe unpickler that only allows known-safe classes."""
    
    # Whitelist of allowed module prefixes
    SAFE_PREFIXES: tuple[str, ...] = (
        'builtins', 'types', 'datetime', 're', 'collections',
        'hashlib', 'io', 'numpy', 'numpy.', 'pandas', 'pickle',
    )
    
    # Whitelist of specific classes
    SAFE_CLASSES: tuple[type, ...] = (
        dict, list, tuple, str, int, float, bool, type(None),
    )
    
    def find_class(self, module: str, name: str) -> Any:
        # Check module prefix
        for prefix in self.SAFE_PREFIXES:
            if module == prefix or module.startswith(prefix + '.'):
                return super().find_class(module, name)
        
        # Block all other imports
        raise pickle.UnpicklingError(
            f"Disallowed module: {module}.{name}. "
            f"Only safe stdlib/numpy/pandas types are allowed."
        )

def safe_pickle_load(filepath: Path | str) -> Any:
    """Safely load a pickle file, rejecting malicious content."""
    with open(filepath, 'rb') as f:
        return SafeUnpickler(f).load()

# Update load_metadata() method:
def load_metadata(self, path: Optional[Path] = None) -> List[Dict[str, Any]]:
    ...
    try:
        # Use safe loader instead of pickle.load
        metadata = safe_pickle_load(metadata_path)
        return metadata
    except pickle.UnpicklingError as e:
        raise VectorStoreException(f"Failed to load metadata (security check failed): {e}")
    except Exception as e:
        raise VectorStoreException(f"Failed to load metadata: {e}")
```

### Step 2.2: Improve Password Hashing (Optional Upgrade)
File: `ai_actuarial/shared_auth.py`

Current implementation uses PBKDF2-SHA256 which is reasonable. If bcrypt is available, use it:

```python
def hash_password(password: str) -> str:
    """Hash password using bcrypt if available, otherwise PBKDF2."""
    try:
        import bcrypt
        salt = bcrypt.gensalt(rounds=12)
        return bcrypt.hashpw(password.encode(), salt).decode()
    except ImportError:
        # Fallback to PBKDF2
        import hashlib, secrets
        salt = secrets.token_hex(16)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260_000)
        return f"pbkdf2:sha256:260000:{salt}:{dk.hex()}"

def check_password(password: str, password_hash: str) -> bool:
    """Verify password against hash."""
    try:
        import bcrypt
        if password_hash.startswith('bcrypt:'):
            return bcrypt.checkpw(password.encode(), password_hash[7:].encode())
    except ImportError:
        pass
    
    # Fallback to PBKDF2 verification
    try:
        parts = password_hash.split(":")
        if len(parts) != 5 or parts[0] not in ('pbkdf2', 'bcrypt'):
            return False
        _, algo, iterations, salt, stored = parts
        dk = hashlib.pbkdf2_hmac(algo, password.encode(), salt.encode(), int(iterations))
        return secrets.compare_digest(dk.hex(), stored)
    except Exception:
        return False
```

---

## 🧪 Task 3: Test Infrastructure

### Step 3.1: Create test structure
```bash
mkdir -p /opt/AI_actuarial_inforsearch/tests
mkdir -p /opt/AI_actuarial_inforsearch/tests/api
mkdir -p /opt/AI_actuarial_inforsearch/tests/unit
```

### Step 3.2: pytest configuration
File: `/opt/AI_actuarial_inforsearch/pytest.ini` or `pyproject.toml`

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = -v --tb=short
filterwarnings =
    ignore::DeprecationWarning
```

### Step 3.3: conftest.py - Test fixtures
File: `/opt/AI_actuarial_inforsearch/tests/conftest.py`

```python
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
```

### Step 3.4: Permission Tests
File: `/opt/AI_actuarial_inforsearch/tests/unit/test_permissions.py`

```python
import pytest
from ai_actuarial.shared_auth import (
    GUEST_PERMISSIONS,
    REGISTERED_PERMISSIONS,
    PREMIUM_PERMISSIONS,
    OPERATOR_PERMISSIONS,
    ADMIN_PERMISSIONS,
    AI_CHAT_QUOTA,
    permissions_for_group,
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
        from ai_actuarial.shared_auth import PERMISSIONS
        assert ADMIN_PERMISSIONS == PERMISSIONS
    
    def test_operator_has_tokens_manage(self):
        """Operator should have tokens.manage permission."""
        assert "tokens.manage" in OPERATOR_PERMISSIONS

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
```

### Step 3.5: SafePickle Tests
File: `/opt/AI_actuarial_inforsearch/tests/unit/test_safe_pickle.py`

```python
import pytest
import pickle
import tempfile
from pathlib import Path
from ai_actuarial.rag.vector_store import SafeUnpickler, VectorStoreException

class TestSafeUnpickler:
    """Test SafeUnpickler security."""
    
    def test_safe_dict_loads(self):
        """Safe dict loading should work."""
        data = {"key": "value", "number": 42}
        pickled = pickle.dumps(data)
        
        result = SafeUnpickler.loads(pickled)
        assert result == data
    
    def test_safe_list_loads(self):
        """Safe list loading should work."""
        data = [1, 2, 3, "test"]
        pickled = pickle.dumps(data)
        
        result = SafeUnpickler.loads(pickled)
        assert result == data
    
    def test_malicious_code_blocked(self):
        """Attempting to load malicious pickle should raise error."""
        # Try to execute code via pickle
        malicious = b"\x80\x04\x95\x08\x00\x00\x00\x00\x00\x00\x00\x8c\x05os\x94\x8c\x06system\x94\x93\x94\x8c\x0becho pwned\x94\x85\x94\x86\x94."
        
        with pytest.raises(pickle.UnpicklingError):
            SafeUnpickler.loads(malicious)
    
    def test_numpy_array_if_available(self):
        """NumPy arrays should be allowed if numpy is available."""
        try:
            import numpy as np
            arr = np.array([1, 2, 3])
            pickled = pickle.dumps(arr)
            
            result = SafeUnpickler.loads(pickled)
            assert result.shape == (3,)
        except ImportError:
            pytest.skip("numpy not installed")
```

### Step 3.6: Requirements for testing
File: `/opt/AI_actuarial_inforsearch/requirements-test.txt`

```
pytest>=7.0.0
pytest-asyncio>=0.21.0
pytest-cov>=4.0.0
httpx>=0.24.0  # For async API testing
```

---

## ✅ Verification Steps

After completing all tasks, verify:

1. **TypeScript:**
   ```bash
   cd /opt/AI_actuarial_inforsearch/client
   npm install @types/react @types/react-dom @types/node
   npx tsc --noEmit 2>&1 | head -50
   ```
   Should show < 10 errors (minor ones acceptable)

2. **Security:**
   ```bash
   cd /opt/AI_actuarial_inforsearch
   python -c "from ai_actuarial.rag.vector_store import SafeUnpickler; print('SafeUnpickler imported OK')"
   python -c "from ai_actuarial.shared_auth import hash_password, check_password; h=hash_password('test'); assert check_password('test', h); print('Password hash OK')"
   ```

3. **Tests:**
   ```bash
   cd /opt/AI_actuarial_inforsearch
   pip install pytest pytest-cov
   pytest tests/unit/test_permissions.py -v
   pytest tests/unit/test_safe_pickle.py -v
   ```

---

## 📝 Commit Strategy

Commit in this order:
1. `chore: add @types/react and fix TypeScript errors`
2. `security: add SafeUnpickler for pickle deserialization`
3. `security: improve password hashing with bcrypt fallback`
4. `test: add pytest infrastructure and permission tests`

---

## ⚠️ Important Notes

1. **DO NOT break existing functionality** - All changes should be backward compatible
2. **Test first** - Run existing tests before making changes
3. **Incremental commits** - Commit often with clear messages
4. **TypeScript** - Focus on fixing critical type errors, minor ones can be suppressed with `// @ts-ignore` if needed temporarily
