# Task Workspace Isolation Workflow

## Overview
This workflow defines how `autonomous-agent-builder` should isolate filesystem state for autonomous feature development. The repo should treat `Workspace` as the execution contract and use git worktrees as the default backend for git repositories.

This document is intentionally split into `Current behavior` and `Target contract`. The current codebase has the core surfaces for isolated execution, but the full lifecycle is not wired end to end yet.

## Why This Exists
- Claude Agent SDK execution is scoped to a working directory (`cwd`).
- Session resume depends on reusing the same `cwd`; session IDs alone are not enough.
- Sessions preserve conversation history, not filesystem isolation.
- Parallel autonomous tasks need separate file state to avoid conflicts.
- SDK checkpointing can rewind file edits inside a session, but it does not replace separate workspaces for concurrent tasks.

## Current Behavior

### What exists today
- `WorkspaceManager` can create, reset, and remove git worktrees for a task.
- `Workspace` exists as a persisted one-to-one model on `Task`.
- `AAB_WORKSPACE_ROOT` controls workspace placement.
- Orchestrator phases already expect `task.workspace.path` and pass `workspace_path` into agents and quality gates.

### What is not wired yet
- The orchestrator does not currently provision a workspace before agent execution.
- The repo has no live workflow that guarantees every coding task gets a persisted workspace.
- Cleanup policy is not connected to terminal task states.
- SDK checkpointing is not part of the current implementation path.

## Target Contract

### Core Rule
Every executable coding task must have exactly one persisted `Workspace` before any agent phase runs against repository files.

### Phase Boundary Rule
- Planning and design may inspect the repo without a task worktree when they are operating read-only.
- The task worktree must be created at the `design -> implementation` handoff, or at the first equivalent repo-mutating phase for non-standard flows.
- Worktree creation is orchestrator-owned. The implementation agent must receive an already-provisioned workspace `cwd`; it should not decide where to create or switch branches.
- Verification, PR creation, and build verification must reuse the same persisted workspace unless an explicit recovery flow replaces it.

### Canonical Execution Rules
- The task workspace path is the canonical `cwd` for all agent phases.
- Resume and follow-up runs for the same task must reuse the same `cwd`.
- For git repositories, the default workspace backend is a git worktree.
- For non-git or unsupported cases, use a plain directory workspace only as an explicit fallback.
- Use SDK file checkpointing for intra-session rollback.
- Use isolated workspaces for inter-task filesystem separation.

### Product Framing
Use this wording in repo-local docs and prompts:

`autonomous-agent-builder is workspace-first by contract and worktree-first by default implementation for git repos.`

Avoid this wording:

`Claude Agent SDK requires every feature to use a git worktree.`

The SDK requires stable `cwd` semantics. Worktrees are this repo's preferred implementation for git-backed tasks.

## Workspace Lifecycle

### 1. Provision
- Create a `Workspace` at the `design -> implementation` boundary, before implementation or any equivalent repo-mutating phase begins.
- Default branch naming should be deterministic and task-bound, for example `task/<task_id>` or `task/<task_id>-<slug>`.
- Persist the `Workspace` row immediately after creation.
- The orchestrator or workspace service is responsible for provisioning. Agents only consume the provided workspace path and branch.

### 2. Execute
- Pass `workspace_path` into every agent phase that reads or modifies repo state.
- Run quality gates against the workspace path, not the main repo root.
- If a phase resumes an SDK session, use the same workspace `cwd`.

### 3. Recover
- For bad edits during a live session, prefer SDK file checkpoint rewind.
- For task failure, preserve the workspace by default so operators can inspect the exact file state.
- Only destroy failed workspaces automatically if an explicit policy says to do so.

### 4. Complete
- After terminal success and any post-merge verification, clean up the workspace.
- Mark cleanup in persisted task/workspace state.
- Do not rely on best-effort directory deletion as the only cleanup signal.

## Resume And Session Rules
- Treat SDK resume as conversation recovery, not portable task identity.
- A session resumed from the wrong `cwd` is not reliable.
- Persist task state, workspace path, and important results in application state; do not rely on transcript files alone.
- If a task needs long-lived continuity, the task owns that continuity through `Workspace` plus stored run metadata.

## Rollback And Safety

### Preferred rollback stack
1. SDK file checkpointing for same-session file rewind
2. Git worktree isolation for concurrent task separation
3. Git history for branch-level recovery

### Safety rules
- Never run autonomous coding tasks directly in the main repo working tree when an isolated workspace is expected.
- Do not treat sessions, forks, or subagents as filesystem isolation.
- Subagents help with context isolation, not shared-file safety.

## Failure Modes

### Workspace missing
If a task needs repo access and no workspace can be created, fail closed and mark the task blocked or failed. Do not silently run in the main repo root.

### Resume mismatch
If a resumed SDK run does not use the original workspace `cwd`, treat the session as unreliable and fall back to explicit task state plus a fresh run.

### Worktree unavailable
If the repo is not git-backed or worktree creation fails for an environmental reason, use an explicit fallback path and record that decision in task state or memory if it changes operator expectations.

## Operator Checklist
- [ ] Task has a persisted `Workspace`
- [ ] Workspace path exists before agent execution
- [ ] Agent phase runs with workspace path as `cwd`
- [ ] Quality gates run against workspace path
- [ ] Resume reuses the same workspace path
- [ ] Cleanup policy is applied only after terminal state
- [ ] Failed workspaces are preserved when inspection is needed

## Implementation Gaps In This Repo
- Wire `WorkspaceManager.create_workspace()` into the `design -> implementation` handoff.
- Persist `Workspace` rows when provisioning succeeds.
- Enforce non-empty `workspace_path` for repo-mutating phases.
- Add SDK file checkpointing to implementation-oriented runs.
- Record cleanup status on success and retention status on failure.

## Related Surfaces
- `src/autonomous_agent_builder/workspace/manager.py`
- `src/autonomous_agent_builder/db/models.py`
- `src/autonomous_agent_builder/orchestrator/orchestrator.py`
- `src/autonomous_agent_builder/config.py`
