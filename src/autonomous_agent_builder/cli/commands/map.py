"""Builder map command — bounded repo orientation for fresh sessions."""

from __future__ import annotations

import contextlib
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

import httpx
import typer

from autonomous_agent_builder.cli.client import EXIT_SUCCESS, resolve_base_url
from autonomous_agent_builder.cli.commands.memory import _load_routing
from autonomous_agent_builder.cli.output import render


def _project_root() -> Path:
    return Path(os.environ.get("AAB_PROJECT_ROOT", Path.cwd()))


def _feature_backlog_summary(project_root: Path) -> dict[str, Any]:
    feature_list_path = project_root / ".claude" / "progress" / "feature-list.json"
    if not feature_list_path.exists():
        return {"available": False}

    try:
        data = json.loads(feature_list_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"available": False}

    features = data.get("features", [])
    if not isinstance(features, list):
        return {"available": False}

    done = sum(1 for feature in features if str(feature.get("status", "")).lower() == "done")
    pending = max(len(features) - done, 0)
    return {"available": True, "total": len(features), "done": done, "pending": pending}


def _knowledge_summary(project_root: Path) -> dict[str, Any]:
    kb_root = Path(
        os.environ.get("AAB_LOCAL_KB_ROOT", project_root / ".agent-builder" / "knowledge")
    )
    docs = sorted(kb_root.rglob("*.md")) if kb_root.exists() else []
    type_counts = Counter()
    for doc in docs:
        relative = doc.relative_to(kb_root)
        doc_type = relative.parts[0] if len(relative.parts) > 1 else "context"
        type_counts[doc_type] += 1
    latest_doc = max(docs, key=lambda path: path.stat().st_mtime) if docs else None
    return {
        "root": str(kb_root),
        "documents": len(docs),
        "types": dict(type_counts),
        "latest_document": latest_doc.relative_to(kb_root).as_posix() if latest_doc else "",
    }


def _memory_summary() -> dict[str, Any]:
    entries = _load_routing()
    type_counts = Counter(str(entry.get("type", "")) for entry in entries)
    status_counts = Counter(str(entry.get("status", "active")) for entry in entries)
    return {
        "total": len(entries),
        "active": status_counts.get("active", 0),
        "flagged": status_counts.get("flagged", 0),
        "types": dict(type_counts),
        "statuses": dict(status_counts),
    }


def _server_snapshot() -> dict[str, Any]:
    base_url = resolve_base_url()
    payload: dict[str, Any] = {"reachable": False, "base_url": base_url}

    with (
        contextlib.suppress(httpx.HTTPError),
        httpx.Client(base_url=base_url, timeout=3.0) as client,
    ):
        health = client.get("/health")
        health.raise_for_status()
        payload["reachable"] = True
        payload["health"] = health.json()

        board_resp = client.get("/api/dashboard/board")
        board_resp.raise_for_status()
        board = board_resp.json()
        payload["board"] = {
            key: len(value) for key, value in board.items() if isinstance(value, list)
        }

        metrics_resp = client.get("/api/dashboard/metrics")
        metrics_resp.raise_for_status()
        metrics = metrics_resp.json()
        payload["metrics"] = {
            "total_runs": metrics.get("total_runs", 0),
            "total_cost": metrics.get("total_cost", 0),
            "gate_pass_rate": metrics.get("gate_pass_rate", 0),
        }

        projects_resp = client.get("/api/projects/")
        projects_resp.raise_for_status()
        projects = projects_resp.json()
        payload["projects"] = {"count": len(projects) if isinstance(projects, list) else 0}

    return payload


def map_command(
    json: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Show a bounded map of active work, KB state, and memory state."""
    project_root = _project_root()
    server = _server_snapshot()
    payload = {
        "project_root": str(project_root),
        "feature_backlog": _feature_backlog_summary(project_root),
        "knowledge_base": _knowledge_summary(project_root),
        "memory": _memory_summary(),
        "server": server,
    }
    payload["next_step"] = (
        "builder board show --json"
        if server.get("reachable")
        else "builder --json doctor"
    )

    def fmt(data: dict[str, Any]) -> str:
        lines = [
            "Builder map",
            "",
            f"project_root: {data['project_root']}",
        ]

        backlog = data["feature_backlog"]
        if backlog.get("available"):
            lines.append(
                f"backlog: {backlog['done']}/{backlog['total']} done, {backlog['pending']} pending"
            )

        kb = data["knowledge_base"]
        lines.append(
            "knowledge: "
            f"{kb['documents']} docs"
            + (
                " ("
                + ", ".join(f"{name}={count}" for name, count in sorted(kb["types"].items()))
                + ")"
                if kb["types"]
                else ""
            )
        )
        if kb.get("latest_document"):
            lines.append(f"latest_kb_doc: {kb['latest_document']}")

        memory = data["memory"]
        lines.append(
            "memory: "
            f"{memory['active']}/{memory['total']} active"
            + (f", {memory['flagged']} flagged" if memory["flagged"] else "")
        )

        server_data = data["server"]
        if server_data["reachable"]:
            board = server_data.get("board", {})
            metrics = server_data.get("metrics", {})
            projects = server_data.get("projects", {})
            lines.append(
                "server: reachable"
                + (f" at {server_data['base_url']}" if server_data.get("base_url") else "")
            )
            if projects:
                lines.append(f"projects: {projects.get('count', 0)}")
            if board:
                lines.append(
                    "board: "
                    + ", ".join(f"{name}={count}" for name, count in sorted(board.items()))
                )
            if metrics:
                lines.append(
                    "metrics: "
                    f"runs={metrics.get('total_runs', 0)}, "
                    f"cost=${metrics.get('total_cost', 0):.2f}, "
                    f"gate_pass_rate={metrics.get('gate_pass_rate', 0):.1f}%"
                )
        else:
            lines.append("server: unreachable")

        lines.append(f"next: {data.get('next_step', '')}")

        return "\n".join(lines)

    render(payload, fmt, use_json=json)
    raise typer.Exit(code=EXIT_SUCCESS)
