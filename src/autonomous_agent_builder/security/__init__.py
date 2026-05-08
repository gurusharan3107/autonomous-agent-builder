"""Security module — prompt injection detection, egress monitoring, permission store.

Features:
1. Prompt injection detection (two-layer: PreToolUse + PostToolUse)
2. Egress monitor (logs network destinations from Bash)
3. Permission store (caches tool permission decisions with TTL)
"""

from autonomous_agent_builder.security.egress_monitor import (
    EgressDestination,
    extract_egress_destinations,
    log_egress_destinations,
)
from autonomous_agent_builder.security.permission_store import (
    PermissionRecord,
    PermissionStore,
    check_permission_store,
)
from autonomous_agent_builder.security.prompt_inspector import (
    InspectionResult,
    inspect_tool_input,
    inspect_tool_output,
)

__all__ = [
    "EgressDestination",
    "extract_egress_destinations",
    "log_egress_destinations",
    "InspectionResult",
    "inspect_tool_input",
    "inspect_tool_output",
    "PermissionRecord",
    "PermissionStore",
    "check_permission_store",
]
