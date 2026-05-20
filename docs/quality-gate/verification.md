---
title: "Verification lane contract"
surface: "verification"
summary: "Verification combines gate results, metrics, and task state after an agent run."
commands:
  - "builder quality-gate quality-gates"
  - "builder backlog task show <task-id> --full --json"
  - "builder metrics show --json"
  - "builder verify --changed --execute --json"
  - "builder script run build_verify --args '{}' --json"
  - "builder script run change_evidence --args '{}' --json"
expectations:
  - "verification starts with bounded summaries"
  - "metrics remain queryable independently from gate details"
  - "generated Node/React/Vite apps run npm lint/build/test instead of warning unsupported language"
  - "Node package tests run through the package's declared test script; do not append runner-specific flags unless the script contract requires them"
---

# Verification lane contract

## Purpose

Use this gate when changing the verification lane that combines gate state,
metrics, and task inspection after an agent run.

## When To Load

Load this gate before:

- changing verification guidance in `builder context verification`
- changing metrics/task verification sequencing
- changing how verification expands from summary to detail
- changing language detection or quality-gate command selection

## Pass Signals

- verification starts bounded and deepens only when needed
- metrics remain independently queryable from task gate details
- Python, Flask/FastAPI/Django, Node, JavaScript, TypeScript, React, Vite,
  Next.js, and Java workspaces map to concrete gate commands instead of
  `UNSUPPORTED_LANGUAGE`
- Node workspaces with `package.json` prefer `npm run lint`, `npm run build`,
  and `npm test` when scripts exist. Do not inject `-- --run` into generic Node
  test scripts because `node --test` treats that as an invalid file path.
- Repeated build-verifier work should collapse into `builder script run
  build_verify --json`; use `app_url` and `paths` arguments when a bounded
  local app-smoke check is available, then reserve Chrome plugin for visual
  proof.
- Repeated model-backed PR/evidence work should collapse into `builder script
  run change_evidence --json` when changed-file evidence is enough and no real
  remote PR target exists.
- `builder verify --changed --execute --json` scopes proof to product-owned
  changed files. It must ignore generated local Codex environment files under
  `.codex/environments/`; those files are operator-local runtime configuration,
  not builder source, dashboard, memory, knowledge, or generated-app state.
- If ignored local files are the only dirty paths, changed verification returns
  `selected_surfaces: []`, `required_proof: []`, and `next_step:
  no_changed_files` instead of selecting the general proof suite.
- Changed-file proof selection should route runtime adapter and execution
  policy edits to runtime tests, agent definition edits to agent-quality tests,
  orchestrator post-ship optimization edits to product-lifecycle tests, and
  dashboard route/projection edits to dashboard proof. Avoid falling back to a
  broad general suite when a narrower owning surface exists.
- Verification distinguishes real failed checks from advisory metadata gaps.
  For example, `git status` failing in an intentionally non-git disposable
  directory is not equivalent to test, lint, build, or browser proof failure.
- Sprint verification treats `queued` as a valid pre-dispatch task state. A
  queued task must be dispatchable through the orchestrator, and the Board must
  project it in the queued lane for the selected sprint.

## Fail Signals

- verification requires reading large task payloads before basic status is clear
- metrics are coupled too tightly to gate-detail retrieval
- generated web apps show `UNSUPPORTED_LANGUAGE` even though `package.json`
  exposes runnable scripts
- a Node test script fails only because verification appended unsupported
  runner flags
- a task is marked `done` even though the latest verifier output contains a real
  failed build, test, lint, browser proof, or acceptance check
- a queued sprint task is visible but dispatch is a silent no-op
- the Board reports sprint verification against mixed tasks from older sprints
- `builder verify --changed` selects the general surface only because
  `.codex/environments/` is untracked
- a changed runtime, agent-quality, product-lifecycle, or dashboard file skips
  its narrower owner proof and relies only on aggregate smoke tests
