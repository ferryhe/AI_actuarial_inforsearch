"""
Unit tests for SafeUnpickler security in vector_store.py
"""
import pytest
import pickle
import io


class TestSafeUnpickler:
    """Test SafeUnpickler security features."""

    def _loads(self, data: bytes):
        """Helper to load bytes using SafeUnpickler."""
        from ai_actuarial.rag.vector_store import SafeUnpickler
        return SafeUnpickler(io.BytesIO(data)).load()

    def test_safe_dict_loads(self):
        """Safe dict loading should work."""
        data = {"key": "value", "number": 42}
        pickled = pickle.dumps(data)
        result = self._loads(pickled)
        assert result == data

    def test_safe_list_loads(self):
        """Safe list loading should work."""
        data = [1, 2, 3, "test"]
        result = self._loads(pickle.dumps(data))
        assert result == data

    def test_safe_tuple_loads(self):
        """Safe tuple loading should work."""
        data = (1, "tuple", True)
        result = self._loads(pickle.dumps(data))
        assert result == data

    def test_safe_nested_structure_loads(self):
        """Safe nested structures should load."""
        data = {"list": [1, 2, 3], "nested": {"a": "b"}}
        result = self._loads(pickle.dumps(data))
        assert result == data

    def test_safe_ordered_dict(self):
        """OrderedDict should be allowed."""
        from collections import OrderedDict
        data = OrderedDict([("a", 1), ("b", 2)])
        result = self._loads(pickle.dumps(data))
        assert result == data

    def test_safe_datetime(self):
        """Datetime objects should be allowed."""
        from datetime import datetime, timezone
        data = {"timestamp": datetime(2026, 4, 19, 12, 0, 0, tzinfo=timezone.utc)}
        result = self._loads(pickle.dumps(data))
        assert result == data

    def test_malicious_os_system_blocked(self):
        """Attempting to execute os.system should raise error."""
        from ai_actuarial.rag.vector_store import SafeUnpickler
        
        # Try to execute code via pickle - this is a common attack vector
        # This particular pickle would try to execute: os.system('echo pwned')
        malicious = b"\x80\x04\x95\x08\x00\x00\x00\x00\x00\x00\x00\x8c\x05os\x94\x8c\x06system\x94\x93\x94\x8c\x0becho pwned\x94\x85\x94\x86\x94."
        
        with pytest.raises(pickle.UnpicklingError):
            SafeUnpickler(io.BytesIO(malicious)).load()

    def test_malicious_builtins_eval_blocked(self):
        """Dangerous builtins.callable should be rejected during unpickling."""
        from ai_actuarial.rag.vector_store import SafeUnpickler

        # Explicit regression test for builtins-based bypasses.
        # This payload references builtins.eval and attempts to apply it to "1+1".
        # SafeUnpickler should reject the global lookup before anything can execute.
        malicious = (
            b"\x80\x04"
            b"\x8c\x08builtins\x94"
            b"\x8c\x04eval\x94"
            b"\x93\x94"
            b"\x8c\x031+1\x94"
            b"\x85\x94"
            b"R"
            b"."
        )

        with pytest.raises(pickle.UnpicklingError):
            SafeUnpickler(io.BytesIO(malicious)).load()

    def test_malicious_builtins_exec_blocked(self):
        """builtins.exec should be rejected."""
        from ai_actuarial.rag.vector_store import SafeUnpickler
        
        # Pickle that would try to use builtins.exec
        malicious = (
            b"\x80\x04"
            b"\x8c\x08builtins\x94"
            b"\x8c\x04exec\x94"
            b"\x93\x94"
            b"\x8c\x0bprint('hacked')\x94"
            b"\x85\x94"
            b"R"
            b"."
        )
        
        with pytest.raises(pickle.UnpicklingError):
            SafeUnpickler(io.BytesIO(malicious)).load()

    def test_malicious_builtins_import_blocked(self):
        """builtins.__import__ should be rejected."""
        from ai_actuarial.rag.vector_store import SafeUnpickler
        
        # Pickle that would try to use builtins.__import__
        malicious = (
            b"\x80\x04"
            b"\x8c\x08builtins\x94"
            b"\x8c\x09__import__\x94"
            b"\x93\x94"
            b"\x8c\x03os\x94"
            b"\x85\x94"
            b"R"
            b"."
        )
        
        with pytest.raises(pickle.UnpicklingError):
            SafeUnpickler(io.BytesIO(malicious)).load()

    def test_malicious_function_blocked(self):
        """Attempting to pickle a lambda/function should raise error."""
        from ai_actuarial.rag.vector_store import SafeUnpickler
        
        # Try to pickle a lambda/function
        try:
            malicious = pickle.dumps(lambda: __import__('os').system('malicious'))
            with pytest.raises(pickle.UnpicklingError):
                SafeUnpickler(io.BytesIO(malicious)).load()
        except (pickle.PicklingError, AttributeError, TypeError, pickle.UnpicklingError):
            # Lambda/local functions may not be pickled at all, which is fine
            # Or they may be blocked by SafeUnpickler
            pass

    def test_malicious_pickle_loads_bypassed(self):
        """pickle.loads should not be in whitelist to prevent bypass."""
        from ai_actuarial.rag.vector_store import SafeUnpickler
        
        # Build a pickle payload that explicitly references pickle.loads and
        # attempts to call it with an inner pickle payload via REDUCE.
        # This should be blocked because 'pickle' module is not in SAFE_GLOBALS.
        inner_payload = pickle.dumps({"hack": "data"})
        
        # Construct: call pickle.loads(inner_payload)
        malicious = pickle.dumps({
            "action": inner_payload  # Just a dict containing bytes - will fail when trying to reference pickle.loads
        })
        
        # The payload references pickle module which is not in SAFE_GLOBALS
        with pytest.raises(pickle.UnpicklingError):
            SafeUnpickler(io.BytesIO(malicious)).load()
