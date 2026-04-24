# System Improvement Loop

## Overview
This workflow is the default loop for improving `autonomous-agent-builder` as a real product, not just as a codebase. It treats the system as an operator-facing autonomous delivery tool and validates changes through realistic user flows, backend state, and Claude Agent SDK behavior.

Use this workflow when the goal is to improve reliability, onboarding, phase behavior, dashboard truthfulness, agent behavior, or any feature that spans frontend, backend, orchestration, or SDK integration.

## Core Principle
Test the system like a real user first. Then trace the failure to the true backend or product-state cause. Fix the smallest correct owner surface. Retest the same user flow. Verify the result is still aligned with Claude Agent SDK constraints and best practices.

## When To Use
- onboarding or first-run experience improvements
- dashboard or board behavior fixes
- task lifecycle or phase-transition bugs
- workspace, resume, or session behavior fixes
- knowledge base or memory lifecycle issues
- approval, gate, or build-verify regressions
- any issue where UI symptoms may hide backend or orchestration causes

## Workflow

### 1. Start From The User Flow
Reproduce the issue through the real product surface whenever possible.

Examples:
- start a fresh repo and run onboarding
- open the dashboard and click the actual controls
- create or inspect backlog items through the product
- trigger a task phase and observe state changes

Use:
- browser testing for operator-facing flows
- local external fixture repos when validating onboarding or repo-state behavior
- product state inspection instead of guessing from code alone
- `builder logs` and other builder CLI telemetry as the canonical compact runtime-evidence lane

## 2. Capture Observable Evidence
Before changing code, capture what the system actually did.

Check:
- UI state and visible operator messages
- persisted product state
- DB rows and phase transitions
- onboarding or task state files
- KB or memory outputs
- `builder logs --error`
- `builder logs --info --compact --json`
- builder CLI telemetry such as board, backlog, approval, and run state
- network requests and console errors if a browser surface is involved

Goal:
- identify the exact failing phase, state transition, or owner surface
- distinguish stale UI from true backend failure
- avoid fixing only the symptom

Default evidence order:
1. browser-visible behavior
2. builder CLI telemetry and `builder logs`
3. lower-level DB or server inspection only if the builder-owned evidence is insufficient

## 3. Classify The Failure
Put the issue in one primary lane before editing:

- `frontend projection`: UI is wrong, stale, misleading, or missing state
- `backend state`: DB or persisted state is wrong
- `orchestrator contract`: phase routing, handoff, or blocking behavior is wrong
- `workspace/session`: `cwd`, resume, isolation, or worktree behavior is wrong
- `KB/memory`: knowledge or memory lifecycle is wrong
- `sdk contract`: Claude Agent SDK assumptions are wrong or incomplete

Pick one primary owner even if multiple surfaces are involved.

## 4. Verify Claude Agent SDK Compliance Before The Fix
For any agent-facing or phase-facing change, validate these invariants:

- stable `cwd` for task execution
- resume uses the same workspace path
- sessions are not treated as filesystem isolation
- tool boundaries remain explicit
- hooks still enforce safety and workspace constraints
- prompt or phase changes do not assume behavior the SDK does not guarantee

If the proposed fix weakens any of these, stop and redesign.

## 5. Fix The Smallest Correct Surface
Default owner choices:

- product behavior or phase logic -> backend/orchestrator
- stale or misleading operator surface -> frontend/dashboard
- repeated multi-step operator procedure -> workflow doc
- reusable non-obvious precedent -> builder memory
- project understanding artifact -> builder KB

Do not patch the UI if the backend state is wrong.
Do not add prose if the problem should be enforced in code or gates.

## 6. Retest The Same User Flow
After the fix, rerun the original user flow end to end.

Always verify:
- the original failure no longer occurs
- no new contradictory UI state appears
- persisted state matches the UI
- the intended phase reaches the correct terminal or next state

If the flow was originally tested in an external repo, retest in an external repo again.

When optimizing runtime behavior, keep using browser-based validation plus builder CLI telemetry as the default feedback loop. Do not optimize only from static code inspection if the product surface or logs can prove the behavior more directly.

## 7. Add Or Update Tests
Convert the reproduced issue into a durable regression test.

Prefer:
- deterministic unit or contract tests for classifiers and state transitions
- onboarding fixture-repo tests for repo-shape-dependent behavior
- browser or operator-surface tests for UI truthfulness
- negative tests for blocked or degraded Claude/SDK conditions

Good regression tests answer:
- what was broken
- what now passes
- what must never regress again

## 8. Recheck SDK Best Practices After The Fix
Before closing the loop, confirm the change still follows Claude Agent SDK best practices:

- concise, high-signal `CLAUDE.md` guidance
- retrieval before broad reasoning
- bounded tool usage
- no hidden assumption that `CLAUDE.md` loads from the wrong `cwd`
- no false assumption that worktrees or sessions do more than they actually do
- clear distinction between conversation continuity and filesystem state

## 9. Record The Learning In The Right Surface
Use the narrowest durable surface:

- workflow doc if the improvement changes a repeated operator/developer procedure
- builder memory if the key learning is a repo-specific decision, correction, or reusable pattern
- `CLAUDE.md` if the builder runtime contract changed
- no doc change if the fix is fully obvious from code and tests

## Default Checklist
- [ ] Reproduced through the real product surface
- [ ] Captured UI, backend, and persisted-state evidence
- [ ] Identified the true owner surface
- [ ] Checked Claude Agent SDK invariants before editing
- [ ] Applied the smallest correct fix
- [ ] Retested the exact original flow
- [ ] Added or updated regression coverage
- [ ] Rechecked SDK best-practice alignment
- [ ] Recorded the learning in the correct durable surface

## Common Anti-Patterns
- fixing the frontend when the backend state is wrong
- patching backend output when the real issue is wrong workspace or resume behavior
- treating a clean-slate repo like a system-doc extraction target instead of a forward-engineering project
- assuming SDK sessions preserve filesystem state
- assuming `CLAUDE.md` loads without the correct `cwd`
- stopping after code change without rerunning the same user flow
- writing broad docs when a deterministic test or gate should own the behavior

## Related Workflows
- [task-workspace-isolation.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/workflows/task-workspace-isolation.md)
- [chrome-devtools-dashboard-testing.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/workflows/chrome-devtools-dashboard-testing.md)
