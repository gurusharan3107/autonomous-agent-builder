"""Dashboard-first onboarding lifecycle for enterprise repositories."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import shlex
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from autonomous_agent_builder.api.dashboard_streams import get_dashboard_stream_hub
from autonomous_agent_builder.claude_runtime import (
    check_claude_availability,
    resolve_claude_backend,
    run_claude_prompt,
)
from autonomous_agent_builder.db.models import (
    AgentRun,
    AgentRunEvent,
    Approval,
    ApprovalGate,
    ChatEvent,
    ChatMessage,
    ChatSession,
    Feature,
    FeatureStatus,
    GateResult,
    Project,
    Task,
    TaskStatus,
    Workspace,
)


@dataclass
class _AgentKbExtractRunResult:
    payload: dict[str, Any]
    raw_output: str


PHASES = [
    "repo_detect",
    "project_seed",
    "repo_scan",
    "work_item_seed",
    "kb_extract",
    "kb_validate",
    "ready",
]

_pipeline_locks: dict[str, asyncio.Lock] = {}
_BOOTSTRAP_FILES = {
    "README",
    "README.md",
    "pyproject.toml",
    "package.json",
    "requirements.txt",
    "go.mod",
    "Cargo.toml",
    "LICENSE",
    "LICENSE.md",
}
_SUPPORT_DIRS = {"docs", "tests", "test", "spec"}
_CODE_DIRS = {"src", "app", "api", "server", "frontend", "backend", "packages", "services", "lib"}
_IGNORED_BOOTSTRAP_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".log"}
_INIT_PROJECT_BOOTSTRAP_MESSAGE = (
    "What do you want to build?\n\n"
    "I will treat this like an `init-project` kickoff. I will ask focused follow-up questions "
    "about users, flows, UX, technical choices, constraints, integrations, and tradeoffs until "
    "the first implementation scope has no obvious gaps. Once we agree on that scope, I will "
    "generate `.claude/progress/feature-list.json`, and the Backlog page will reflect it."
)


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


def _builder_dir(project_root: Path) -> Path:
    return project_root / ".agent-builder"


def _state_path(project_root: Path) -> Path:
    return _builder_dir(project_root) / "onboarding-state.json"


def _archive_root(project_root: Path) -> Path:
    return _builder_dir(project_root) / "archive"


def _phase_records() -> list[dict[str, Any]]:
    return [
        {
            "id": phase,
            "title": phase.replace("_", " ").title(),
            "status": "pending",
            "message": "",
            "started_at": None,
            "finished_at": None,
            "result": None,
            "error": None,
        }
        for phase in PHASES
    ]


def _classify_onboarding_mode(project_root: Path) -> str:
    visible_dirs = sorted(
        p.name for p in project_root.iterdir() if p.is_dir() and not p.name.startswith(".")
    )
    root_files = sorted(
        p.name for p in project_root.iterdir() if p.is_file() and not p.name.startswith(".")
    )
    root_files = [
        name
        for name in root_files
        if Path(name).suffix.lower() not in _IGNORED_BOOTSTRAP_SUFFIXES
    ]

    entrypoints: set[str] = set()
    for pattern in ["main.py", "app.py", "server.py", "manage.py", "src/**/main.py"]:
        for match in project_root.glob(pattern):
            if match.is_file():
                entrypoints.add(match.relative_to(project_root).as_posix())

    bootstrap_only = all(name in _BOOTSTRAP_FILES for name in root_files)
    support_only = all(name in _SUPPORT_DIRS for name in visible_dirs)
    has_code_dirs = any(name in _CODE_DIRS for name in visible_dirs)

    if not entrypoints and not has_code_dirs and bootstrap_only and support_only:
        return "forward_engineering"
    return "reverse_engineering"


def _detect_language(project_root: Path) -> str:
    if (project_root / "pyproject.toml").exists() or (project_root / "requirements.txt").exists():
        return "python"
    if (project_root / "package.json").exists():
        return "node"
    if (project_root / "pom.xml").exists() or (project_root / "build.gradle").exists():
        return "java"
    if (project_root / "go.mod").exists():
        return "go"
    if (project_root / "Cargo.toml").exists():
        return "rust"
    return "unknown"


def _detect_framework(project_root: Path, language: str) -> str:
    if language == "python":
        if (project_root / "manage.py").exists():
            return "django"
        if (project_root / "fastapi").exists():
            return "fastapi"
        pyproject = project_root / "pyproject.toml"
        if pyproject.exists():
            text = pyproject.read_text(encoding="utf-8", errors="ignore").lower()
            if "fastapi" in text:
                return "fastapi"
            if "django" in text:
                return "django"
    if language == "node":
        package_json = project_root / "package.json"
        if package_json.exists():
            text = package_json.read_text(encoding="utf-8", errors="ignore").lower()
            if '"next"' in text:
                return "next"
            if '"express"' in text:
                return "express"
            if '"vite"' in text:
                return "vite"
            if '"react"' in text:
                return "react"
    return ""


def _git_info(project_root: Path) -> dict[str, Any]:
    def run(*args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return ""
        return result.stdout.strip()

    branch = run("branch", "--show-current")
    status = run("status", "--short")
    return {
        "branch": branch,
        "dirty": bool(status),
        "status_lines": len([line for line in status.splitlines() if line.strip()]),
    }


def _read_legacy_feature_list(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"features": [], "metadata": {}}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"features": [], "metadata": {}}


def _latest_archived_feature_list(project_root: Path) -> Path | None:
    archive_dir = project_root / ".claude" / "progress" / "archive"
    if not archive_dir.exists():
        return None
    files = sorted(archive_dir.glob("feature-list.*.json"))
    return files[-1] if files else None


def default_onboarding_state(project_root: Path) -> dict[str, Any]:
    language = _detect_language(project_root)
    framework = _detect_framework(project_root, language)
    onboarding_mode = _classify_onboarding_mode(project_root)
    return {
        "repo": {
            "root": str(project_root),
            "name": project_root.name,
            "language": language,
            "framework": framework,
            "branch": "",
            "dirty": False,
            "status_lines": 0,
        },
        "onboarding_mode": onboarding_mode,
        "current_phase": "repo_detect",
        "ready": False,
        "started_at": None,
        "updated_at": _utcnow(),
        "phases": _phase_records(),
        "entity_counts": {
            "projects": 0,
            "features": 0,
            "tasks": 0,
        },
        "kb_status": {
            "collection": (
                "forward-engineering"
                if onboarding_mode == "forward_engineering"
                else "system-docs"
            ),
            "document_count": 0,
            "extraction_method": "cli",
            "lint_passed": False,
            "quality_gate": "pending",
            "message": "Knowledge base not yet generated.",
            "cli_result": None,
        },
        "scan_summary": {},
        "archives": [],
        "errors": [],
    }


def load_onboarding_state(project_root: Path) -> dict[str, Any]:
    path = _state_path(project_root)
    if not path.exists():
        return default_onboarding_state(project_root)
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_onboarding_state(project_root)

    # Refresh volatile repo metadata on read.
    repo = state.setdefault("repo", {})
    repo.setdefault("root", str(project_root))
    repo.setdefault("name", project_root.name)
    repo.setdefault("language", _detect_language(project_root))
    repo.setdefault("framework", _detect_framework(project_root, repo["language"]))
    state.setdefault("onboarding_mode", _classify_onboarding_mode(project_root))
    state.setdefault("phases", _phase_records())
    state.setdefault("entity_counts", {"projects": 0, "features": 0, "tasks": 0})
    state.setdefault(
        "kb_status",
        {
            "collection": (
                "forward-engineering"
                if state["onboarding_mode"] == "forward_engineering"
                else "system-docs"
            ),
            "document_count": 0,
            "extraction_method": "cli",
            "lint_passed": False,
            "quality_gate": "pending",
            "message": "Knowledge base not yet generated.",
            "cli_result": None,
        },
    )
    state.setdefault("scan_summary", {})
    state.setdefault("archives", [])
    state.setdefault("errors", [])
    state.setdefault("current_phase", "repo_detect")
    state.setdefault("ready", False)
    state["updated_at"] = _utcnow()
    return state


def save_onboarding_state(project_root: Path, state: Mapping[str, Any]) -> None:
    builder_dir = _builder_dir(project_root)
    builder_dir.mkdir(parents=True, exist_ok=True)
    path = _state_path(project_root)
    path.write_text(json.dumps(dict(state), indent=2), encoding="utf-8")


async def publish_onboarding_snapshot(project_root: Path) -> None:
    await get_dashboard_stream_hub().publish_onboarding(load_onboarding_state(project_root))


def onboarding_mode(project_root: Path) -> bool:
    state = load_onboarding_state(project_root)
    return not state.get("ready", False)


def _set_phase_state(
    state: dict[str, Any],
    phase_id: str,
    *,
    status: str,
    message: str = "",
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    phase = next(phase for phase in state["phases"] if phase["id"] == phase_id)
    phase["status"] = status
    phase["message"] = message
    phase["result"] = result
    phase["error"] = error
    if status == "running":
        phase["started_at"] = _utcnow()
    if status in {"passed", "failed", "blocked"}:
        phase["finished_at"] = _utcnow()
    state["current_phase"] = phase_id
    state["updated_at"] = _utcnow()
    if error:
        state["errors"].append({"phase": phase_id, "error": error, "timestamp": _utcnow()})


def _project_lock(project_root: Path) -> asyncio.Lock:
    key = str(project_root.resolve())
    lock = _pipeline_locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _pipeline_locks[key] = lock
    return lock


async def start_onboarding(project_root: Path, session_factory: Any) -> dict[str, Any]:
    state = load_onboarding_state(project_root)
    if state.get("ready"):
        return state

    if not await _preflight_onboarding_claude(project_root, state):
        save_onboarding_state(project_root, state)
        await publish_onboarding_snapshot(project_root)
        return state

    lock = _project_lock(project_root)
    if lock.locked():
        return state

    async def run() -> None:
        async with lock:
            await _run_pipeline(project_root, session_factory)

    asyncio.create_task(run())
    state["started_at"] = state.get("started_at") or _utcnow()
    save_onboarding_state(project_root, state)
    await publish_onboarding_snapshot(project_root)
    return state


async def retry_onboarding(project_root: Path, session_factory: Any) -> dict[str, Any]:
    state = load_onboarding_state(project_root)
    if state.get("ready"):
        return state
    for phase in state["phases"]:
        if phase["status"] in {"failed", "blocked"}:
            phase["status"] = "pending"
            phase["error"] = None
            phase["message"] = ""
    state["errors"] = []
    save_onboarding_state(project_root, state)
    await publish_onboarding_snapshot(project_root)
    return await start_onboarding(project_root, session_factory)


async def _preflight_onboarding_claude(project_root: Path, state: dict[str, Any]) -> bool:
    from autonomous_agent_builder.config import get_settings

    if state.get("onboarding_mode") == "forward_engineering":
        return True

    availability = await check_claude_availability(
        workspace_path=project_root,
        model=get_settings().agent.implementation_model,
        allowed_tools=["Bash"],
        permission_mode=get_settings().agent.permission_mode,
    )
    if availability.available:
        return True

    message = (
        "Onboarding disabled: Claude unavailable for KB extraction. "
        f"backend={availability.backend}. {availability.message}"
    )
    _set_phase_state(
        state,
        "repo_detect",
        status="blocked",
        message=message,
        result={
            "blocked_reason": "claude_unavailable",
            "backend": availability.backend,
        },
        error=message,
    )
    state["ready"] = False
    state["kb_status"]["quality_gate"] = "blocked"
    state["kb_status"]["message"] = message
    return False


async def _run_pipeline(project_root: Path, session_factory: Any) -> None:
    state = load_onboarding_state(project_root)
    state["started_at"] = state.get("started_at") or _utcnow()
    save_onboarding_state(project_root, state)
    await publish_onboarding_snapshot(project_root)

    try:
        detect_result = await _run_repo_detect(project_root, state)
        save_onboarding_state(project_root, state)
        await publish_onboarding_snapshot(project_root)

        async with session_factory() as db:
            project_result = await _run_project_seed(project_root, state, db)
            await db.commit()
        save_onboarding_state(project_root, state)
        await publish_onboarding_snapshot(project_root)

        scan_result = await _run_repo_scan(project_root, state, detect_result)
        save_onboarding_state(project_root, state)
        await publish_onboarding_snapshot(project_root)

        async with session_factory() as db:
            await _run_work_item_seed(project_root, state, db, scan_result, project_result)
            await db.commit()
        save_onboarding_state(project_root, state)
        await publish_onboarding_snapshot(project_root)

        if state.get("onboarding_mode") == "forward_engineering":
            _defer_kb_for_forward_engineering(state)
            save_onboarding_state(project_root, state)
            await publish_onboarding_snapshot(project_root)
        else:
            await _run_kb_extract(project_root, state)
            save_onboarding_state(project_root, state)
            await publish_onboarding_snapshot(project_root)

            await _run_kb_validate(project_root, state)
            save_onboarding_state(project_root, state)
            await publish_onboarding_snapshot(project_root)

        _set_phase_state(
            state,
            "ready",
            status="passed",
            message="Repo onboarding complete. Dashboard is ready for operational use.",
            result={"ready": True},
        )
        state["ready"] = True
        state["current_phase"] = "ready"
        # Onboarding completed successfully — drop any transient errors from prior
        # failed attempts so the dashboard doesn't show stale blockers.
        state["errors"] = []
        save_onboarding_state(project_root, state)

        async with session_factory() as db:
            await ensure_init_project_bootstrap_session(project_root, db)
            await db.commit()

        await publish_onboarding_snapshot(project_root)
    except Exception as exc:
        current_phase = state.get("current_phase", "repo_detect")
        _set_phase_state(
            state,
            current_phase,
            status="failed",
            message=str(exc),
            error=str(exc),
        )
        state["ready"] = False
        save_onboarding_state(project_root, state)
        await publish_onboarding_snapshot(project_root)


async def _run_repo_detect(project_root: Path, state: dict[str, Any]) -> dict[str, Any]:
    _set_phase_state(
        state,
        "repo_detect",
        status="running",
        message="Inspecting repo identity, environment, and archiving legacy generated artifacts.",
    )

    repo = state["repo"]
    repo["language"] = _detect_language(project_root)
    repo["framework"] = _detect_framework(project_root, repo["language"])
    repo.update(_git_info(project_root))
    state["onboarding_mode"] = _classify_onboarding_mode(project_root)
    state["kb_status"]["collection"] = (
        "forward-engineering"
        if state["onboarding_mode"] == "forward_engineering"
        else "system-docs"
    )

    archive_result = _archive_legacy_inputs(project_root)
    state["archives"] = archive_result["archives"]

    _set_phase_state(
        state,
        "repo_detect",
        status="passed",
        message="Repository identity detected and legacy generated artifacts archived.",
        result={
            "repo": repo,
            "archives": archive_result["archives"],
            "onboarding_mode": state["onboarding_mode"],
        },
    )
    return {"repo": repo, "archives": archive_result["archives"]}


def _archive_legacy_inputs(project_root: Path) -> dict[str, Any]:
    archives: list[dict[str, Any]] = []
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    archive_root = _archive_root(project_root) / stamp
    archive_root.mkdir(parents=True, exist_ok=True)

    builder_dir = _builder_dir(project_root)
    legacy_knowledge = builder_dir / "knowledge"
    if legacy_knowledge.exists() and any(path.is_file() for path in legacy_knowledge.rglob("*")):
        dest = archive_root / "knowledge"
        shutil.copytree(legacy_knowledge, dest, dirs_exist_ok=True)
        shutil.rmtree(legacy_knowledge)
        legacy_knowledge.mkdir(parents=True, exist_ok=True)
        archives.append({"type": "knowledge", "path": str(dest)})

    legacy_db = builder_dir / "agent_builder.db"
    if legacy_db.exists() and _db_has_operational_state(legacy_db):
        db_dest = archive_root / "agent_builder.db"
        shutil.copy2(legacy_db, db_dest)
        archives.append({"type": "database", "path": str(db_dest)})

    feature_list = project_root / ".claude" / "progress" / "feature-list.json"
    if feature_list.exists():
        progress_archive = project_root / ".claude" / "progress" / "archive"
        progress_archive.mkdir(parents=True, exist_ok=True)
        feature_dest = progress_archive / f"feature-list.{stamp}.json"
        shutil.move(str(feature_list), feature_dest)
        archives.append({"type": "legacy_feature_list", "path": str(feature_dest)})

    return {"archives": archives}


def _db_has_operational_state(db_path: Path) -> bool:
    con: sqlite3.Connection | None = None
    try:
        con = sqlite3.connect(db_path)
        cur = con.cursor()
        for table in ("projects", "features", "tasks", "workspaces", "agent_runs", "approvals"):
            try:
                count = cur.execute(f"select count(*) from {table}").fetchone()
            except sqlite3.Error:
                continue
            if count and int(count[0]) > 0:
                return True
        return False
    except sqlite3.Error:
        return False
    finally:
        if con is not None:
            con.close()


async def _run_project_seed(
    project_root: Path,
    state: dict[str, Any],
    db: AsyncSession,
) -> dict[str, Any]:
    _set_phase_state(
        state,
        "project_seed",
        status="running",
        message="Seeding builder-managed project record and clearing legacy operational state.",
    )

    await _clear_operational_state(db)
    repo = state["repo"]
    project = Project(
        name=repo["name"],
        description=f"Onboarded enterprise repo at {project_root}",
        repo_url=str(project_root),
        language=repo["language"],
    )
    db.add(project)
    await db.flush()
    await db.refresh(project)
    state["entity_counts"]["projects"] = 1
    _set_phase_state(
        state,
        "project_seed",
        status="passed",
        message="Builder project record created.",
        result={"project_id": project.id},
    )
    return {"project_id": project.id}


async def _clear_operational_state(db: AsyncSession) -> None:
    for model in (
        ChatMessage,
        ChatSession,
        AgentRunEvent,
        AgentRun,
        Approval,
        ApprovalGate,
        GateResult,
        Workspace,
        Task,
        Feature,
        Project,
    ):
        await db.execute(delete(model))


async def _run_repo_scan(
    project_root: Path,
    state: dict[str, Any],
    detect_result: dict[str, Any],
) -> dict[str, Any]:
    _set_phase_state(
        state,
        "repo_scan",
        status="running",
        message="Scanning repo surfaces, entrypoints, docs, and compatibility inputs.",
    )

    top_level_dirs = sorted(
        p.name for p in project_root.iterdir() if p.is_dir() and not p.name.startswith(".")
    )
    important_files = []
    for name in [
        "README.md",
        "pyproject.toml",
        "package.json",
        "manage.py",
        "go.mod",
        "Cargo.toml",
    ]:
        if (project_root / name).exists():
            important_files.append(name)

    entrypoints = []
    for pattern in ["main.py", "app.py", "server.py", "manage.py", "src/**/main.py"]:
        for match in project_root.glob(pattern):
            if match.is_file():
                entrypoints.append(match.relative_to(project_root).as_posix())
    entrypoints = sorted(set(entrypoints))[:10]

    legacy_path = _latest_archived_feature_list(project_root)
    legacy_data = (
        _read_legacy_feature_list(legacy_path) if legacy_path else {"features": [], "metadata": {}}
    )

    scan = {
        "top_level_dirs": top_level_dirs[:12],
        "important_files": important_files,
        "entrypoints": entrypoints,
        "has_frontend": (project_root / "frontend").exists(),
        "has_api": any(name in top_level_dirs for name in ("src", "api", "server")),
        "legacy_feature_count": len(legacy_data.get("features", [])),
        "legacy_feature_titles": [f.get("title", "") for f in legacy_data.get("features", [])[:5]],
        "onboarding_mode": state.get("onboarding_mode", "reverse_engineering"),
        "repo": detect_result["repo"],
    }
    state["scan_summary"] = scan
    _set_phase_state(
        state,
        "repo_scan",
        status="passed",
        message="Repo scan complete. Surfaces and compatibility inputs recorded.",
        result=scan,
    )
    return scan


async def _run_work_item_seed(
    project_root: Path,
    state: dict[str, Any],
    db: AsyncSession,
    scan_result: dict[str, Any],
    project_result: dict[str, Any],
) -> None:
    _set_phase_state(
        state,
        "work_item_seed",
        status="running",
        message=(
            "Creating initial forward-engineering backlog for a clean-slate repo."
            if state.get("onboarding_mode") == "forward_engineering"
            else "Creating initial features and tasks from deterministic repo scan outputs."
        ),
    )

    project_id = project_result["project_id"]
    feature_specs = (
        _forward_engineering_feature_specs(scan_result)
        if state.get("onboarding_mode") == "forward_engineering"
        else _system_docs_feature_specs()
    )

    if scan_result.get("has_frontend") and state.get("onboarding_mode") != "forward_engineering":
        feature_specs.insert(
            1,
            {
                "title": "Map operator-facing UI and dashboard delivery path",
                "description": (
                    "Capture the frontend entrypoints and dashboard delivery mechanics "
                    "detected during scan."
                ),
                "status": FeatureStatus.BACKLOG,
                "tasks": [
                    (
                        "Inspect frontend shell and routes",
                        "Review the operator-facing frontend shell and route inventory.",
                    ),
                    (
                        "Verify dashboard deployment path",
                        "Confirm how built frontend assets reach the embedded dashboard runtime.",
                    ),
                ],
            },
        )

    features_created = 0
    tasks_created = 0
    for spec in feature_specs:
        feature = Feature(
            project_id=project_id,
            title=spec["title"],
            description=spec["description"],
            status=spec["status"],
            priority=max(0, 100 - features_created),
        )
        db.add(feature)
        await db.flush()
        features_created += 1
        for title, description in spec["tasks"]:
            task = Task(
                feature_id=feature.id,
                title=title,
                description=description,
                status=TaskStatus.PENDING,
                complexity=1,
            )
            db.add(task)
            tasks_created += 1

    state["entity_counts"]["features"] = features_created
    state["entity_counts"]["tasks"] = tasks_created
    _set_phase_state(
        state,
        "work_item_seed",
        status="passed",
        message=(
            "Initial forward-engineering features and tasks were seeded for the clean-slate repo."
            if state.get("onboarding_mode") == "forward_engineering"
            else "Initial builder-managed features and tasks were seeded from scan outputs."
        ),
        result={
            "features": features_created,
            "tasks": tasks_created,
            "onboarding_mode": state.get("onboarding_mode"),
        },
    )


def _system_docs_feature_specs() -> list[dict[str, Any]]:
    return [
        {
            "title": "Establish runtime and architecture baseline",
            "description": (
                "Map the runtime entrypoints, configuration, and architectural seams "
                "detected in the repository scan."
            ),
            "status": FeatureStatus.PLANNING,
            "tasks": [
                (
                    "Review runtime entrypoints",
                    "Inspect detected entrypoints and runtime boot paths for the "
                    "onboarded repository.",
                ),
                (
                    "Confirm architecture seams",
                    "Capture the major subsystem boundaries and ownership surfaces from the deterministic scan.",
                ),
            ],
        },
        {
            "title": "Seed operator workspace and backlog surfaces",
            "description": (
                "Create the initial operational work items so the dashboard starts "
                "from builder-managed state instead of legacy files."
            ),
            "status": FeatureStatus.BACKLOG,
            "tasks": [
                (
                    "Validate builder-managed setup state",
                    "Confirm setup/backlog views reflect builder-managed features and tasks.",
                ),
                (
                    "Review archived legacy backlog input",
                    "Use archived compatibility inputs only as reference while builder state becomes canonical.",
                ),
            ],
        },
        {
            "title": "Generate and validate initial local knowledge base",
            "description": (
                "Produce the first seed system-docs collection and validate it "
                "through onboarding quality checks."
            ),
            "status": FeatureStatus.PLANNING,
            "tasks": [
                (
                    "Extract seed system docs",
                    "Generate seed system-doc documents from the repo scan.",
                ),
                (
                    "Validate KB quality",
                    "Run lint and quality gates over the generated knowledge base.",
                ),
            ],
        },
    ]


def _forward_engineering_feature_specs(scan_result: dict[str, Any]) -> list[dict[str, Any]]:
    language = scan_result.get("repo", {}).get("language", "unknown")
    return [
        {
            "title": "Define product intent and first user journey",
            "description": (
                "Turn the clean-slate repo into a concrete delivery target by "
                "clarifying the app goal, user flow, and first shippable slice."
            ),
            "status": FeatureStatus.PLANNING,
            "tasks": [
                (
                    "Capture product goal and success criteria",
                    "Write down the intended app outcome, target user, and the first "
                    "milestone that should be considered useful.",
                ),
                (
                    "Define the first end-to-end journey",
                    "Choose one concrete workflow that the first implementation slice "
                    "must support.",
                ),
            ],
        },
        {
            "title": "Bootstrap the initial application skeleton",
            "description": (
                f"Create the first runnable {language} app shell and choose the "
                "delivery shape for the initial vertical slice."
            ),
            "status": FeatureStatus.BACKLOG,
            "tasks": [
                (
                    "Choose runtime and scaffolding approach",
                    "Decide the primary framework, layout, and startup path for the "
                    "new app.",
                ),
                (
                    "Create the initial runnable shell",
                    "Add the minimal application entrypoint, structure, and "
                    "configuration needed to start implementation.",
                ),
            ],
        },
        {
            "title": "Establish verification and builder-managed delivery flow",
            "description": (
                "Set the repo up so future work can run through builder-managed "
                "backlog, quality checks, and reviewable evidence."
            ),
            "status": FeatureStatus.BACKLOG,
            "tasks": [
                (
                    "Define verification commands and quality expectations",
                    "Choose the first test, lint, or build commands that will prove "
                    "the app is progressing safely.",
                ),
                (
                    "Prepare the first reviewable implementation task",
                    "Convert the first vertical slice into a bounded implementation "
                    "task ready for builder execution.",
                ),
            ],
        },
    ]


def _extract_json_object(text: str) -> dict[str, Any]:
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            payload, _end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    raise ValueError("No JSON object found in agent output.")


async def _run_builder_kb_extract_via_agent(
    project_root: Path, output_dir: str = "system-docs"
) -> _AgentKbExtractRunResult:
    from autonomous_agent_builder.config import get_settings

    source_root = Path(__file__).resolve().parents[1]
    command = (
        f"env PYTHONPATH={shlex.quote(str(source_root))} "
        f"{shlex.quote(sys.executable)} -m autonomous_agent_builder.cli.main "
        f"knowledge extract --force --output-dir {shlex.quote(output_dir)} --json"
    )
    prompt = (
        "Use the Bash tool exactly once to run this argv-safe command in the workspace:\n"
        f"{command}\n\n"
        "After the command completes, return only the raw JSON stdout from that command. "
        "Do not add markdown fences, explanation, or any extra text."
    )

    backend = resolve_claude_backend()
    if backend == "cli":
        raw_output = await run_claude_prompt(
            prompt,
            workspace_path=project_root,
            model=get_settings().agent.implementation_model,
            allowed_tools=["Bash"],
            permission_mode=get_settings().agent.permission_mode,
        )
    else:
        from claude_agent_sdk import (
            AssistantMessage,
            ClaudeAgentOptions,
            HookMatcher,
            ResultMessage,
            query,
        )

        from autonomous_agent_builder.agents.hooks import validate_bash_argv

        options = ClaudeAgentOptions(
            model=get_settings().agent.implementation_model,
            cwd=project_root,
            allowed_tools=["Bash"],
            max_turns=3,
            permission_mode=get_settings().agent.permission_mode,
        )
        options.hooks = {
            "PreToolUse": [
                HookMatcher(
                    matcher="Bash",
                    hooks=[validate_bash_argv],
                    timeout=30.0,
                )
            ]
        }

        output_parts: list[str] = []
        async for message in query(prompt=prompt, options=options):
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if hasattr(block, "text") and block.text:
                        output_parts.append(block.text)
            elif isinstance(message, ResultMessage):
                break

        raw_output = "\n".join(output_parts).strip()

    if not raw_output:
        raise RuntimeError("Claude returned no output for KB extraction.")

    payload = _extract_json_object(raw_output)
    return _AgentKbExtractRunResult(payload=payload, raw_output=raw_output)


def _project_kb_status_from_cli_result(
    cli_result: dict[str, Any], existing_status: dict[str, Any]
) -> dict[str, Any]:
    documents = cli_result.get("documents", [])
    lint = cli_result.get("lint", {})
    lint_counts = lint.get("counts", {})
    validation = cli_result.get("validation", {})
    deterministic = validation.get("deterministic", {})
    advisory = validation.get("agent_advisory", {})

    projected = dict(existing_status)
    projected.update(
        {
            "collection": existing_status.get("collection", "system-docs"),
            "document_count": len(documents),
            "extraction_method": cli_result.get("engine", "deterministic"),
            "lint_passed": bool(lint.get("passed", False)),
            "lint_counts": {
                "passed": int(lint_counts.get("passed", 0)),
                "failed": int(lint_counts.get("failed", 0)),
                "total": int(lint_counts.get("total", 0)),
            },
            "rule_based_score": float(deterministic.get("score", 0.0)),
            "rule_based_summary": str(deterministic.get("summary", "")),
            "blocking_docs": list(deterministic.get("blocking_docs", [])),
            "non_blocking_docs": list(deterministic.get("non_blocking_docs", [])),
            "claim_failures": list(deterministic.get("claim_failures", [])),
            "unresolved_claims": list(deterministic.get("unresolved_claims", [])),
            "contradicted_claims": list(deterministic.get("contradicted_claims", [])),
            "agent_score": float(advisory.get("score", 0.0)),
            "agent_summary": str(advisory.get("summary", "")),
            "quality_gate": "passed" if deterministic.get("passed", False) else "failed",
            "message": str(cli_result.get("operator_message", "")),
            "cli_result": cli_result,
        }
    )
    return projected


def _defer_kb_for_forward_engineering(state: dict[str, Any]) -> None:
    message = "Project knowledge is deferred until the initial scope and architecture are concrete."
    state["kb_status"].update(
        {
            "collection": "forward-engineering",
            "document_count": 0,
            "extraction_method": "deferred",
            "lint_passed": False,
            "quality_gate": "deferred",
            "message": message,
            "cli_result": None,
        }
    )
    _set_phase_state(
        state,
        "kb_extract",
        status="passed",
        message=message,
        result={"skipped": True, "reason": "forward_engineering_onboarding"},
    )
    _set_phase_state(
        state,
        "kb_validate",
        status="passed",
        message=message,
        result={"skipped": True, "reason": "forward_engineering_onboarding"},
    )


async def ensure_init_project_bootstrap_session(
    project_root: Path,
    db: AsyncSession,
) -> str | None:
    repo_identity = str(project_root.resolve())
    workspace_cwd = repo_identity
    state = load_onboarding_state(project_root)
    if not state.get("ready"):
        return None
    if state.get("onboarding_mode") != "forward_engineering":
        return None

    feature_list = project_root / ".claude" / "progress" / "feature-list.json"
    if feature_list.exists():
        return None

    result = await db.execute(
        select(ChatSession)
        .options(selectinload(ChatSession.events), selectinload(ChatSession.messages))
        .order_by(ChatSession.created_at.desc())
    )
    sessions = result.scalars().all()
    for session in sessions:
        if session.repo_identity and session.repo_identity != repo_identity:
            continue
        if session.workspace_cwd and session.workspace_cwd != workspace_cwd:
            continue
        if not session.repo_identity:
            session.repo_identity = repo_identity
        if not session.workspace_cwd:
            session.workspace_cwd = workspace_cwd
        if session.events:
            first_event = session.events[0]
            if (
                first_event.event_type == "assistant_message"
                and first_event.payload_json.get("content") == _INIT_PROJECT_BOOTSTRAP_MESSAGE
            ):
                return session.id
        if session.messages:
            first_message = session.messages[0]
            if (
                first_message.role == "assistant"
                and first_message.content == _INIT_PROJECT_BOOTSTRAP_MESSAGE
                ):
                    return session.id

    session = ChatSession(repo_identity=repo_identity, workspace_cwd=workspace_cwd)
    db.add(session)
    await db.flush()
    db.add(
        ChatEvent(
            session_id=session.id,
            event_type="assistant_message",
            payload_json={"content": _INIT_PROJECT_BOOTSTRAP_MESSAGE, "final": True},
            status="completed",
        )
    )
    db.add(
        ChatMessage(
            session_id=session.id,
            role="assistant",
            content=_INIT_PROJECT_BOOTSTRAP_MESSAGE,
        )
    )
    await db.flush()
    return session.id


def write_feature_list_file(project_root: Path, payload: dict[str, Any]) -> Path:
    feature_list_path = project_root / ".claude" / "progress" / "feature-list.json"
    feature_list_path.parent.mkdir(parents=True, exist_ok=True)
    feature_list_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return feature_list_path


async def _run_kb_extract(project_root: Path, state: dict[str, Any]) -> None:
    _set_phase_state(
        state,
        "kb_extract",
        status="running",
        message="Dispatching Claude to run the canonical `builder knowledge extract --json` flow.",
    )

    result = await _run_builder_kb_extract_via_agent(project_root)
    kb_status = _project_kb_status_from_cli_result(result.payload, state["kb_status"])
    kb_status["raw_agent_output"] = result.raw_output
    state["kb_status"] = kb_status
    _set_phase_state(
        state,
        "kb_extract",
        status="passed",
        message=result.payload.get("operator_message", "KB extraction command completed."),
        result={
            "documents": kb_status["document_count"],
            "errors": result.payload.get("errors", []),
            "next_step": result.payload.get("next_step", {}),
        },
    )


async def _run_kb_validate(project_root: Path, state: dict[str, Any]) -> None:
    _set_phase_state(
        state,
        "kb_validate",
        status="running",
        message="Projecting KB validation state from the canonical CLI result.",
    )

    kb_status = state["kb_status"]
    cli_result = kb_status.get("cli_result")
    if not isinstance(cli_result, dict):
        kb_status["quality_gate"] = "failed"
        kb_status["message"] = "KB CLI result missing from extraction phase."
        raise RuntimeError(kb_status["message"])

    kb_status.update(_project_kb_status_from_cli_result(cli_result, kb_status))
    lint_payload = cli_result.get("lint", {})
    deterministic = cli_result.get("validation", {}).get("deterministic", {})
    next_step = cli_result.get("next_step", {})
    operator_message = cli_result.get("operator_message", "KB validation failed.")

    if next_step.get("action") == "stop" or not deterministic.get("passed", False):
        kb_status["quality_gate"] = "failed"
        kb_status["message"] = operator_message
        raise RuntimeError(operator_message)

    _set_phase_state(
        state,
        "kb_validate",
        status="passed",
        message=operator_message,
        result={
            "lint_passed": bool(lint_payload.get("passed", False)),
            "lint_counts": kb_status.get("lint_counts", {}),
            "rule_based_score": float(deterministic.get("score", 0.0)),
            "blocking_docs": kb_status.get("blocking_docs", []),
            "claim_failures": kb_status.get("claim_failures", []),
            "agent_summary": kb_status.get("agent_summary", ""),
            "next_step": next_step,
        },
    )


async def load_feature_list_from_db(db: AsyncSession, project_root: Path) -> dict[str, Any]:
    result = await db.execute(select(Project).order_by(Project.created_at.desc()))
    project = result.scalars().first()
    if not project:
        return {
            "project_name": project_root.name,
            "total": 0,
            "done": 0,
            "pending": 0,
            "features": [],
        }

    feature_result = await db.execute(
        select(Feature)
        .where(Feature.project_id == project.id)
        .order_by(Feature.priority.desc(), Feature.created_at.desc())
    )
    features = feature_result.scalars().all()
    done = len([feature for feature in features if feature.status == FeatureStatus.DONE])
    pending = len(features) - done
    return {
        "project_name": project.name,
        "total": len(features),
        "done": done,
        "pending": pending,
        "features": [
            {
                "id": feature.id,
                "title": feature.title,
                "description": feature.description or "",
                "status": feature.status.value
                if hasattr(feature.status, "value")
                else str(feature.status),
                "priority": str(feature.priority),
                "acceptance_criteria": [],
                "dependencies": [],
            }
            for feature in features
        ],
    }
