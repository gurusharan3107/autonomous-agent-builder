"""Day-0 readiness contract for builder-managed repositories."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1"
READINESS_FILENAME = "readiness.json"
READY_STATE = "agent_ready"
BLOCKED_STATE = "blocked"
UNKNOWN_STATE = "unknown"

_MANIFEST_NAMES = (
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "go.mod",
    "Cargo.toml",
    "pom.xml",
    "build.gradle",
)
_MODE_VALUES = {"forward_engineering", "reverse_engineering"}
_COMMON_PHASES = ("repo_detect", "project_seed", "repo_scan", "work_item_seed")


def readiness_path(project_root: Path) -> Path:
    return project_root / ".agent-builder" / READINESS_FILENAME


def assess_readiness(
    project_root: Path,
    *,
    onboarding_state: dict[str, Any] | None = None,
    write: bool = True,
) -> dict[str, Any]:
    """Assess readiness from local project state and optionally persist it."""
    project_root = project_root.resolve()
    state = onboarding_state or _load_onboarding_state(project_root)
    mode = str(state.get("onboarding_mode") or _classify_mode(project_root))
    checks = _build_checks(project_root, state, mode)
    required_failed = [
        check for check in checks if check["required"] and check["status"] != "passed"
    ]
    optional_failed = [
        check for check in checks if not check["required"] and check["status"] == "failed"
    ]
    skipped = [check for check in checks if check["status"] == "skipped"]
    required_passed = [
        check for check in checks if check["required"] and check["status"] == "passed"
    ]
    state_name = READY_STATE if not required_failed else BLOCKED_STATE
    payload = {
        "schema_version": SCHEMA_VERSION,
        "mode": mode if mode in _MODE_VALUES else "unknown",
        "state": state_name,
        "can_continue": state_name == READY_STATE,
        "project_root": str(project_root),
        "repo_fingerprint": repo_fingerprint(project_root, mode=mode),
        "assessed_at": datetime.now(UTC).isoformat(),
        "checks": checks,
        "summary": {
            "required_passed": len(required_passed),
            "required_failed": len(required_failed),
            "optional_failed": len(optional_failed),
            "skipped": len(skipped),
        },
        "blocking_reasons": [
            {
                "code": check["id"],
                "message": check["message"],
                "evidence": check.get("evidence", []),
            }
            for check in required_failed
        ],
        "invalidated_by": [],
        "next": _next_actions(required_failed),
    }
    if write and (project_root / ".agent-builder").is_dir():
        path = readiness_path(project_root)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def load_readiness_status(project_root: Path) -> dict[str, Any]:
    """Load persisted readiness and mark it unknown when local inputs changed."""
    project_root = project_root.resolve()
    path = readiness_path(project_root)
    if not path.exists():
        return _unknown_status(project_root, "readiness_missing", "No readiness assessment found.")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _unknown_status(
            project_root, "readiness_unreadable", "Readiness assessment is unreadable."
        )

    if not isinstance(payload, dict) or str(payload.get("schema_version")) != SCHEMA_VERSION:
        return _unknown_status(
            project_root,
            "readiness_schema_mismatch",
            "Readiness schema is missing or stale.",
        )

    mode = str(payload.get("mode") or _classify_mode(project_root))
    current_fingerprint = repo_fingerprint(project_root, mode=mode)
    invalidated_by = _fingerprint_diff(payload.get("repo_fingerprint"), current_fingerprint)
    if invalidated_by:
        stale = dict(payload)
        stale["state"] = UNKNOWN_STATE
        stale["can_continue"] = False
        stale["invalidated_by"] = invalidated_by
        stale["next"] = [
            {
                "code": "run_assess",
                "command": "builder readiness assess --json",
                "reason": "Readiness inputs changed since the last assessment.",
            }
        ]
        return stale
    payload.setdefault("invalidated_by", [])
    payload.setdefault("can_continue", payload.get("state") == READY_STATE)
    payload.setdefault("next", [])
    return payload


def compact_status(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "mode": payload.get("mode", "unknown"),
        "state": payload.get("state", UNKNOWN_STATE),
        "can_continue": bool(payload.get("can_continue", False)),
        "blocking_reasons": payload.get("blocking_reasons", []),
        "invalidated_by": payload.get("invalidated_by", []),
        "next": payload.get("next", []),
    }


def readiness_exit_code(payload: dict[str, Any]) -> int:
    state = str(payload.get("state", UNKNOWN_STATE))
    if state == READY_STATE:
        return 0
    if state == BLOCKED_STATE:
        return 2
    if state == UNKNOWN_STATE:
        return 3
    return 1


def repo_fingerprint(project_root: Path, *, mode: str) -> dict[str, Any]:
    return {
        "root": str(project_root.resolve()),
        "mode": mode if mode in _MODE_VALUES else "unknown",
        **_git_info(project_root),
        "manifest_hashes": _manifest_hashes(project_root),
        "runtime_guidance": _runtime_guidance_fingerprint(project_root),
        "onboarding_state_hash": _file_hash(
            project_root / ".agent-builder" / "onboarding-state.json"
        ),
        "config_hash": _file_hash(project_root / ".agent-builder" / "config.yaml"),
    }


def _build_checks(project_root: Path, state: dict[str, Any], mode: str) -> list[dict[str, Any]]:
    builder_dir = project_root / ".agent-builder"
    runtime_guidance = _runtime_guidance_path(project_root)
    runtime_guidance_contract = _runtime_guidance_contract_status(project_root)
    telemetry_status = _telemetry_env_status(project_root)
    guidance_kind = str(runtime_guidance_contract.get("kind") or "claude")
    guidance_filename = str(runtime_guidance_contract.get("expected_path") or "CLAUDE.md")
    guidance_check_id = "project_agents_md" if guidance_kind == "codex" else "project_claude_md"
    checks = [
        _check(
            "builder_state",
            builder_dir.is_dir()
            and (builder_dir / "config.yaml").exists()
            and (builder_dir / "agent_builder.db").exists(),
            True,
            "Builder state, config, and database are present.",
            [{"path": str(builder_dir)}],
        ),
        _check(
            guidance_check_id,
            runtime_guidance is not None,
            True,
            f"Project {guidance_filename} exists for {guidance_kind} runtime guidance.",
            [
                {
                    "path": str(project_root / guidance_filename),
                    "alternate_path": str(project_root / ".claude" / "CLAUDE.md"),
                    "active_path": str(runtime_guidance) if runtime_guidance else "",
                    "sdk": runtime_guidance_contract.get("sdk", ""),
                    "kind": guidance_kind,
                }
            ],
        ),
        _check(
            "runtime_guidance_contract",
            runtime_guidance_contract.get("ok") is True,
            True,
            f"Project {guidance_filename} contains the Day-0 runtime contract "
            "or preserves existing guidance.",
            [runtime_guidance_contract],
        ),
        _check(
            "deterministic_command_slots",
            runtime_guidance_contract.get("deterministic_command_slots") is True
            or runtime_guidance_contract.get("builder_generated") is False,
            True,
            "Project runtime guidance exposes deterministic command slots when builder-created.",
            [runtime_guidance_contract],
        ),
        _check(
            "telemetry_env_config",
            telemetry_status.get("ok") is True,
            True,
            "Selected runtime telemetry is enabled and inactive runtime lanes are disabled.",
            [telemetry_status],
        ),
        _check(
            "telemetry_content_safe",
            telemetry_status.get("content_safe") is True,
            True,
            "Claude SDK telemetry does not enable raw prompt, tool, or API body export by default.",
            [telemetry_status],
        ),
        _check(
            "telemetry_collector_reachable",
            telemetry_status.get("collector_reachable") is True,
            False,
            "Configured OTEL collector is reachable for structural telemetry.",
            [telemetry_status],
        ),
        _check(
            "onboarding_state",
            (builder_dir / "onboarding-state.json").exists(),
            True,
            "Onboarding state exists.",
            [{"path": str(builder_dir / "onboarding-state.json")}],
        ),
        _check(
            "onboarding_mode",
            mode in _MODE_VALUES,
            True,
            f"Repo classified as {mode}.",
            [{"mode": mode}],
        ),
        _check(
            "project_root_writable",
            os.access(project_root, os.W_OK),
            True,
            "Project root is writable.",
            [{"path": str(project_root)}],
        ),
    ]
    checks.extend(_phase_checks(state, _COMMON_PHASES))
    if mode == "forward_engineering":
        checks.extend(_forward_engineering_checks(project_root, state))
    elif mode == "reverse_engineering":
        checks.extend(_reverse_engineering_checks(state))
    return checks


def _forward_engineering_checks(project_root: Path, state: dict[str, Any]) -> list[dict[str, Any]]:
    kb_extract = _phase(state, "kb_extract")
    kb_validate = _phase(state, "kb_validate")
    return [
        _check(
            "forward_workspace_shape",
            _clean_slate_workspace(project_root, state),
            True,
            "Workspace is clean-slate/disposable enough for forward engineering.",
            [{"root": str(project_root)}],
        ),
        _check(
            "feature_backlog_write_path",
            os.access(project_root, os.W_OK),
            True,
            "Feature backlog write path is available.",
            [{"path": str(project_root / ".claude" / "progress" / "feature-list.json")}],
        ),
        _check(
            "forward_kb_extract_deferred",
            _phase_was_forward_skipped(kb_extract),
            False,
            "KB extraction is deferred for forward engineering.",
            [{"phase_status": kb_extract.get("status", "")}],
            skipped=True,
        ),
        _check(
            "forward_kb_validate_deferred",
            _phase_was_forward_skipped(kb_validate),
            False,
            "KB validation is deferred for forward engineering.",
            [{"phase_status": kb_validate.get("status", "")}],
            skipped=True,
        ),
    ]


def _reverse_engineering_checks(state: dict[str, Any]) -> list[dict[str, Any]]:
    scan = state.get("scan_summary", {}) if isinstance(state.get("scan_summary"), dict) else {}
    kb_status = state.get("kb_status", {}) if isinstance(state.get("kb_status"), dict) else {}
    entrypoints = scan.get("entrypoints") if isinstance(scan.get("entrypoints"), list) else []
    important_files = (
        scan.get("important_files") if isinstance(scan.get("important_files"), list) else []
    )
    has_surface_map = bool(
        entrypoints or important_files or scan.get("has_frontend") or scan.get("has_api")
    )
    return [
        *_phase_checks(state, ("kb_extract", "kb_validate")),
        _check(
            "repo_surfaces_mapped",
            has_surface_map,
            True,
            "Repo source, test, or runtime surfaces are mapped.",
            [{"entrypoints": entrypoints, "important_files": important_files[:8]}],
        ),
        _check(
            "kb_quality_gate",
            str(kb_status.get("quality_gate")) == "passed",
            True,
            "KB extraction and validation passed for reverse engineering.",
            [{"quality_gate": kb_status.get("quality_gate", "")}],
        ),
    ]


def _phase_checks(state: dict[str, Any], phase_ids: tuple[str, ...]) -> list[dict[str, Any]]:
    if _ready_phase_passed(state):
        return [
            _check(
                f"phase_{phase_id}",
                True,
                True,
                f"Onboarding phase {phase_id} is covered by completed ready state.",
                [
                    {
                        "phase": phase_id,
                        "status": _phase(state, phase_id).get("status", "missing"),
                        "ready_phase": "passed",
                    }
                ],
            )
            for phase_id in phase_ids
        ]
    return [
        _check(
            f"phase_{phase_id}",
            _phase(state, phase_id).get("status") == "passed",
            True,
            f"Onboarding phase {phase_id} passed.",
            [{"phase": phase_id, "status": _phase(state, phase_id).get("status", "missing")}],
        )
        for phase_id in phase_ids
    ]


def _ready_phase_passed(state: dict[str, Any]) -> bool:
    ready_phase = _phase(state, "ready")
    ready_result = (
        ready_phase.get("result") if isinstance(ready_phase.get("result"), dict) else {}
    )
    return (
        state.get("ready") is True
        or state.get("current_phase") == "ready"
        or ready_phase.get("status") == "passed"
        or ready_result.get("ready") is True
    )


def _check(
    check_id: str,
    passed: bool,
    required: bool,
    message: str,
    evidence: list[dict[str, Any]],
    *,
    skipped: bool = False,
) -> dict[str, Any]:
    status = "skipped" if skipped and passed else ("passed" if passed else "failed")
    return {
        "id": check_id,
        "status": status,
        "required": required,
        "message": message if passed else f"Missing: {message}",
        "evidence": evidence,
    }


def _phase(state: dict[str, Any], phase_id: str) -> dict[str, Any]:
    phases = state.get("phases", [])
    if not isinstance(phases, list):
        return {}
    for phase in phases:
        if isinstance(phase, dict) and phase.get("id") == phase_id:
            return phase
    return {}


def _phase_was_forward_skipped(phase: dict[str, Any]) -> bool:
    result = phase.get("result") if isinstance(phase.get("result"), dict) else {}
    return phase.get("status") == "passed" and result.get("skipped") is True


def _next_actions(required_failed: list[dict[str, Any]]) -> list[dict[str, str]]:
    if not required_failed:
        return []
    first = required_failed[0]
    if first["id"] == "builder_state":
        return [{"code": "run_init", "command": "builder init", "reason": first["message"]}]
    if first["id"] in {
        "project_claude_md",
        "project_agents_md",
        "runtime_guidance_contract",
        "deterministic_command_slots",
        "telemetry_env_config",
        "telemetry_content_safe",
    }:
        return [
            {
                "code": "repair_day0_runtime_contract",
                "command": "builder init",
                "reason": first["message"],
            }
        ]
    if first["id"] == "onboarding_state":
        return [
            {"code": "start_onboarding", "command": "builder start", "reason": first["message"]}
        ]
    return [
        {
            "code": first["id"],
            "command": "builder readiness assess --json",
            "reason": first["message"],
        }
    ]


def _unknown_status(project_root: Path, code: str, message: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": _classify_mode(project_root),
        "state": UNKNOWN_STATE,
        "can_continue": False,
        "project_root": str(project_root.resolve()),
        "repo_fingerprint": repo_fingerprint(
            project_root.resolve(), mode=_classify_mode(project_root)
        ),
        "assessed_at": "",
        "checks": [],
        "summary": {"required_passed": 0, "required_failed": 0, "optional_failed": 0, "skipped": 0},
        "blocking_reasons": [{"code": code, "message": message, "evidence": []}],
        "invalidated_by": [],
        "next": [
            {
                "code": "run_assess",
                "command": "builder readiness assess --json",
                "reason": message,
            }
        ],
    }


def _load_onboarding_state(project_root: Path) -> dict[str, Any]:
    from autonomous_agent_builder.onboarding import load_onboarding_state

    return load_onboarding_state(project_root)


def _classify_mode(project_root: Path) -> str:
    try:
        from autonomous_agent_builder.onboarding import _classify_onboarding_mode

        return _classify_onboarding_mode(project_root)
    except Exception:
        return "unknown"


def _clean_slate_workspace(project_root: Path, state: dict[str, Any]) -> bool:
    ready_phase = _phase(state, "ready")
    ready_result = ready_phase.get("result") if isinstance(ready_phase.get("result"), dict) else {}
    if (
        str(state.get("onboarding_mode") or "") == "forward_engineering"
        and (
            state.get("current_phase") == "ready"
            or ready_phase.get("status") == "passed"
            or ready_result.get("ready") is True
        )
    ):
        return True
    mode = _classify_mode(project_root)
    return mode == "forward_engineering"


def _git_info(project_root: Path) -> dict[str, Any]:
    def run(*args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout.strip() if result.returncode == 0 else ""

    status = run("status", "--short")
    return {
        "branch": run("branch", "--show-current"),
        "head": run("rev-parse", "--verify", "HEAD"),
        "dirty": bool(status),
    }


def _manifest_hashes(project_root: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for name in _MANIFEST_NAMES:
        path = project_root / name
        digest = _file_hash(path)
        if digest:
            hashes[name] = digest
    return hashes


def _file_hash(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def _runtime_guidance_path(project_root: Path) -> Path | None:
    from autonomous_agent_builder.services.runtime_guidance import find_project_runtime_guidance

    return find_project_runtime_guidance(project_root)


def _runtime_guidance_fingerprint(project_root: Path) -> dict[str, str]:
    path = _runtime_guidance_path(project_root)
    if path is None:
        return {"path": "", "hash": ""}
    try:
        relative_path = str(path.relative_to(project_root.resolve()))
    except ValueError:
        relative_path = str(path)
    return {"path": relative_path, "hash": _file_hash(path)}


def _runtime_guidance_contract_status(project_root: Path) -> dict[str, Any]:
    from autonomous_agent_builder.services.runtime_guidance import runtime_guidance_contract_status

    return runtime_guidance_contract_status(project_root)


def _telemetry_env_status(project_root: Path) -> dict[str, Any]:
    from autonomous_agent_builder.services.runtime_guidance import telemetry_env_status

    return telemetry_env_status(project_root)


def _fingerprint_diff(saved: Any, current: dict[str, Any]) -> list[str]:
    if not isinstance(saved, dict):
        return ["repo_fingerprint"]
    changed: list[str] = []
    for key in (
        "root",
        "mode",
        "runtime_guidance",
        "onboarding_state_hash",
        "config_hash",
    ):
        if saved.get(key) != current.get(key):
            changed.append(key)
    return changed
