---
title: "Documentation agent quality gate"
surface: "documentation-agent"
summary: "Use when changing the documentation specialist lane to verify that doc work stays internal, bounded, and routed through canonical repo-local doc and knowledge surfaces."
commands:
  - "workflow --docs-dir docs read references/documentation-agent"
  - "workflow --docs-dir docs read MISSION.md"
  - "builder quality-gate architecture-boundary --json"
  - "builder quality-gate knowledge-base --json"
  - "builder quality-gate documentation-agent --json"
  - "builder knowledge validate --json"
expectations:
  - "the user remains in one main chat surface and does not need to talk to a separate documentation persona"
  - "the documentation agent remains an internal specialist invoked only when documentation or KB intent is present"
  - "main-agent responsibilities stay distinct from documentation-agent responsibilities"
  - "documentation work uses the canonical repo-local doc and builder knowledge surfaces rather than ad hoc parallel lanes"
  - "maintained KB docs are created and refreshed through builder-owned mutation paths, not raw runtime writes"
  - "documentation-routed turns do not surface interactive approve/deny cards for the documentation-agent's canonical builder KB/task tools"
  - "documentation completion requires bounded verification through normal retrieval and validation paths"
  - "canonical maintained-doc freshness stays anchored to `main`, while non-`main` documentation runs remain advisory-only"
  - "documentation work reports explicit remaining gaps instead of drifting into unrelated cleanup"
  - "documentation changes stay aligned with docs/MISSION.md and do not push workflow or tool selection burden back to the user"
  - "permission design stays narrow; avoid broad autonomous access when an allowlisted doc/KB surface is enough"
related_docs:
  - "docs/references/documentation-agent.md"
  - "docs/MISSION.md"
  - "docs/quality-gate/architecture-boundary.md"
  - "docs/quality-gate/knowledge-base.md"
---

# Documentation Agent Quality Gate

## Purpose

Use this gate when changing the documentation-agent contract, its routing
criteria, its write permissions, or its verification behavior.

This gate checks that the documentation specialist remains a bounded internal
lane inside one coherent builder product experience.

## When To Load

Load this gate before:

- adding a documentation specialist or changing how it is invoked
- changing which tools the documentation agent can use
- changing how the agent updates maintained KB docs
- changing how the main chat agent routes documentation intent
- changing the completion criteria for doc freshness or KB update tasks
- changing how maintained docs stamp or compare canonical `main` baselines

## Review Questions

1. Does the user still interact only with the main chat agent?
2. Is the documentation agent justified by a stable documentation task class
   rather than a vague desire for more agents?
3. Does the write path stay on canonical repo-local doc or builder knowledge
   surfaces?
4. Are main-agent and documentation-agent responsibilities explicit rather than
   implied?
5. Does the documentation agent verify retrieval and validation before claiming
   success?
6. Does the permission model auto-allow only the documentation-agent's canonical
   KB/task tools while still keeping unrelated tools on the approval path?
7. Does the change keep documentation work aligned with the repo mission of
   low-burden, system-owned execution?

## Pass Signals

- documentation intent is detected by the main agent and delegated internally
  when appropriate
- the documentation agent is bounded to documentation and KB maintenance tasks
- maintained KB writes still go through builder-owned publish surfaces
- canonical documentation-agent KB/task tools run without interactive approval
  cards during documentation-routed turns
- doc completion includes retrieval and validation evidence
- the user does not need to supply implementation-shaped prompts to get
  documentation work done

## Fail Signals

- the user must choose between multiple agent personas to get documentation work
  done
- documentation logic is encoded only in prompts and not in an explicit owner
  contract
- the documentation agent starts doing unrelated code, architecture, or product
  work by default
- raw file or database mutation bypasses the canonical doc or KB publish surface
- documentation-routed turns still block on approve/deny cards for canonical
  documentation-agent KB/task tools
- success is reported without retrieval proof or without noting the remaining
  validation gap

## Recommended Verification

Read:

- [documentation-agent.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/documentation-agent.md)
- [MISSION.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/MISSION.md)
- [architecture-boundary.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/quality-gate/architecture-boundary.md)
- [knowledge-base.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/quality-gate/knowledge-base.md)

Check behavior when relevant:

- the main chat lane decides whether documentation intent is present
- the documentation lane is given only the tools needed for canonical doc/KB
  work
- canonical documentation-agent KB/task tools do not emit interactive
  `tool_approval_request` cards, while unrelated tools still do
- maintained KB doc mutations still pass through `builder knowledge add` or
  `builder knowledge update`
- canonical `main` refreshes stamp `documented_against_commit`,
  `documented_against_ref=main`, and `owned_paths` on maintained docs
- non-`main` runs report advisory freshness findings without advancing the
  canonical baseline
- the completion path still verifies retrieval through the normal read lane

## Anti-Patterns

- making the documentation agent a second product persona
- using a broad permission bypass just to avoid defining the real doc write lane
- treating file creation alone as proof that documentation is updated
- sending the documentation agent into unrelated stale-surface cleanup before it
  answers the user’s requested documentation question

## Related Docs

- [documentation-agent.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/documentation-agent.md)
- [MISSION.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/MISSION.md)
- [architecture-boundary.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/quality-gate/architecture-boundary.md)
- [knowledge-base.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/quality-gate/knowledge-base.md)
