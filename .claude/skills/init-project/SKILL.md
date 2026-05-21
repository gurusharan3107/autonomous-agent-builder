---
name: init-project
description: "Scaffold a new project and create its feature backlog. Detects project type, creates CLAUDE.md + dev infrastructure + utility scripts, interviews the user to understand intent, then produces feature-list.json. Use for /init-project, 'scaffold project', 'setup new project', 'initialize', 'new repo', 'start from scratch', 'break down requirements'. Also use when no CLAUDE.md or feature-list.json exists. NOT for improving existing configs — use /audit."
model: sonnet
effort: medium
allowed-tools: Read, Write, Bash, Glob, Grep
---

# Init Project

Detect, scaffold, interview, plan. Single pass from empty directory to ready-to-implement.

**EXECUTE this skill now.** Do NOT describe or explain — run it.

## Gotchas

| Gotcha | What happens | Do instead |
|--------|-------------|------------|
| Guessing features without interviewing | Agent creates a feature list based on assumptions, user rejects half of it | Always run Step 3 (Interview) — the user knows what they want, you don't |
| Overwriting existing CLAUDE.md | Project had customizations (BEFORE triggers, Key Decisions) that get lost | Check what exists first. Skip existing files in Step 2, only add missing sections |
| Too many P0 features | Everything feels critical, ending up with 15+ P0s defeats prioritization | Cap P0 at 3-5. Everything else is P1/P2. Ship P0 first, then reassess |
| Wrong project type detection | Monorepo with both package.json and pyproject.toml — picks the wrong one | Check detection output against actual entry points. Override if wrong |
| Scripts generated with wrong commands | Dev server command points to wrong module, lint command doesn't match config | Verify generated scripts by running them once. Fix before moving on |

## Workflow

### Step 1: Analyze Project

Scan the directory for config files to determine language, framework, and existing tooling:

| File | Indicates |
|------|-----------|
| `package.json` | Node/React/Next.js — check `dependencies` for framework |
| `pyproject.toml` / `requirements.txt` | Python — check for FastAPI/Django/Flask |
| `Cargo.toml` | Rust |
| `go.mod` | Go |

Also check: existing CLAUDE.md, .claude/, docs/, test config, formatter config, README.md, directory structure, entry points.

For existing projects, audit modules for completeness (done/partial/stub/missing) so Step 4 can mark done features accurately.

### Step 2: Scaffold

Create the following. Skip what already exists — don't overwrite customizations.

**CLAUDE.md** — Load the canonical template via `workflow summary claude-md-template`. It defines 4 required sections:

| Section | What |
|---------|------|
| Commands | Table of real install/dev/test/lint/format/build commands |
| Architecture | Directory tree with purpose annotations |
| Key Files | Important files with one-line descriptions |
| Maintenance | Placement rule, quality gate, workflow doc creation, principles, audit |

For new projects, seed all 4 sections. For existing projects, check which exist and add what's missing.

**Dev infrastructure** — only create what's missing:

| Deliverable | JS/TS | Python |
|-------------|-------|--------|
| Formatter | `.prettierrc` + ESLint | `[tool.ruff]` in pyproject.toml |
| Tests | Jest/Vitest config + one real test | pytest config + one real test |
| .gitignore | node_modules/, dist/, .env | __pycache__/, .env, venv/ |

**Project structure:**
- `docs/` — `references/`, `design-docs/`, `exec-plans/active/`, `exec-plans/completed/`
- `.claude/progress/` — will hold feature-list.json
- `.claude/scripts/` — project utility scripts (see below)

**Scripts** — generate in `.claude/scripts/` using the detected project type:

| Script | Purpose | How |
|--------|---------|-----|
| `feature.py` | Feature CRUD (next/get/done/add/list/summary) | Copy as-is from `~/.claude/skills/init-project/scripts/feature.py` |
| `verify.sh` | Run lint → test → build, stop at first failure | Generate with correct commands for detected type |
| `dev-server.sh` | Install deps + start dev server | Generate with correct commands for detected type |

Generate verify.sh and dev-server.sh using these commands:

| Project | verify.sh: lint | verify.sh: test | verify.sh: build | dev-server.sh |
|---------|----------------|-----------------|-------------------|---------------|
| Python | `ruff check .` | `pytest` | `# python -m build` | `pip install -e ".[dev]" && python -m <module>` |
| Node/TS | `eslint .` | `npm test` | `npm run build` | `npm install && npm run dev` |
| Rust | `cargo clippy` | `cargo test` | `cargo build` | `cargo run` |
| Go | `go vet ./...` | `go test ./...` | `go build` | `go run .` |

Use `~/.claude/skills/init-project/scripts/verify.sh` and `dev-server.sh` as structural references (set -e, echo headers, comment style) but replace commands with the project-specific ones. After generating, run each script once to verify it works.

If a step fails (permissions, missing tools), note it and continue.

### Step 3: Interview

The user knows what they want to build — you don't. Ask to understand their intent before creating the feature list.

| Domain | What to learn |
|--------|---------------|
| Scope | MVP vs full vision, deployment target |
| Technical | Auth, real-time, state management, data model |
| Quality | Test coverage targets, CI/CD, monitoring |
| Tradeoffs | Performance vs features, build vs buy, polish vs speed |
| Risks | Known blockers, concerns, hard deadlines |

- Ask non-obvious questions — don't ask what you can derive from code
- First option for each question should be your recommended answer based on codebase analysis, marked "(Recommended)"
- Go deep on answers that reveal priorities or constraints
- Continue rounds until intent is clear
- For existing projects, present the codebase inventory first so the user can confirm what's done vs what needs work

### Step 4: Create feature-list.json

Synthesize the codebase analysis (Step 1) + interview (Step 3) into atomic features.

Each feature should be:
- **Single responsibility** — one thing, testable with clear pass/fail
- **Independent** — minimal coupling to other features
- **Small** — completable in a focused session

Write to `.claude/progress/feature-list.json`:

```json
{
  "features": [
    {
      "id": "FT-001",
      "title": "Short title",
      "description": "What to build and why",
      "priority": "P0",
      "status": "pending",
      "acceptance_criteria": ["Criterion 1", "Criterion 2"],
      "dependencies": []
    }
  ]
}
```

- **P0**: 3-5 features max — the critical path to a working system
- **P1**: Should-have, not blocking MVP
- **P2**: Nice-to-have, after P0 and P1 are done
- Mark existing complete features as `"status": "done"`

### Step 5: Report

```
Initialized: {project_name}
Type: {language/framework}
Features: {done} done, {pending} pending ({P0 count} P0)

Next: run /implementation to start building
```

## Constants

- `MANIFEST_PATH`: `C:/Users/gurusharan.gupta/Agents/Claude Code/manifest.json`
