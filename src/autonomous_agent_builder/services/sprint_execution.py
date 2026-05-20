"""Sprint-level execution planning for forward-engineering delivery."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autonomous_agent_builder.config import get_settings
from autonomous_agent_builder.db.models import (
    DesignDocument,
    Feature,
    FeatureStatus,
    Project,
    Sprint,
    SprintPhase,
    Task,
    TaskPhase,
    TaskStatus,
)
from autonomous_agent_builder.observability.runtime_optimization import runtime_decision_summary
from autonomous_agent_builder.runtime.factory import resolve_runtime_config

SPRINT_EXECUTION_SCHEMA_VERSION = "1"
SPRINT_EXECUTION_KEY = "sprint_execution"
SPRINT_PLAN_DOC_TYPE = "sprint_plan"
SPRINT_DESIGN_DOC_TYPE = "sprint_design"

BOARD_SPRINT_EXECUTION_KEYS: tuple[str, ...] = (
    "sprint_id",
    "plan_id",
    "design_id",
    "mode",
    "feature_id",
    "task_key",
    "batch_id",
    "batch_index",
    "execution_mode",
    "parallel_group",
    "depends_on_batches",
    "recommended_model",
    "recommended_effort",
    "context_strategy",
)
BOARD_RUNTIME_TOOL_STRATEGY_KEYS: tuple[str, ...] = (
    "runtime_sdk",
    "primary_tools",
    "telemetry",
)
BOARD_SPRINT_PLAN_DETAIL_KEYS: tuple[str, ...] = (
    "schema_version",
    "plan_id",
    "project_id",
    "project_name",
    "mode",
    "planning_model",
    "planning_effort",
    "single_sprint_plan",
    "single_sprint_design",
    "context_strategy",
    "sprint_item_ids",
    "implementation_order",
)
BOARD_SPRINT_DESIGN_DETAIL_KEYS: tuple[str, ...] = (
    "schema_version",
    "design_id",
    "plan_id",
    "project_id",
    "schema_data_model_direction",
    "route_api_ui_conventions",
    "testing_strategy",
)

_RISK_KEYWORDS: dict[str, tuple[str, ...]] = {
    "schema": ("schema", "database", "sqlite", "table", "migration", "persist"),
    "api": ("api", "endpoint", "route", "contract", "json"),
    "auth": ("auth", "login", "oauth", "permission", "session"),
    "security": ("security", "secret", "token", "password", "encrypt"),
    "integration": ("integration", "webhook", "external", "third-party", "service"),
    "migration": ("migration", "migrate", "backfill"),
    "ambiguous_ux": ("editable", "override", "workflow", "approval", "discoverable"),
}
_HIGH_RISK_FLAGS = {"auth", "security", "integration", "migration"}
_SPRINT_TASK_TEMPLATES: tuple[dict[str, str], ...] = (
    {
        "key": "setup-domain-model",
        "title": "Set up domain model for {feature}",
        "purpose": "Create the data shape, local state, and shared types needed by the feature.",
        "ownership": "domain model, state shape, fixture data, and focused tests",
    },
    {
        "key": "ui-shell",
        "title": "Build UI shell for {feature}",
        "purpose": "Expose the feature through visible navigation, layout, and input surfaces.",
        "ownership": "visible route, components, navigation, empty/loading/error states",
    },
    {
        "key": "core-behavior",
        "title": "Implement core behavior for {feature}",
        "purpose": "Wire the primary user action and acceptance criteria through the app.",
        "ownership": "feature behavior, validation, event handling, and state transitions",
    },
    {
        "key": "persistence",
        "title": "Wire persistence for {feature}",
        "purpose": "Persist and restore the feature state across navigation or reload.",
        "ownership": "storage adapter, hydration, migration-safe defaults, persistence tests",
    },
    {
        "key": "tests-browser-proof",
        "title": "Verify {feature}",
        "purpose": "Add focused tests and browser proof that the approved feature is shippable.",
        "ownership": "unit/integration checks, browser acceptance, and verification evidence",
    },
)


def compact_board_runtime_tool_strategy(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Return only operator-facing runtime routing facts for Board snapshots."""
    if not isinstance(payload, dict):
        return {}
    return {key: payload[key] for key in BOARD_RUNTIME_TOOL_STRATEGY_KEYS if key in payload}


def compact_board_sprint_execution(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Keep Board snapshots small by excluding implementation prompt payloads."""
    if not isinstance(payload, dict):
        return {}
    compact = {key: payload[key] for key in BOARD_SPRINT_EXECUTION_KEYS if key in payload}
    runtime_strategy = compact_board_runtime_tool_strategy(payload.get("runtime_tool_strategy"))
    if runtime_strategy:
        compact["runtime_tool_strategy"] = runtime_strategy
    return compact


def compact_board_sprint_plan_details(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Summarize sprint plan details without embedding per-task implementation briefs."""
    if not isinstance(payload, dict):
        return {}
    compact = {key: payload[key] for key in BOARD_SPRINT_PLAN_DETAIL_KEYS if key in payload}
    runtime_strategy = compact_board_runtime_tool_strategy(payload.get("runtime_tool_strategy"))
    if runtime_strategy:
        compact["runtime_tool_strategy"] = runtime_strategy
    parallelism = payload.get("parallelism")
    if isinstance(parallelism, dict):
        compact["parallelism"] = {
            key: parallelism[key]
            for key in ("strategy", "sequential_batches", "parallel_batches")
            if key in parallelism
        }
    return compact


def compact_board_sprint_design_details(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Summarize shared sprint design details for dashboard rendering."""
    if not isinstance(payload, dict):
        return {}
    compact = {key: payload[key] for key in BOARD_SPRINT_DESIGN_DETAIL_KEYS if key in payload}
    shared_decisions = payload.get("shared_architecture_decisions")
    if isinstance(shared_decisions, list):
        compact["shared_architecture_decisions"] = [
            str(item) for item in shared_decisions if str(item).strip()
        ]
        compact["shared_concerns"] = compact["shared_architecture_decisions"]
    return compact
_LOW_RISK_SPRINT_TASK_TEMPLATES: tuple[dict[str, str], ...] = (
    {
        "key": "core-app-behavior",
        "title": "Implement core app behavior for {feature}",
        "purpose": "Create the visible UI, domain state, and primary user actions for the feature.",
        "ownership": "visible UI, state model, validation, and event handling",
    },
    {
        "key": "persistence-tests",
        "title": "Cover persistence and tests for {feature}",
        "purpose": "Wire required persistence and deterministic tests for the approved behavior.",
        "ownership": "storage behavior, focused unit/integration tests, and edge cases",
    },
    {
        "key": "browser-verification",
        "title": "Verify {feature} for shipping",
        "purpose": "Run final checks and browser-visible proof that the feature is shippable.",
        "ownership": "build/test/lint/browser acceptance evidence",
    },
)


def build_sprint_execution_plan(project: Project, features: list[Feature]) -> dict[str, Any]:
    """Create a compact deterministic sprint-level implementation plan."""
    ordered = sorted(features, key=lambda item: (-int(item.priority or 0), str(item.created_at)))
    feature_ids = [feature.id for feature in ordered]
    plan_id = _stable_id("sprint-plan", project.id, feature_ids)
    runtime_model = _selected_runtime_model()
    runtime_decisions = runtime_decision_summary(_selected_runtime_kind())
    phase_decisions = {
        str(item.get("phase")): item
        for item in runtime_decisions.get("phase_decisions", [])
        if isinstance(item, dict)
    }
    implementation_decision = phase_decisions.get("implementation", {})
    batches: list[dict[str, Any]] = []
    task_specs: list[dict[str, Any]] = []
    dependency_graph: dict[str, list[str]] = {}
    previous_batch_by_feature: dict[str, str] = {}

    for feature in ordered:
        dependencies = [
            str(item).strip() for item in (feature.dependencies or []) if str(item).strip()
        ]
        risk_flags = _risk_flags(feature)
        high_risk = bool(set(risk_flags) & _HIGH_RISK_FLAGS)
        for template in _task_templates_for_feature(feature, risk_flags):
            batch_id = f"batch-{len(batches) + 1:03d}"
            previous_batch_id = previous_batch_by_feature.get(feature.id, "")
            depends_on_batches = [previous_batch_id] if previous_batch_id else []
            dependency_graph[batch_id] = depends_on_batches + dependencies
            task_key = template["key"]
            execution_mode, parallel_group, orchestration_reason = _task_orchestration_policy(
                task_key=task_key,
                feature_count=len(ordered),
                high_risk=high_risk,
                depends_on_batches=depends_on_batches,
                feature_dependencies=dependencies,
            )
            implementation_brief = _task_implementation_brief(
                feature,
                template,
                risk_flags,
                dependencies,
            )
            spec = {
                "feature_id": feature.id,
                "task_key": task_key,
                "title": template["title"].format(feature=feature.title),
                "purpose": template["purpose"],
                "ownership": template["ownership"],
                "depends_on_batches": depends_on_batches,
                "risk_flags": risk_flags,
                "high_risk": high_risk,
                "execution_mode": execution_mode,
                "parallel_group": parallel_group,
                "orchestration_reason": orchestration_reason,
                "recommended_model": runtime_model,
                "recommended_effort": "high" if high_risk else "medium",
                "implementation_brief": implementation_brief,
                "file_ownership_hint": template["ownership"],
                "runtime_decision": implementation_decision,
            }
            task_specs.append(spec)
            batches.append(
                {
                    "id": batch_id,
                    "index": len(batches) + 1,
                    "feature_ids": [feature.id],
                    "titles": [spec["title"]],
                    "task_key": task_key,
                    "task_title": spec["title"],
                    "risk_flags": risk_flags,
                    "high_risk": high_risk,
                    "execution_mode": execution_mode,
                    "parallel_group": parallel_group,
                    "orchestration_reason": orchestration_reason,
                    "depends_on_batches": depends_on_batches,
                    "recommended_model": runtime_model,
                    "recommended_effort": spec["recommended_effort"],
                    "context_strategy": (
                        "single shared sprint plan/design, then compact task implementation brief"
                    ),
                    "runtime_tool_strategy": _runtime_tool_strategy(),
                    "runtime_decision": implementation_decision,
                    "implementation_briefs": {feature.id: implementation_brief},
                    "file_ownership_hint": spec["file_ownership_hint"],
                }
            )
            previous_batch_by_feature[feature.id] = batch_id

    return {
        "schema_version": SPRINT_EXECUTION_SCHEMA_VERSION,
        "plan_id": plan_id,
        "project_id": project.id,
        "project_name": project.name,
        "mode": "sprint_task_breakdown",
        "planning_model": runtime_model,
        "planning_effort": "high" if any(batch["high_risk"] for batch in batches) else "medium",
        "single_sprint_plan": True,
        "single_sprint_design": True,
        "parallelism": _parallelism_summary(batches),
        "context_strategy": (
            "Keep sprint-level reasoning in the plan/design docs; implementation prompts receive "
            "only the compact batch brief, shared design summary, and local file ownership hint."
        ),
        "runtime_tool_strategy": _runtime_tool_strategy(),
        "runtime_decision_summary": runtime_decisions,
        "phase_runtime_decisions": runtime_decisions.get("phase_decisions", []),
        "deterministic_script_candidates": runtime_decisions.get(
            "deterministic_script_candidates",
            [],
        ),
        "sprint_item_ids": feature_ids,
        "task_specs": task_specs,
        "dependency_graph": dependency_graph,
        "implementation_order": [spec["task_key"] for spec in task_specs],
        "batches": batches,
        "shared_architecture_concerns": _shared_architecture_concerns(batches),
    }


def build_sprint_design(project: Project, plan: dict[str, Any]) -> dict[str, Any]:
    """Create the shared read-only design handoff for a sprint plan."""
    risk_flags = sorted(
        {
            flag
            for batch in plan.get("batches", [])
            for flag in batch.get("risk_flags", [])
            if isinstance(flag, str)
        }
    )
    return {
        "schema_version": SPRINT_EXECUTION_SCHEMA_VERSION,
        "design_id": _stable_id("sprint-design", project.id, plan.get("sprint_item_ids", [])),
        "plan_id": plan["plan_id"],
        "project_id": project.id,
        "shared_architecture_decisions": [
            "Use one coherent app architecture across all approved sprint items.",
            "Keep implementation scoped to the current task or dependency batch workspace.",
            "Preserve generated-app discoverability through visible navigation and controls.",
        ],
        "schema_data_model_direction": _schema_direction(risk_flags),
        "user_flow": [
            "User lands on the generated app and can discover the approved feature.",
            "User performs the primary action through visible controls.",
            "The app shows the resulting state and preserves it across navigation or reload.",
        ],
        "state_data_model": {
            "direction": _schema_direction(risk_flags),
            "scope": "Model only the approved sprint feature and the state needed to verify it.",
        },
        "component_module_boundaries": [
            "domain/state foundation",
            "visible UI shell",
            "core behavior handler",
            "persistence adapter",
            "verification proof",
        ],
        "task_file_ownership_hints": [
            {
                "task_key": str(spec.get("task_key", "")),
                "title": str(spec.get("title", "")),
                "ownership": str(spec.get("ownership", "")),
            }
            for spec in plan.get("task_specs", [])
            if isinstance(spec, dict)
        ],
        "route_api_ui_conventions": (
            "Expose every shipped feature through visible routes, links, forms, or buttons; "
            "do not rely on guessed URLs for acceptance."
        ),
        "testing_strategy": (
            "Run focused unit/integration tests for each batch and browser acceptance after "
            "the generated app changes."
        ),
        "implementation_orchestration": {
            "single_plan": True,
            "single_design": True,
            "parallelism": plan.get("parallelism", {}),
            "runtime_tool_strategy": plan.get("runtime_tool_strategy", {}),
            "context_strategy": plan.get("context_strategy", ""),
        },
        "generated_app_acceptance": [
            "feature is discoverable through visible navigation",
            "user can operate it through forms/buttons/links",
            "state persists after navigation or reload",
            "no guessed URL is required",
            "generated app runs from the disposable repo",
        ],
        "task_specific_design_required": [],
    }


async def persist_sprint_execution_artifacts(
    db: AsyncSession,
    project: Project,
    features: list[Feature],
) -> dict[str, Any]:
    """Persist sprint plan/design metadata and generated sprint task slices."""
    plan = build_sprint_execution_plan(project, features)
    design = build_sprint_design(project, plan)
    sprint = await _ensure_sprint_record(db, project, plan)
    feature_by_id = {feature.id: feature for feature in features}
    tasks_by_key = await _tasks_by_sprint_key(db, sprint.id, features)

    generated_tasks: list[Task] = []
    batch_by_task_key: dict[tuple[str, str], dict[str, Any]] = {}
    for batch in plan["batches"]:
        for feature_id in batch.get("feature_ids", []):
            batch_by_task_key[(str(feature_id), str(batch.get("task_key", "")))] = batch

    for spec in plan.get("task_specs", []):
        feature = feature_by_id.get(str(spec.get("feature_id", "")))
        if feature is None:
            continue
        task_key = str(spec.get("task_key", "")).strip()
        task = tasks_by_key.get((feature.id, task_key))
        if task is None:
            task = Task(
                feature_id=feature.id,
                title=str(spec.get("title") or feature.title),
                description=str(spec.get("purpose") or feature.description or ""),
                status=TaskStatus.PENDING,
                phase=TaskPhase.PLANNING,
                complexity=2 if spec.get("high_risk") else 1,
            )
            db.add(task)
            await db.flush()
            tasks_by_key[(feature.id, task_key)] = task
        batch = batch_by_task_key.get((feature.id, task_key), {})
        depends_on = dict(task.depends_on or {})
        depends_on[SPRINT_EXECUTION_KEY] = {
            "schema_version": SPRINT_EXECUTION_SCHEMA_VERSION,
            "sprint_id": sprint.id,
            "plan_id": plan["plan_id"],
            "design_id": design["design_id"],
            "mode": plan["mode"],
            "feature_id": feature.id,
            "task_key": task_key,
            "batch_id": batch.get("id", ""),
            "batch_index": batch.get("index", 0),
            "skip_task_planning": True,
            "skip_task_design": True,
            "risk_flags": batch.get("risk_flags", []),
            "recommended_model": batch.get("recommended_model", _selected_runtime_model()),
            "recommended_effort": batch.get("recommended_effort", "medium"),
            "execution_mode": batch.get("execution_mode", "sequential"),
            "parallel_group": batch.get("parallel_group", ""),
            "orchestration_reason": batch.get("orchestration_reason", ""),
            "depends_on_batches": batch.get("depends_on_batches", []),
            "context_strategy": batch.get("context_strategy", ""),
            "runtime_tool_strategy": batch.get("runtime_tool_strategy", {}),
            "runtime_decision": batch.get("runtime_decision", {}),
            "implementation_brief": spec.get("implementation_brief")
            or batch.get("implementation_briefs", {}).get(feature.id, ""),
            "file_ownership_hint": spec.get("file_ownership_hint")
            or batch.get("file_ownership_hint", ""),
        }
        phase_context = dict(depends_on.get("phase_context") or {})
        phase_context.setdefault("planning_context", _compact_json(plan))
        phase_context.setdefault("design_context", _compact_json(design))
        depends_on["phase_context"] = phase_context
        task.depends_on = depends_on
        generated_tasks.append(task)

    if generated_tasks:
        holder = generated_tasks[0]
        plan_doc = await _ensure_design_document(
            db,
            holder.id,
            SPRINT_PLAN_DOC_TYPE,
            "Sprint execution plan",
            plan,
        )
        design_doc = await _ensure_design_document(
            db,
            holder.id,
            SPRINT_DESIGN_DOC_TYPE,
            "Sprint shared design",
            design,
        )
        sprint.plan_doc_id = plan_doc.id
        sprint.design_doc_id = design_doc.id
    sprint.approved_feature_ids = [feature.id for feature in features]
    sprint.generated_task_ids = [task.id for task in generated_tasks]
    sprint.phase = SprintPhase.IMPLEMENTATION if generated_tasks else SprintPhase.BLOCKED
    sprint.verification_status = "pending"

    for feature in features:
        feature.status = FeatureStatus.SPRINT_PLANNED

    await db.flush()
    return {"sprint": sprint, "plan": plan, "design": design, "tasks": generated_tasks}


def task_uses_sprint_plan(task: Task) -> bool:
    payload = _task_sprint_execution(task)
    return bool(payload.get("skip_task_planning"))


def task_uses_sprint_design(task: Task) -> bool:
    payload = _task_sprint_execution(task)
    return bool(payload.get("skip_task_design"))


def sprint_execution_context(task: Task) -> str:
    payload = _task_sprint_execution(task)
    if not payload:
        return ""
    return _compact_json(
        {
            "batch_id": payload.get("batch_id"),
            "batch_index": payload.get("batch_index"),
            "risk_flags": payload.get("risk_flags", []),
            "recommended_model": payload.get("recommended_model"),
            "recommended_effort": payload.get("recommended_effort"),
            "implementation_brief": payload.get("implementation_brief"),
            "file_ownership_hint": payload.get("file_ownership_hint"),
        }
    )


def _task_sprint_execution(task: Task) -> dict[str, Any]:
    depends_on = task.depends_on if isinstance(task.depends_on, dict) else {}
    payload = depends_on.get(SPRINT_EXECUTION_KEY)
    return payload if isinstance(payload, dict) else {}


def _selected_runtime_model() -> str:
    try:
        config = resolve_runtime_config(get_settings())
    except Exception:
        return "runtime_selected"
    model = str(config.get("model") or "").strip()
    return model or "runtime_selected"


def _selected_runtime_kind() -> str:
    try:
        config = resolve_runtime_config(get_settings())
    except Exception:
        return "claude_agent_sdk"
    sdk = str(config.get("sdk") or "claude")
    return "codex_sdk" if sdk.startswith("codex") else "claude_agent_sdk"


def _runtime_tool_strategy() -> dict[str, Any]:
    try:
        config = resolve_runtime_config(get_settings())
    except Exception:
        return {
            "runtime_sdk": "unknown",
            "primary_tools": ["workspace tools", "deterministic commands"],
            "telemetry": "builder run history",
        }
    sdk = str(config.get("sdk") or "")
    if sdk == "codex_sdk":
        return {
            "runtime_sdk": sdk,
            "primary_tools": [
                "Codex app-server JSON-RPC events",
                "workspace shell commands",
                "patch/file edits",
                "requestUserInput only for operator decisions",
            ],
            "telemetry": "thread/tokenUsage/updated and turn lifecycle events",
            "avoid": ["codex exec compatibility behavior", "duplicating full sprint context"],
        }
    if sdk == "claude":
        return {
            "runtime_sdk": sdk,
            "primary_tools": [
                "Claude Agent SDK tool permissions",
                "builder MCP tools",
                "workspace commands",
            ],
            "telemetry": "Claude SDK OTEL summary signals",
            "avoid": ["raw transcript telemetry", "duplicating full sprint context"],
        }
    return {
        "runtime_sdk": sdk or "runtime_selected",
        "primary_tools": ["runtime-native tools", "workspace commands"],
        "telemetry": "builder run history",
        "avoid": ["duplicating full sprint context"],
    }


def _parallelism_summary(batches: list[dict[str, Any]]) -> dict[str, Any]:
    parallel_batches = [
        batch["id"] for batch in batches if batch.get("execution_mode") == "parallel"
    ]
    sequential_batches = [
        batch["id"] for batch in batches if batch.get("execution_mode") == "sequential"
    ]
    return {
        "strategy": "single shared plan/design with dependency-batch execution",
        "parallel_batches": parallel_batches,
        "sequential_batches": sequential_batches,
        "max_parallel_tasks": max(len(parallel_batches), 1) if parallel_batches else 1,
        "reason": (
            "Default to sequential task workspaces when generated-app slices share files; "
            "only independent, non-conflicting batches should run in parallel."
        ),
    }


def _task_orchestration_policy(
    *,
    task_key: str,
    feature_count: int,
    high_risk: bool,
    depends_on_batches: list[str],
    feature_dependencies: list[str],
) -> tuple[str, str, str]:
    if high_risk:
        return (
            "sequential",
            "",
            "High-risk slices stay sequential so schema, security, or integration changes land in order.",
        )
    if feature_dependencies:
        return (
            "sequential",
            "",
            "Backlog dependencies must ship before this task starts.",
        )
    if depends_on_batches:
        return (
            "sequential",
            "",
            "This task depends on the previous feature batch and should reuse its committed context.",
        )
    if feature_count > 1:
        return (
            "parallel",
            f"independent-{task_key}",
            "Independent backlog items can start this batch in parallel from the shared sprint plan.",
        )
    return (
        "sequential",
        "",
        "Single-feature sprint tasks share files, so Builder keeps mutations ordered while auto-dispatching.",
    )


async def _tasks_by_feature(db: AsyncSession, features: list[Feature]) -> dict[str, Task]:
    feature_ids = [feature.id for feature in features]
    if not feature_ids:
        return {}
    rows = await db.execute(
        select(Task).where(Task.feature_id.in_(feature_ids)).order_by(Task.created_at)
    )
    result: dict[str, Task] = {}
    for task in rows.scalars().all():
        result.setdefault(task.feature_id, task)
    return result


async def _ensure_sprint_record(
    db: AsyncSession,
    project: Project,
    plan: dict[str, Any],
) -> Sprint:
    feature_ids = [str(value) for value in plan.get("sprint_item_ids", [])]
    result = await db.execute(
        select(Sprint).where(Sprint.project_id == project.id).order_by(Sprint.created_at.desc())
    )
    sprints = list(result.scalars().all())
    for sprint in sprints:
        if list(sprint.approved_feature_ids or []) == feature_ids:
            if sprint.phase == SprintPhase.SHIPPED and sprint.verification_status == "passed":
                continue
            sprint.phase = SprintPhase.PLANNING
            return sprint
    sprint = Sprint(
        project_id=project.id,
        label=f"Sprint {len(sprints) + 1}",
        phase=SprintPhase.PLANNING,
        approved_feature_ids=feature_ids,
        verification_status="pending",
    )
    db.add(sprint)
    await db.flush()
    return sprint


async def _tasks_by_sprint_key(
    db: AsyncSession,
    sprint_id: str,
    features: list[Feature],
) -> dict[tuple[str, str], Task]:
    feature_ids = [feature.id for feature in features]
    if not feature_ids:
        return {}
    rows = await db.execute(
        select(Task).where(Task.feature_id.in_(feature_ids)).order_by(Task.created_at)
    )
    result: dict[tuple[str, str], Task] = {}
    for task in rows.scalars().all():
        payload = dict((task.depends_on or {}).get(SPRINT_EXECUTION_KEY) or {})
        if str(payload.get("sprint_id", "")) != sprint_id:
            continue
        task_key = str(payload.get("task_key", "")).strip()
        if task_key:
            result.setdefault((task.feature_id, task_key), task)
    return result


async def _ensure_design_document(
    db: AsyncSession,
    task_id: str,
    doc_type: str,
    title: str,
    content: dict[str, Any],
) -> DesignDocument:
    existing = await db.execute(
        select(DesignDocument)
        .where(DesignDocument.task_id == task_id)
        .where(DesignDocument.doc_type == doc_type)
    )
    doc = existing.scalar_one_or_none()
    serialized = json.dumps(content, ensure_ascii=True, indent=2, sort_keys=True)
    if doc is not None:
        doc.title = title
        doc.content = serialized
        return doc
    doc = DesignDocument(
        task_id=task_id,
        doc_type=doc_type,
        title=title,
        content=serialized,
    )
    db.add(doc)
    await db.flush()
    return doc


def _risk_flags(feature: Feature) -> list[str]:
    text = " ".join(
        [
            str(feature.title or ""),
            str(feature.description or ""),
            " ".join(str(item) for item in (feature.acceptance_criteria or [])),
        ]
    ).lower()
    flags = [
        flag
        for flag, keywords in _RISK_KEYWORDS.items()
        if any(keyword in text for keyword in keywords)
    ]
    return flags or ["routine"]


def _task_templates_for_feature(
    feature: Feature,
    risk_flags: list[str],
) -> tuple[dict[str, str], ...]:
    if set(risk_flags) & _HIGH_RISK_FLAGS:
        return _SPRINT_TASK_TEMPLATES
    return _LOW_RISK_SPRINT_TASK_TEMPLATES


def _implementation_brief(feature: Feature, risk_flags: list[str], dependencies: list[str]) -> str:
    parts = [f"Deliver {feature.title}: {feature.description}".strip()]
    if dependencies:
        parts.append("Respect dependencies: " + ", ".join(dependencies))
    parts.append("Risk flags: " + ", ".join(risk_flags))
    if feature.acceptance_criteria:
        criteria = "; ".join(str(item) for item in feature.acceptance_criteria)
        parts.append("Acceptance: " + criteria)
    return " ".join(part for part in parts if part)


def _task_implementation_brief(
    feature: Feature,
    template: dict[str, str],
    risk_flags: list[str],
    dependencies: list[str],
) -> str:
    parts = [
        f"{template['title'].format(feature=feature.title)}.",
        template["purpose"],
        f"Feature outcome: {feature.description}".strip(),
        f"Task ownership: {template['ownership']}.",
        "Risk flags: " + ", ".join(risk_flags),
    ]
    if dependencies:
        parts.append("Respect feature dependencies: " + ", ".join(dependencies))
    if feature.acceptance_criteria:
        criteria = "; ".join(str(item) for item in feature.acceptance_criteria)
        parts.append("Acceptance: " + criteria)
    return " ".join(part for part in parts if part)


def _file_ownership_hint(feature: Feature, risk_flags: list[str]) -> str:
    title = str(feature.title or "feature").lower().replace(" ", "-")
    if "schema" in risk_flags:
        return (
            f"models/routes/templates/tests for {title}; include database setup changes if needed"
        )
    if "api" in risk_flags:
        return f"routes/api/tests for {title}"
    return f"app files and tests for {title}"


def _shared_architecture_concerns(batches: list[dict[str, Any]]) -> list[str]:
    flags = sorted(
        {flag for batch in batches for flag in batch.get("risk_flags", []) if flag != "routine"}
    )
    concerns = ["generated-app discoverability", "batch-scoped verification"]
    if flags:
        concerns.append("shared " + ", ".join(flags) + " decisions")
    return concerns


def _schema_direction(risk_flags: list[str]) -> str:
    if "schema" in risk_flags or "migration" in risk_flags:
        return "Define shared schema changes once in sprint design, then apply them in batch order."
    return "No shared schema change required unless an implementation batch discovers one."


def _task_specific_design_required(plan: dict[str, Any]) -> list[str]:
    required: list[str] = []
    for batch in plan.get("batches", []):
        if batch.get("high_risk"):
            required.extend(str(feature_id) for feature_id in batch.get("feature_ids", []))
    return required


def _stable_id(prefix: str, project_id: str, feature_ids: list[str]) -> str:
    digest = hashlib.sha1("|".join([project_id, *feature_ids]).encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}"


def _compact_json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
