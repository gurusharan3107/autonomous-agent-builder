from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from autonomous_agent_builder.db.models import (
    BacklogItemType,
    ChatMessage,
    ChatSession,
    Feature,
    FeatureStatus,
    Project,
    Task,
)


def _write_builder_bootstrap(project_root: Path) -> None:
    builder_dir = project_root / ".agent-builder"
    builder_dir.mkdir(exist_ok=True)
    (builder_dir / "config.yaml").write_text("project:\n  name: test\n", encoding="utf-8")
    (builder_dir / "agent_builder.db").write_text("", encoding="utf-8")


def _write_forward_feature_list(project_root: Path) -> None:
    progress_dir = project_root / ".claude" / "progress"
    progress_dir.mkdir(parents=True, exist_ok=True)
    (progress_dir / "feature-list.json").write_text(
        """
{
  "metadata": {"project": "todo-app", "done": 2, "pending": 3},
  "features": [
    {
      "id": "feature-01",
      "title": "Todo Creation And Editing",
      "description": "Users can create and edit todos.",
      "status": "done",
      "priority": 100,
      "acceptance_criteria": ["Create a todo"],
      "dependencies": []
    },
    {
      "id": "feature-02",
      "title": "Local Browser Persistence",
      "description": "Todos persist locally.",
      "status": "done",
      "priority": 90,
      "acceptance_criteria": ["Refresh keeps todos"],
      "dependencies": ["feature-01"]
    },
    {
      "id": "feature-03",
      "title": "Today List View",
      "description": "Group todos by due state.",
      "status": "backlog",
      "priority": 80,
      "acceptance_criteria": ["Today todos are visible"],
      "dependencies": ["feature-01", "feature-02"]
    }
  ]
}
""".strip()
        + "\n",
        encoding="utf-8",
    )


@pytest.fixture
async def onboarding_client(test_db, tmp_path):
    from autonomous_agent_builder.api.app import create_app

    app = create_app()
    app.state.project_root = tmp_path
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_onboarding_status_defaults_to_not_ready(onboarding_client, test_db, tmp_path):
    (tmp_path / ".agent-builder").mkdir()

    resp = await onboarding_client.get("/api/onboarding/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ready"] is False
    assert data["current_phase"] == "repo_detect"
    assert [phase["id"] for phase in data["phases"]] == [
        "repo_detect",
        "project_seed",
        "repo_scan",
        "work_item_seed",
        "kb_extract",
        "kb_validate",
        "ready",
    ]


@pytest.mark.asyncio
async def test_onboarding_status_refreshes_repo_identity_after_rename(
    onboarding_client, test_db, tmp_path
):
    builder_dir = tmp_path / ".agent-builder"
    builder_dir.mkdir()
    (builder_dir / "onboarding-state.json").write_text(
        """
{
  "repo": {
    "root": "/tmp/old-name",
    "name": "old-name",
    "language": "python",
    "framework": "fastapi",
    "branch": "",
    "dirty": false,
    "status_lines": 0
  },
  "onboarding_mode": "reverse_engineering",
  "current_phase": "repo_detect",
  "ready": false,
  "updated_at": "2026-04-24T20:56:21.122542+00:00",
  "phases": [],
  "entity_counts": {"projects": 0, "features": 0, "tasks": 0},
  "kb_status": {
    "collection": "system-docs",
    "document_count": 0,
    "extraction_method": "cli",
    "lint_passed": false,
    "quality_gate": "blocked",
    "message": "stale",
    "cli_result": null
  },
  "scan_summary": {},
  "archives": [],
  "errors": []
}
""".strip(),
        encoding="utf-8",
    )

    resp = await onboarding_client.get("/api/onboarding/status")
    assert resp.status_code == 200
    data = resp.json()

    assert data["repo"]["root"] == str(tmp_path)
    assert data["repo"]["name"] == tmp_path.name


@pytest.mark.asyncio
async def test_onboarding_start_seeds_builder_state(test_db, sample_workspace, monkeypatch):
    _write_builder_bootstrap(sample_workspace)

    import autonomous_agent_builder.onboarding as onboarding
    from autonomous_agent_builder.api.app import create_app
    from autonomous_agent_builder.claude_runtime import ClaudeAvailability

    async def fake_kb_extract(project_root, state):
        onboarding._set_phase_state(
            state,
            "kb_extract",
            status="passed",
            message="KB extracted for test.",
            result={"documents": 3},
        )
        state["kb_status"]["document_count"] = 3

    async def fake_kb_validate(project_root, state):
        onboarding._set_phase_state(
            state,
            "kb_validate",
            status="passed",
            message="KB validated for test.",
            result={"lint_passed": True, "rule_based_score": 1.0},
        )
        state["kb_status"]["lint_passed"] = True
        state["kb_status"]["quality_gate"] = "passed"
        state["kb_status"]["message"] = "KB validated for test."

    async def fake_check_claude(*args, **kwargs):
        return ClaudeAvailability(available=True, backend="cli", message="")

    monkeypatch.setattr(onboarding, "_run_kb_extract", fake_kb_extract)
    monkeypatch.setattr(onboarding, "_run_kb_validate", fake_kb_validate)
    monkeypatch.setattr(onboarding, "check_claude_availability", fake_check_claude)

    app = create_app()
    app.state.project_root = sample_workspace
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        start = await client.post("/api/onboarding/start")
        assert start.status_code == 200

        data = None
        for _ in range(40):
            await asyncio.sleep(0.05)
            status = await client.get("/api/onboarding/status")
            data = status.json()
            if data["ready"]:
                break

        assert data is not None
        assert data["ready"] is True
        assert data["entity_counts"]["projects"] == 1
        assert data["entity_counts"]["features"] >= 3
        assert data["entity_counts"]["tasks"] >= 6
        assert data["kb_status"]["document_count"] == 3

        board = await client.get("/api/dashboard/features")
        board_data = board.json()
        assert board_data["total"] >= 3
        assert board_data["project_name"] == sample_workspace.name


@pytest.mark.asyncio
async def test_onboarding_start_blocks_when_claude_unavailable(
    test_db, sample_workspace, monkeypatch
):
    _write_builder_bootstrap(sample_workspace)

    import autonomous_agent_builder.onboarding as onboarding
    from autonomous_agent_builder.api.app import create_app
    from autonomous_agent_builder.claude_runtime import ClaudeAvailability

    async def fake_check_claude(*args, **kwargs):
        return ClaudeAvailability(
            available=False,
            backend="cli",
            message="Claude CLI is not installed or not on PATH.",
        )

    monkeypatch.setattr(onboarding, "check_claude_availability", fake_check_claude)

    app = create_app()
    app.state.project_root = sample_workspace
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        start = await client.post("/api/onboarding/start")
        assert start.status_code == 200
        data = start.json()

    assert data["ready"] is False
    assert data["current_phase"] == "repo_detect"
    phase = next(item for item in data["phases"] if item["id"] == "repo_detect")
    assert phase["status"] == "blocked"
    assert "Onboarding disabled: Claude unavailable" in phase["message"]


@pytest.mark.asyncio
async def test_onboarding_kb_validate_projects_cli_result(sample_workspace):
    import autonomous_agent_builder.onboarding as onboarding

    state = onboarding.default_onboarding_state(sample_workspace)
    state["kb_status"]["cli_result"] = {
        "passed": True,
        "phase": "kb_extract",
        "engine": "deterministic",
        "documents": [{"filename": "project-overview.md"}],
        "lint": {
            "passed": True,
            "counts": {"passed": 1, "failed": 0, "total": 1},
        },
        "validation": {
            "deterministic": {
                "passed": True,
                "score": 1.0,
                "summary": "Deterministic KB validation passed.",
            },
            "agent_advisory": {
                "available": True,
                "passed": False,
                "score": 0.57,
                "summary": "Agent suggests richer repo-specific content.",
                "recommendations": ["Add code-specific evidence"],
            },
        },
        "operator_message": "Knowledge base generated; deterministic gate passed.",
        "next_step": {
            "action": "continue",
            "reason": "deterministic_validation_passed",
            "target_phase": "kb_ready",
            "recommended_command": "",
        },
    }

    await onboarding._run_kb_validate(sample_workspace, state)

    assert state["kb_status"]["lint_passed"] is True
    assert state["kb_status"]["lint_counts"] == {"passed": 1, "failed": 0, "total": 1}
    assert state["kb_status"]["rule_based_score"] == 1.0
    assert state["kb_status"]["agent_summary"] == "Agent suggests richer repo-specific content."
    phase = next(p for p in state["phases"] if p["id"] == "kb_validate")
    assert phase["status"] == "passed"


@pytest.mark.asyncio
async def test_onboarding_kb_extract_uses_agent_cli_contract(sample_workspace, monkeypatch):
    (sample_workspace / ".agent-builder").mkdir(exist_ok=True)

    import autonomous_agent_builder.onboarding as onboarding

    calls: dict[str, object] = {}

    async def fake_run(project_root, output_dir="system-docs"):
        calls["project_root"] = project_root
        calls["output_dir"] = output_dir
        return onboarding._AgentKbExtractRunResult(
            payload={
                "passed": True,
                "phase": "kb_extract",
                "engine": "deterministic",
                "documents": [{"filename": "project-overview.md"}],
                "errors": [],
                "lint": {
                    "passed": True,
                    "counts": {"passed": 1, "failed": 0, "total": 1},
                },
                "validation": {
                    "deterministic": {
                        "passed": True,
                        "score": 0.9,
                        "summary": "Deterministic KB validation passed.",
                    },
                    "agent_advisory": {
                        "available": False,
                        "passed": False,
                        "score": 0.0,
                        "summary": "",
                        "recommendations": [],
                    },
                },
                "operator_message": "Knowledge base generated; deterministic gate passed.",
                "next_step": {
                    "action": "continue",
                    "reason": "deterministic_validation_passed",
                    "target_phase": "kb_ready",
                    "recommended_command": "",
                },
            },
            raw_output='{"passed": true}',
        )

    monkeypatch.setattr(onboarding, "_run_builder_kb_extract_via_agent", fake_run)

    state = onboarding.default_onboarding_state(sample_workspace)

    await onboarding._run_kb_extract(sample_workspace, state)

    assert calls["project_root"] == sample_workspace
    assert calls["output_dir"] == "system-docs"
    assert state["kb_status"]["extraction_method"] == "deterministic"
    assert state["kb_status"]["document_count"] == 1
    assert state["kb_status"]["cli_result"]["next_step"]["action"] == "continue"
    phase = next(p for p in state["phases"] if p["id"] == "kb_extract")
    assert phase["status"] == "passed"


@pytest.mark.asyncio
async def test_onboarding_agent_kb_command_uses_plain_extract_contract(
    sample_workspace, monkeypatch
):
    (sample_workspace / ".agent-builder").mkdir(exist_ok=True)

    import autonomous_agent_builder.onboarding as onboarding

    captured: dict[str, object] = {}

    async def fake_run_claude_prompt(prompt, **kwargs):
        captured["prompt"] = prompt
        captured["kwargs"] = kwargs
        return '{"passed": true, "documents": [], "errors": [], "lint": {"passed": true, "counts": {"passed": 0, "failed": 0, "total": 0}}, "validation": {"deterministic": {"passed": true, "score": 1.0, "summary": "ok"}, "agent_advisory": {"available": false, "passed": false, "score": 0.0, "summary": "", "recommendations": []}}, "operator_message": "ok", "next_step": {"action": "continue", "reason": "ok", "target_phase": "kb_ready", "recommended_command": ""}}'

    monkeypatch.setattr(onboarding, "resolve_claude_backend", lambda: "cli")
    monkeypatch.setattr(onboarding, "run_claude_prompt", fake_run_claude_prompt)

    await onboarding._run_builder_kb_extract_via_agent(sample_workspace)

    assert (
        f"env PYTHONPATH={Path(onboarding.__file__).resolve().parents[1]} "
        f"{sys.executable} -m autonomous_agent_builder.cli.main knowledge extract --force --output-dir system-docs --json"
        in captured["prompt"]
    )
    assert "--skip-claude-preflight" not in captured["prompt"]


@pytest.mark.asyncio
async def test_onboarding_kb_validate_stops_when_cli_contract_fails(sample_workspace):
    import autonomous_agent_builder.onboarding as onboarding

    state = onboarding.default_onboarding_state(sample_workspace)
    state["kb_status"]["cli_result"] = {
        "passed": False,
        "phase": "kb_extract",
        "engine": "deterministic",
        "documents": [{"filename": "project-overview.md"}],
        "lint": {
            "passed": False,
            "counts": {"passed": 0, "failed": 1, "total": 1},
        },
        "validation": {
            "deterministic": {
                "passed": False,
                "score": 0.0,
                "summary": "Knowledge base lint failed.",
            },
            "agent_advisory": {
                "available": False,
                "passed": False,
                "score": 0.0,
                "summary": "",
                "recommendations": [],
            },
        },
        "operator_message": "Knowledge base lint failed.",
        "next_step": {
            "action": "stop",
            "reason": "lint_failed",
            "target_phase": "",
            "recommended_command": "builder knowledge lint --verbose",
        },
    }

    with pytest.raises(RuntimeError, match="Knowledge base lint failed."):
        await onboarding._run_kb_validate(sample_workspace, state)

    assert state["kb_status"]["quality_gate"] == "failed"


@pytest.mark.asyncio
async def test_onboarding_start_clean_slate_defers_forward_backlog_until_agent_interview(
    test_db, tmp_path, monkeypatch
):
    _write_builder_bootstrap(tmp_path)
    (tmp_path / "README.md").write_text("# Clean Slate\n")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "clean-slate"\nversion = "0.1.0"\n')

    import autonomous_agent_builder.onboarding as onboarding
    from autonomous_agent_builder.api.app import create_app

    calls = {"check_claude": 0, "kb_extract": 0, "kb_validate": 0}

    async def fake_check_claude(*args, **kwargs):
        calls["check_claude"] += 1
        raise AssertionError("Claude preflight should be skipped for clean-slate onboarding")

    async def fake_kb_extract(*args, **kwargs):
        calls["kb_extract"] += 1
        raise AssertionError("KB extract should be deferred for clean-slate onboarding")

    async def fake_kb_validate(*args, **kwargs):
        calls["kb_validate"] += 1
        raise AssertionError("KB validate should be deferred for clean-slate onboarding")

    monkeypatch.setattr(onboarding, "check_claude_availability", fake_check_claude)
    monkeypatch.setattr(onboarding, "_run_kb_extract", fake_kb_extract)
    monkeypatch.setattr(onboarding, "_run_kb_validate", fake_kb_validate)

    app = create_app()
    app.state.project_root = tmp_path
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        start = await client.post("/api/onboarding/start")
        assert start.status_code == 200

        for _ in range(50):
            status = await client.get("/api/onboarding/status")
            assert status.status_code == 200
            payload = status.json()
            if payload["ready"]:
                break
            await asyncio.sleep(0.05)
        else:
            raise AssertionError("Onboarding did not reach ready state for clean-slate repo")

    assert calls == {"check_claude": 0, "kb_extract": 0, "kb_validate": 0}
    assert payload["onboarding_mode"] == "forward_engineering"
    assert payload["ready"] is True
    assert payload["entity_counts"] == {"projects": 1, "features": 0, "tasks": 0}
    assert payload["kb_status"]["quality_gate"] == "deferred"
    assert payload["kb_status"]["collection"] == "forward-engineering"

    phases = {phase["id"]: phase for phase in payload["phases"]}
    assert phases["work_item_seed"]["result"] == {
        "features": 0,
        "tasks": 0,
        "onboarding_mode": "forward_engineering",
        "deferred_until": "agent_requirements_interview_complete",
    }
    assert phases["kb_extract"]["status"] == "passed"
    assert phases["kb_validate"]["status"] == "passed"
    assert phases["ready"]["status"] == "passed"

    _engine, factory = test_db
    async with factory() as db:
        backlog = await onboarding.load_feature_list_from_db(db, tmp_path)
        chat_sessions = (await db.execute(select(ChatSession))).scalars().all()
        chat_messages = (await db.execute(select(ChatMessage))).scalars().all()

    assert backlog["features"] == []
    assert chat_sessions == []
    assert chat_messages == []


@pytest.mark.asyncio
async def test_forward_sync_removes_legacy_onboarding_seed_backlog(test_db, tmp_path):
    import autonomous_agent_builder.onboarding as onboarding

    state = onboarding.default_onboarding_state(tmp_path)
    state["onboarding_mode"] = "forward_engineering"
    state["ready"] = True
    onboarding.save_onboarding_state(tmp_path, state)

    _engine, factory = test_db
    async with factory() as db:
        project = Project(
            name=tmp_path.name,
            description=f"Onboarded enterprise repo at {tmp_path}",
            repo_url=str(tmp_path),
            language="unknown",
        )
        db.add(project)
        await db.flush()
        seed_feature = Feature(
            project_id=project.id,
            title="Define product intent and first user journey",
            description="Legacy onboarding seed.",
            status=FeatureStatus.PLANNING,
            priority=100,
        )
        db.add(seed_feature)
        await db.flush()
        db.add(
            Task(
                feature_id=seed_feature.id,
                title="Capture product goal and success criteria",
                description="Legacy onboarding seed task.",
                status="pending",
            )
        )
        await db.commit()

    async with factory() as db:
        changed = await onboarding.sync_forward_engineering_feature_backlog(db, tmp_path)
        await db.commit()

    assert changed is True
    async with factory() as db:
        backlog = await onboarding.load_feature_list_from_db(db, tmp_path)

    assert backlog["features"] == []


@pytest.mark.asyncio
async def test_forward_onboarding_retry_reuses_existing_delivery_project(test_db, tmp_path):
    import autonomous_agent_builder.onboarding as onboarding

    _write_forward_feature_list(tmp_path)
    state = onboarding.default_onboarding_state(tmp_path)
    state["onboarding_mode"] = "forward_engineering"
    state["repo"]["language"] = "node"
    state["repo"]["name"] = tmp_path.name

    _engine, factory = test_db
    async with factory() as db:
        existing_project = Project(
            name=tmp_path.name,
            description=f"Onboarded enterprise repo at {tmp_path}",
            repo_url=str(tmp_path),
            language="node",
        )
        db.add(existing_project)
        await db.flush()
        todo_feature = Feature(
            id="feature-01",
            project_id=existing_project.id,
            title="Todo Creation And Editing",
            description="Already delivered with Codex SDK.",
            status=FeatureStatus.DONE,
            priority=100,
        )
        db.add(todo_feature)
        await db.flush()
        db.add(Task(feature_id=todo_feature.id, title="Shipped Codex task", status="done"))
        await db.commit()

        result = await onboarding._run_project_seed(tmp_path, state, db)
        await onboarding.sync_forward_engineering_feature_backlog(db, tmp_path)
        await db.commit()

        projects = list(
            (
                await db.execute(
                    select(Project)
                    .options(selectinload(Project.features))
                    .order_by(Project.created_at.asc())
                )
            )
            .scalars()
            .all()
        )
        backlog = await onboarding.load_feature_list_from_db(db, tmp_path)

    assert result["project_id"] == existing_project.id
    assert len(projects) == 1
    assert [feature["id"] for feature in backlog["features"]] == [
        "feature-01",
        "feature-02",
        "feature-03",
    ]
    assert backlog["features"][0]["title"] == "Todo Creation And Editing"


@pytest.mark.asyncio
async def test_select_delivery_project_prefers_canonical_feature_backlog_over_setup_project(
    test_db, tmp_path
):
    import autonomous_agent_builder.onboarding as onboarding

    _engine, factory = test_db
    async with factory() as db:
        setup_project = Project(
            name=tmp_path.name,
            description="Builder setup and architecture baseline.",
            repo_url=str(tmp_path),
            language="node",
        )
        product_project = Project(
            name=tmp_path.name,
            description="Generated todo app product backlog.",
            repo_url=str(tmp_path),
            language="node",
        )
        db.add_all([setup_project, product_project])
        await db.flush()
        db.add_all(
            [
                Feature(
                    id="setup-architecture",
                    project_id=setup_project.id,
                    title="Establish runtime and architecture baseline",
                    status=FeatureStatus.PLANNING,
                    item_type=BacklogItemType.FEATURE,
                    priority=100,
                ),
                Feature(
                    id="feature-03",
                    project_id=product_project.id,
                    title="Today List View",
                    status=FeatureStatus.DONE,
                    item_type=BacklogItemType.FEATURE,
                    priority=80,
                ),
                Feature(
                    id="feature-04",
                    project_id=product_project.id,
                    title="Completion Workflow",
                    status=FeatureStatus.DONE,
                    item_type=BacklogItemType.FEATURE,
                    priority=70,
                ),
                Feature(
                    id="feature-05",
                    project_id=product_project.id,
                    title="Focused Task Controls",
                    status=FeatureStatus.BACKLOG,
                    item_type=BacklogItemType.FEATURE,
                    priority=60,
                ),
            ]
        )
        await db.commit()

        selected = await onboarding.select_delivery_project(db, "")

    assert selected is not None
    assert selected.id == product_project.id


def test_classify_onboarding_mode_detects_clean_slate_and_existing_repo(tmp_path, sample_workspace):
    import autonomous_agent_builder.onboarding as onboarding

    clean_slate = tmp_path / "clean-slate"
    clean_slate.mkdir()
    (clean_slate / "README.md").write_text("# Clean Slate\n")
    (clean_slate / "pyproject.toml").write_text(
        '[project]\nname = "clean-slate"\nversion = "0.1.0"\n'
    )

    assert onboarding._classify_onboarding_mode(clean_slate) == "forward_engineering"
    assert onboarding._classify_onboarding_mode(sample_workspace) == "reverse_engineering"


def test_classify_onboarding_mode_treats_non_code_workspace_as_forward_engineering(tmp_path):
    import autonomous_agent_builder.onboarding as onboarding

    workspace = tmp_path / "operator-proof"
    workspace.mkdir()
    (workspace / "notes").mkdir()
    (workspace / "scratch").mkdir()
    (workspace / "notes" / "idea.txt").write_text("plain operator idea\n", encoding="utf-8")
    (workspace / "scratch" / "trace.log").write_text("diagnostic output\n", encoding="utf-8")

    assert onboarding._classify_onboarding_mode(workspace) == "forward_engineering"


def test_classify_onboarding_mode_requires_real_code_inside_code_dirs(tmp_path):
    import autonomous_agent_builder.onboarding as onboarding

    empty_src = tmp_path / "empty-src"
    empty_src.mkdir()
    (empty_src / "src").mkdir()
    (empty_src / "README.md").write_text("# Empty source tree\n", encoding="utf-8")

    code_src = tmp_path / "code-src"
    code_src.mkdir()
    (code_src / "src").mkdir()
    (code_src / "src" / "main.py").write_text("print('ok')\n", encoding="utf-8")

    assert onboarding._classify_onboarding_mode(empty_src) == "forward_engineering"
    assert onboarding._classify_onboarding_mode(code_src) == "reverse_engineering"


def test_ready_forward_engineering_state_preserves_mode_after_code_is_generated(tmp_path):
    import autonomous_agent_builder.onboarding as onboarding

    project_root = tmp_path / "generated-app"
    project_root.mkdir()
    _write_builder_bootstrap(project_root)
    (project_root / "CLAUDE.md").write_text("# Runtime guidance\n", encoding="utf-8")
    (project_root / "requirements.txt").write_text("Flask>=3.0\n", encoding="utf-8")
    package_dir = project_root / "shipcheck"
    package_dir.mkdir()
    (package_dir / "__init__.py").write_text("", encoding="utf-8")
    state = onboarding.default_onboarding_state(project_root)
    state["onboarding_mode"] = "forward_engineering"
    state["current_phase"] = "ready"
    state["ready"] = True
    onboarding.save_onboarding_state(project_root, state)

    loaded = onboarding.load_onboarding_state(project_root)

    assert onboarding._classify_onboarding_mode(project_root) == "reverse_engineering"
    assert loaded["onboarding_mode"] == "forward_engineering"
