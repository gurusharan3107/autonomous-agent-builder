---
title: Never mutate the app workspace being worked on by autonomous builder (incl. memory writes)
type: correction
date: 2026-05-08
phase: implementation
entity: workspace-ownership
tags: [workspace-ownership, memory-discipline, fix-discipline]
status: active
---

## Correction

I must never create memory entries, files, or any change inside an app workspace that the autonomous builder is operating on (e.g. `/home/gurusharangupta/Workspace/<generated-app>/`, `/tmp/aab-workspaces/<task>/`, or any directory the builder treats as a generated/target app). All changes to such workspaces are the builder's job, not mine. This includes `builder memory add` runs whose cwd is inside the app workspace — those create entries in the app's `.memory/` and count as a change to the app.

## Agent Retrieval Summary

Retrieve before running ANY command that mutates state in an app workspace the builder is operating on. Includes file edits, `builder memory add/invalidate/graduate`, npm install, git operations, and any other mutating CLI run from inside the workspace cwd. The right cwd for builder-development memory is the autonomous-agent-builder repo itself; the right reaction to a workspace defect is to fix the builder surface that produced it, never the workspace.

## User-Facing Summary

I do not touch generated/target app workspaces. If something is wrong in one, the fix belongs in the autonomous builder so the next run produces a correct workspace.

## Reusable Guidance

- `cd` to `/home/gurusharangupta/code/autonomous-agent-builder/` (or the active worktree of the builder) before running `builder memory ...` for builder-development lessons. Memory about how to develop/test the BUILDER lives in the builder repo's `.memory/`, never in a generated app's `.memory/`.
- Do not run `builder memory add/invalidate/graduate/relate` with cwd inside `/home/gurusharangupta/Workspace/<app>/`, `/tmp/aab-workspaces/<task>/`, or any worktree the builder dispatches code-gen into.
- Do not edit files, install dependencies, run linters or tests against, or otherwise mutate the contents of an app workspace owned by the builder — even if the workspace appears broken. A broken workspace is signal that the builder's quality-gate runner, code-gen prompt, or workspace bootstrap has a defect; fix that surface in the builder.
- Past examples of correct vs. incorrect cwd for memory writes: correct → builder repo memory captures "use Playwright CLI" as a builder-development convention. Incorrect → saving the same correction in `Workspace/todo-app/.memory/` polluted the generated app and had to be cleaned up.

## When To Apply

Apply before EVERY mutating command. Specifically: before `builder memory add`, before any `npm/pip/git` command, before any file edit. If the cwd shows a path under `/home/gurusharangupta/Workspace/`, `/tmp/aab-workspaces/`, or any builder-managed worktree, stop and `cd` to the builder repo first.

## Retrieval Queries

- never modify generated app workspace
- builder memory cwd
- workspace defect fix builder not workspace
- mutating commands cwd discipline
- generated app ownership
