---
title: Create task worktree at design-to-implementation handoff
type: decision
date: 2026-04-24
phase: implementation
entity: workspace-lifecycle
tags: [worktree, workspace, orchestrator, claude-agent-sdk]
status: active
---

For git-backed tasks, create and persist the task workspace at the design-to-implementation handoff, or the first equivalent repo-mutating phase. Planning and design may stay read-only without a task worktree. Workspace provisioning is orchestrator-owned; implementation, verification, PR creation, and build verification reuse the same persisted workspace cwd and branch.
