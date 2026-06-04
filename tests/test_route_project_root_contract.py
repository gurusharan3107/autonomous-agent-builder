from __future__ import annotations

from pathlib import Path

ROUTE_ROOTS = [
    Path("src/autonomous_agent_builder/api/routes"),
    Path("src/autonomous_agent_builder/embedded/server/routes"),
]


def test_routes_do_not_read_project_state_from_process_cwd() -> None:
    offenders: list[str] = []
    patterns = ("Path.cwd()", 'Path(".agent-builder', "Path('.agent-builder")
    for root in ROUTE_ROOTS:
        for path in sorted(root.glob("*.py")):
            text = path.read_text(encoding="utf-8")
            for pattern in patterns:
                if pattern in text:
                    offenders.append(f"{path}:{pattern}")

    assert offenders == []
