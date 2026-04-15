# autonomous-agent-builder

Production-grade autonomous SDLC builder using Claude Agent SDK. Supports Java/Node/Python.

## Commands

| Command | Description |
|---------|-------------|
| `pip install -e ".[dev]"` | Install with dev dependencies |
| `python -m autonomous_agent_builder` | Run the server (port 8000) |
| `pytest` | Run tests |
| `pytest --cov` | Run tests with coverage |
| `ruff check .` | Lint |
| `ruff format .` | Format |
| `docker compose -f docker/docker-compose.yml up` | Run with PostgreSQL |
| `cd frontend && npm run dev` | React dev server (port 5173, proxies /api to 8000) |
| `cd frontend && npm run build` | Build React SPA to `frontend/dist/` |

## Architecture

```
src/autonomous_agent_builder/
├── api/                    # FastAPI REST API + routes
├── agents/
│   ├── definitions.py      # AgentDefinitions (versioned, immutable at execution)
│   ├── tool_registry.py    # ToolRegistry contract (keystone — schema discovery)
│   ├── runner.py            # query() dispatch + ResultMessage cost + SDK errors
│   ├── hooks.py             # PreToolUse (safety) + PostToolUse (audit) + hook wiring
│   └── tools/               # @tool definitions (workspace_tools, git_tools)
├── orchestrator/
│   ├── orchestrator.py      # Deterministic dispatch (task_status → phase handler)
│   └── gate_feedback.py     # FAIL → autofix → retry → CAPABILITY_LIMIT
├── security/
│   ├── prompt_inspector.py  # Two-layer prompt injection detection (HIGH/MEDIUM/LOW)
│   ├── egress_monitor.py    # Network destination logging from Bash commands
│   └── permission_store.py  # Per-project tool permission cache with TTL
├── quality_gates/           # Concurrent gates: Ruff, pytest, Semgrep, Trivy
├── db/                      # 14 SQLAlchemy models + async PostgreSQL
├── harness/                 # Harnessability scorer (0-8) + routing
├── workspace/               # Git worktree per task
├── dashboard/               # Legacy Jinja2 templates (kept for reference)
├── config.py                # Pydantic Settings
└── main.py                  # Entry point
frontend/                    # React SPA — shadcn/ui Luma + GSAP + Vite
├── src/pages/               # BoardPage, MetricsPage, ApprovalPage, SetupPage
├── src/components/ui/       # shadcn/ui Luma components
├── src/lib/                 # types.ts (Pydantic mirrors) + api.ts (fetch client)
└── src/hooks/               # GSAP animation hooks (Board + Metrics)
```

## Key Files

- `agents/tool_registry.py` — Keystone: schema discovery at phase start
- `agents/definitions.py` — Agent-as-artifact: versioned AgentDefinitions
- `agents/runner.py` — SDK query() dispatch with cost tracking
- `agents/hooks.py` — Workspace boundary + bash argv + security hook wiring
- `security/prompt_inspector.py` — Prompt injection detection (tiered: HIGH blocks, MEDIUM/LOW logs)
- `security/egress_monitor.py` — Extracts network destinations from Bash commands
- `security/permission_store.py` — Per-project tool permission cache with SHA-256 hashing + TTL
- `orchestrator/orchestrator.py` — Deterministic SDLC phase routing
- `orchestrator/gate_feedback.py` — Gate failure → retry → CAPABILITY_LIMIT
- `quality_gates/base.py` — asyncio.gather + per-gate timeouts + AND aggregation
- `db/models.py` — 14 tables (projects→features→tasks→gates→runs→approvals→security_findings)
- `config.py` — All settings: agent budgets, gate timeouts, retry limits

## Key Decisions

- **Claude Agent SDK** is the foundation — replaces 6 custom components
- **Deterministic dispatch** — orchestrator owns routing, not agents
- **Bash must use argv** — no shell=True, enforced by PreToolUse hook
- **Concurrent quality gates** — asyncio.gather with per-gate timeouts
- **MAX_RETRIES=2** — then CAPABILITY_LIMIT → dead-letter queue
- **Session chaining** — resume=session_id passes context between phases

## Environment Constraints

- **Windows + Git Bash** — never create `.sh` scripts. Use Python for complex file ops. `set -euo pipefail` kills grep pipelines on zero matches.
- **npm/npx not in PATH** — use `/c/Program Files/nodejs/npm.cmd` and `/c/Program Files/nodejs/npx.cmd`.
- **Managed env** — hookify/PreToolUse hooks blocked by `allowManagedHooksOnly`. Use `permissions.deny` in settings.json instead.
- **Agent delegation** — agents for read-only exploration only. Writes, skill execution, and interactive prompts must run in main context.

## Project Memory

Per-project structured memory lives in `.memory/` (decisions, corrections, patterns). Pull-based — query when needed, never auto-loaded.

**Boundary with auto-memory (`~/.claude/projects/.../memory/`):**
- **Auto-memory** = about the *person* and *collaboration style* (feedback, preferences, user profile). Travels across projects.
- **Workflow memory** = about *this project's* technical decisions, patterns, and corrections. Meaningless outside this repo.
- If it's a correction to agent behavior → auto-memory feedback. If it's a project-specific technical decision → workflow memory.

**BEFORE triggers:**
- BEFORE starting work on a task → `workflow memory list --phase <current_phase> --status active` (scan titles, skip if nothing relevant)
- BEFORE making a non-obvious decision (tradeoff, exception, override) → `workflow memory search --entity <entity> "<what you're deciding>"` (check for precedent)
- BEFORE changing a config value or gate threshold → `workflow memory search "<config key>"` (check if a prior decision explains the current value)

**AFTER triggers:**
- AFTER making a decision involving exceptions, tradeoffs, or precedent → `workflow memory add --type decision --phase <phase> --entity <entity> --tags "<tags>" "<title>"` with structured Trace section (Inputs, Policy, Exception, Approval)
- AFTER identifying a mistake worth preventing → `workflow memory add --type correction --phase <phase> --entity <entity> --tags "<tags>" "<title>"` with Constraint + What Went Wrong + What To Do Instead
- AFTER validating an approach that should be reused → `workflow memory add --type pattern --phase <phase> --entity <entity> --tags "<tags>" "<title>"`

**What warrants a memory:** Not every decision. Only decisions with exceptions granted, tradeoffs made, prior precedent invoked, or mistakes worth preventing. If the decision is obvious from the code or config, don't memory it.

## Frontend Design Language

BEFORE modifying any frontend page, component, or style → `workflow --docs-dir docs summary design-language`.
Covers: visual identity, status color system, typography rules, component conventions, animation principles, anti-patterns.

## Maintenance

**Placement rule:** project-specific → this file + `docs/`. Cross-project → `~/.claude/CLAUDE.md` + `~/.claude/docs/`.

| What | Where | Retrieve |
|------|-------|----------|
| Project rule (≤3 lines) | This CLAUDE.md | Always loaded |
| Project reference/workflow doc | `docs/` | `workflow --docs-dir docs summary <name>` |
| Cross-project rule | `~/.claude/CLAUDE.md` | Always loaded |
| Cross-project reference doc | `~/.claude/docs/` | `workflow summary <name>` |

- Before editing this file: `workflow summary claude-md-quality-gate`
- Before creating docs: `workflow summary workflow-doc-creation`
- Operating principles: `workflow summary AGENT-PRINCIPLES`
- Surface placement: `workflow summary CLAUDE-CODE-PRINCIPLES`
- Control plane: registered in `~/Agents/Claude Code/manifest.json`
- Run `/audit` to check project compliance
