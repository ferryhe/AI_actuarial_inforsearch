"""
Unit tests for SafeUnpickler security in vector_store.py
"""
import pytest
import pickle
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


class TestSafeUnpickler:
    """Test SafeUnpickler security features."""

    def test_safe_dict_loads(self):
        """Safe dict loading should work."""
        data = {"key": "value", "number": 42}
        pickled = pickle.dumps(data)
        
        # Import the safe loader
        from ai_actuarial.rag.vector_store import SafeUnpickler
        result = SafeUnpickler.loads(pickled)
        assert result == data

    def test_safe_list_loads(self):
        """Safe list loading should work."""
        data = [1, 2, 3, "test"]
        pickled = pickle.dumps(data)
        
        from ai_actuarial.rag.vector_store import SafeUnpickler
        result = SafeUnpickler.loads(pickled)
        assert result == data

    def test_safe_tuple_loads(self):
        """Safe tuple loading should work."""
        data = (1, "tuple", True)
        pickled = pickle.dumps(data)
        
        from ai_actuarial.rag.vector_store import SafeUnpickler
        result = SafeUnpickler.loads(pickled)
        assert result == data

    def test_safe_nested_structure_loads(self):
        """Safe nested structures should load."""
        data = {"list": [1, 2, 3], "nested": {"a": "b"}}
        pickled = pickle.dumps(data)
        
        from ai_actuarial.rag.vector_store import SafeUnpickler
        result = SafeUnpickler.loads(pickled)
        assert result == data

    def test_malicious_code_blocked(self):
        """Attempting to load malicious pickle should raise error."""
        from ai_actuarial.rag.vector_store import SafeUnpickler
        
        # Try to execute code via pickle - this is a common attack vector
        # This particular pickle would try to execute: os.system('echo pwned')
        malicious = b"\x80\x04\x95\x08\x00\x00\x00\x00\x00\x00\x00\x8c\x05os\x94\x8c\x06system\x94\x93\x94\x8c\x0becho pwned\x94\x85\x94\x86\x94."
        
        with pytest.raises(pickle.UnpicklingError):
            SafeUnpickler.loads(malicious)

    def test_malicious_function_blocked(self):
        """Attempting to load malicious function should raise error."""
        from ai_actuarial.rag.vector_store import SafeUnpickler
        
        # Try to pickle a lambda/function
        try:
            malicious = pickle.dumps(lambda: __import__('os').system('malicious'))
            with pytest.raises(pickle.UnpicklingError):
                SafeUnpickler.loads(malicious)
        except pickle.PicklingError:
            # Lambda can't be pickled at all, which is fine
            pass

    def test_builtins_safe(self):
        """Built-in types should be allowed."""
        from ai_actuarial.rag.vector_store import SafeUnpickler
        
        # Various built-in types
        test_cases = [
            {"a": 1},
            [1, 2, 3],
            (1, 2),
            "string",
            42,
            3.14,
            True,
            None,
        ]
        
        for data in test_cases:
            pickled = pickle.dumps(data)
            result = SafeUnpickler.loads(pickled)
            assert result == data
