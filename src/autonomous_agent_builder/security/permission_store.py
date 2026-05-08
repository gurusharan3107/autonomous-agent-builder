"""Permission store — per-project tool permission cache with TTL.

Caches user-approved or user-denied tool decisions to avoid re-prompting
for identical operations. Uses SHA-256 hashing of tool_input for comparison.

Usage:
1. At application startup: store = PermissionStore(Path(...))
2. In PreToolUse hook: decision = store.check(tool_name, tool_input)
3. After human approval/denial: store.record(tool_name, tool_input, allowed=True/False, expiry=...)
4. Periodically: store.cleanup_expired()
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger()


@dataclass
class PermissionRecord:
    """A cached permission decision."""

    tool_name: str
    context_hash: str  # SHA-256 of sorted tool_input JSON
    allowed: bool
    readable_context: str  # human-readable summary for audit
    timestamp: float  # time.time()
    expiry: float | None  # None = permanent, else unix timestamp


class PermissionStore:
    """Per-project tool permission cache with TTL support."""

    def __init__(self, store_path: Path):
        """Initialize store from JSON file.

        Args:
            store_path: Path to JSON file for persistence (created if missing).
        """
        self._path = Path(store_path)
        self._records: dict[str, list[PermissionRecord]] = {}
        self.load()

    def check(self, tool_name: str, tool_input: dict[str, Any]) -> bool | None:
        """Look up cached decision.

        Returns:
            True if allowed, False if blocked, None if no cached decision.
        """
        key = self._make_key(tool_name, tool_input)
        records = self._records.get(key, [])

        for record in reversed(records):  # most recent first
            if record.expiry and record.expiry < time.time():
                continue  # expired
            return record.allowed

        return None

    def record(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        allowed: bool,
        readable_context: str = "",
        expiry: float | None = None,
    ) -> None:
        """Store a permission decision.

        Args:
            tool_name: Name of the tool.
            tool_input: Tool input dict.
            allowed: True if allowed, False if blocked.
            readable_context: Human-readable summary (e.g., "create file: main.py").
            expiry: Unix timestamp for TTL, None for permanent.
        """
        key = self._make_key(tool_name, tool_input)
        record = PermissionRecord(
            tool_name=tool_name,
            context_hash=self._hash(tool_input),
            allowed=allowed,
            readable_context=readable_context,
            timestamp=time.time(),
            expiry=expiry,
        )
        self._records.setdefault(key, []).append(record)
        self.save()

    def cleanup_expired(self) -> int:
        """Remove expired records.

        Returns:
            Count of records removed.
        """
        now = time.time()
        removed = 0

        for key in list(self._records):
            before = len(self._records[key])
            self._records[key] = [r for r in self._records[key] if not r.expiry or r.expiry > now]
            removed += before - len(self._records[key])

            if not self._records[key]:
                del self._records[key]

        if removed > 0:
            self.save()

        return removed

    def load(self) -> None:
        """Load records from JSON file."""
        if not self._path.exists():
            self._records = {}
            return

        try:
            with open(self._path) as f:
                data = json.load(f)

            self._records = {}
            for key, records_list in data.items():
                self._records[key] = [
                    PermissionRecord(
                        tool_name=r["tool_name"],
                        context_hash=r["context_hash"],
                        allowed=r["allowed"],
                        readable_context=r["readable_context"],
                        timestamp=r["timestamp"],
                        expiry=r.get("expiry"),
                    )
                    for r in records_list
                ]

            log.info("permission_store_loaded", path=str(self._path), records=len(self._records))
        except Exception as e:
            log.warning("permission_store_load_error", path=str(self._path), error=str(e))
            self._records = {}

    def save(self) -> None:
        """Atomically save records to JSON file."""
        try:
            # Prepare data for JSON serialization
            data = {}
            for key, records_list in self._records.items():
                data[key] = [
                    {
                        "tool_name": r.tool_name,
                        "context_hash": r.context_hash,
                        "allowed": r.allowed,
                        "readable_context": r.readable_context,
                        "timestamp": r.timestamp,
                        "expiry": r.expiry,
                    }
                    for r in records_list
                ]

            # Atomic write: write to temp file, then rename
            tmp_path = self._path.with_suffix(".tmp")
            with open(tmp_path, "w") as f:
                json.dump(data, f, indent=2)

            tmp_path.replace(self._path)
            log.debug("permission_store_saved", path=str(self._path))
        except Exception as e:
            log.error("permission_store_save_error", path=str(self._path), error=str(e))

    @staticmethod
    def _hash(tool_input: dict[str, Any]) -> str:
        """Compute SHA-256 hash of tool input for comparison."""
        canonical = json.dumps(tool_input, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()

    def _make_key(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        """Make cache key from tool name and input hash."""
        return f"{tool_name}:{self._hash(tool_input)}"


async def check_permission_store(
    input: dict[str, Any],
    tool_use_id: str | None,
    context: dict[str, Any],
) -> dict[str, Any]:
    """PreToolUse hook: check stored permissions before allowing tool call.

    SDK signature: (input: PreToolUseHookInput, tool_use_id, context: HookContext)

    If a prior decision exists, return it. Otherwise allow (return {}).
    Human approvers populate the store via separate flow.
    """
    try:
        store = context.get("permission_store")
        if store is None:
            return {}  # fail-open if store not configured

        tool_name = input.get("tool_name", "")
        tool_input = input.get("tool_input", {})

        decision = store.check(tool_name, tool_input)

        if decision is False:
            log.warning("permission_denied", tool=tool_name, reason="Previously denied by user")
            return {"decision": "block", "reason": "Previously denied by user"}

        # None or True = allow
        return {}
    except Exception as e:
        log.error("hook_error", hook="check_permission_store", error=str(e))
        return {}  # fail-open on error
