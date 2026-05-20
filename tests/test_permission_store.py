"""Tests for permission store."""

import tempfile
import time
from pathlib import Path

import pytest

from autonomous_agent_builder.security.permission_store import (
    PermissionRecord,
    PermissionStore,
    check_permission_store,
)


@pytest.fixture
def temp_store_path():
    """Provide a temporary file path for store."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        path = Path(f.name)
    yield path
    # Cleanup
    if path.exists():
        path.unlink()


class TestPermissionStore:
    """Test PermissionStore class."""

    def test_init_creates_empty_store(self, temp_store_path):
        """Initialize store creates empty records."""
        store = PermissionStore(temp_store_path)
        assert store._records == {}

    def test_check_returns_none_for_unknown_tool(self, temp_store_path):
        """Check returns None for unknown tool+input."""
        store = PermissionStore(temp_store_path)
        result = store.check("Bash", {"command": "ls"})
        assert result is None

    def test_record_and_check_allowed(self, temp_store_path):
        """Record allow -> check returns True."""
        store = PermissionStore(temp_store_path)
        store.record("Bash", {"command": "ls"}, allowed=True)
        result = store.check("Bash", {"command": "ls"})
        assert result is True

    def test_record_and_check_denied(self, temp_store_path):
        """Record deny -> check returns False (blocks)."""
        store = PermissionStore(temp_store_path)
        store.record("Bash", {"command": "rm -rf /"}, allowed=False)
        result = store.check("Bash", {"command": "rm -rf /"})
        assert result is False

    def test_different_inputs_different_decisions(self, temp_store_path):
        """Different inputs have independent decisions."""
        store = PermissionStore(temp_store_path)
        store.record("Bash", {"command": "ls"}, allowed=True)
        store.record("Bash", {"command": "rm -rf /"}, allowed=False)

        assert store.check("Bash", {"command": "ls"}) is True
        assert store.check("Bash", {"command": "rm -rf /"}) is False

    def test_hash_determinism(self, temp_store_path):
        """Same input always produces same hash."""
        store = PermissionStore(temp_store_path)
        input1 = {"command": "ls", "path": "/tmp"}
        input2 = {"path": "/tmp", "command": "ls"}  # different order
        hash1 = store._hash(input1)
        hash2 = store._hash(input2)
        assert hash1 == hash2

    def test_expiry_expired_record_ignored(self, temp_store_path):
        """Expired record is ignored (returns None)."""
        store = PermissionStore(temp_store_path)
        past_expiry = time.time() - 10  # 10 seconds ago
        store.record("Bash", {"command": "ls"}, allowed=True, expiry=past_expiry)
        result = store.check("Bash", {"command": "ls"})
        assert result is None

    def test_expiry_valid_record_used(self, temp_store_path):
        """Non-expired record is used."""
        store = PermissionStore(temp_store_path)
        future_expiry = time.time() + 3600  # 1 hour from now
        store.record("Bash", {"command": "ls"}, allowed=True, expiry=future_expiry)
        result = store.check("Bash", {"command": "ls"})
        assert result is True

    def test_most_recent_record_wins(self, temp_store_path):
        """Most recent record takes precedence."""
        store = PermissionStore(temp_store_path)
        store.record("Bash", {"command": "ls"}, allowed=False)
        store.record("Bash", {"command": "ls"}, allowed=True)
        result = store.check("Bash", {"command": "ls"})
        assert result is True

    def test_cleanup_removes_expired(self, temp_store_path):
        """Cleanup removes expired records."""
        store = PermissionStore(temp_store_path)
        past_expiry = time.time() - 10
        store.record("Bash", {"command": "expired"}, allowed=True, expiry=past_expiry)
        store.record("Bash", {"command": "valid"}, allowed=True)

        removed = store.cleanup_expired()
        assert removed == 1
        assert store.check("Bash", {"command": "expired"}) is None
        assert store.check("Bash", {"command": "valid"}) is True

    def test_cleanup_keeps_valid(self, temp_store_path):
        """Cleanup keeps valid non-expired records."""
        store = PermissionStore(temp_store_path)
        future_expiry = time.time() + 3600
        store.record("Bash", {"command": "ls"}, allowed=True, expiry=future_expiry)
        store.record("Read", {"file_path": "/etc/passwd"}, allowed=False)

        removed = store.cleanup_expired()
        assert removed == 0
        assert store.check("Bash", {"command": "ls"}) is True


class TestPermissionStorePersistence:
    """Test persistence to JSON file."""

    def test_save_creates_json_file(self, temp_store_path):
        """Save creates JSON file."""
        store = PermissionStore(temp_store_path)
        store.record("Bash", {"command": "ls"}, allowed=True)
        assert temp_store_path.exists()

    def test_load_restores_records(self, temp_store_path):
        """Load restores records from JSON."""
        store1 = PermissionStore(temp_store_path)
        store1.record("Bash", {"command": "ls"}, allowed=True)

        # Create new store from same path
        store2 = PermissionStore(temp_store_path)
        result = store2.check("Bash", {"command": "ls"})
        assert result is True

    def test_load_nonexistent_file(self, temp_store_path):
        """Load from nonexistent file creates empty store."""
        nonexistent = Path("/tmp/nonexistent_perm_store_" + str(time.time()) + ".json")
        store = PermissionStore(nonexistent)
        assert store._records == {}

    def test_atomic_save_no_corruption(self, temp_store_path):
        """Save uses atomic rename to prevent corruption."""
        store = PermissionStore(temp_store_path)
        for i in range(10):
            store.record("Bash", {"command": f"cmd{i}"}, allowed=i % 2 == 0)

        # Verify all records persisted
        store2 = PermissionStore(temp_store_path)
        for i in range(10):
            expected = i % 2 == 0
            assert store2.check("Bash", {"command": f"cmd{i}"}) == expected


class TestPermissionRecord:
    """Test PermissionRecord dataclass."""

    def test_record_fields(self):
        """PermissionRecord has all fields."""
        record = PermissionRecord(
            tool_name="Bash",
            context_hash="abc123",
            allowed=True,
            readable_context="run ls command",
            timestamp=time.time(),
            expiry=None,
        )
        assert record.tool_name == "Bash"
        assert record.context_hash == "abc123"
        assert record.allowed is True
        assert record.readable_context == "run ls command"
        assert record.expiry is None


@pytest.mark.asyncio
class TestCheckPermissionStoreHook:
    """Test hook integration."""

    async def test_hook_no_store_in_context(self):
        """Hook returns empty dict if store not in context."""
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "ls"},
        }
        result = await check_permission_store(hook_input, None, {})
        assert result == {}

    async def test_hook_allowed_returns_empty(self, temp_store_path):
        """Hook returns empty dict for allowed tool."""
        store = PermissionStore(temp_store_path)
        store.record("Bash", {"command": "ls"}, allowed=True)

        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "ls"},
        }
        context = {"permission_store": store}
        result = await check_permission_store(hook_input, None, context)
        assert result == {}

    async def test_hook_denied_returns_block(self, temp_store_path):
        """Hook returns block for denied tool."""
        store = PermissionStore(temp_store_path)
        store.record("Bash", {"command": "rm -rf /"}, allowed=False)

        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "rm -rf /"},
        }
        context = {"permission_store": store}
        result = await check_permission_store(hook_input, None, context)
        assert result["decision"] == "block"
        assert "Previously denied" in result["reason"]

    async def test_hook_exception_handling(self):
        """Hook handles exceptions gracefully."""
        hook_input = None  # Will cause exception
        try:
            result = await check_permission_store(hook_input, None, {})
            assert result == {}
        except Exception as e:
            pytest.fail(f"Hook should handle exceptions gracefully: {e}")
