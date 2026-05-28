---
name: create-skill
description: >
  Use when the user asks to create a new agent skill, scaffold a skill directory,
  add a reusable workflow as a skill, build a slash command, improve an existing
  skill, or "turn this into a skill". Three lanes — Create (scaffold a new skill
  following the webwright pattern: preflight → explore → author → validate →
  closeout with introspection loop), Refine (improve an existing skill's structure,
  description, or content), Audit (check a skill against agentskills.io spec and
  project standards). Output skills are ready to activate, self-verify, and
  self-improve — not blank stubs. Also triggers on: "make a skill for X", "create
  a slash command for Y", "refine the Z skill", "why isn't my skill activating",
  "add a skill that does X".
allowed-tools: Read, Write, Edit, Bash, AskUserQuestion
---

# create-skill — author, refine, audit

Router skill. Body holds only what's needed on every activation: lane selection,
universal invariants, and pointers. Lane procedure and output templates load on
demand from `reference/`.

## Entry — pick a lane

First action is `AskUserQuestion` unless the typed prompt names a lane:

| Lane | When | Procedure |
|---|---|---|
| **Create** | New skill from scratch | [reference/create.md](reference/create.md) |
| **Refine** | Modify existing skill | [reference/refine.md](reference/refine.md) |
| **Audit** | Check conformance | [reference/audit.md](reference/audit.md) |

Skip the question when the prompt is unambiguous:

| Pattern | Lane |
|---|---|
| "create / scaffold / make / add a skill for X" | Create |
| "refine / improve / fix / shrink / update skill X" | Refine |
| "audit / check / validate skill(s)" | Audit |
| anything ambiguous | **Ask** |

## Spec at a glance

| Field | Required | Constraint |
|---|---|---|
| `name` | yes | kebab-case, equals directory name |
| `description` | yes | ≤1024 chars; imperative; trigger-centric |
| `allowed-tools` | no | minimize; omit if pure prose |

## Workflow

create-skill's own execution is: pick a lane → load its reference file → follow it.

1. Ask which lane (or infer from prompt — see Entry table above).
2. Load the lane's reference file.
3. Follow the procedure in that file end-to-end.

The **5-step pattern** (PREFLIGHT → EXPLORE → AUTHOR → VALIDATE → CLOSEOUT) is what
create-skill **encodes into the skills it creates** — via `reference/create.md` (the
Create lane procedure) and `reference/templates.md` (the output skill scaffold).
create-skill itself does not follow that pattern; it is a simple router.

## Hard rules (universal — every lane)

1. **Output skills are always project-local.** Create skills in `.claude/skills/<name>/`,
   never in `~/.claude/skills/`. Preflight reads project context; closeout encodes
   project-specific friction back into the skill. The resulting gotchas and guards
   are shaped by this project's failure modes — they are not portable global knowledge.
2. **Never generate from training data alone.** If no source material exists
   (tasks, conversations, code, runbooks, similar skills in this repo), stop and
   ask before writing a single line of skill content.
3. **scope.md is the oracle.** Write it before any skill file. Every section of
   the output skill maps to a CP in scope.md. Never skip it.
4. **Body is a router, not a content dump.** Bulk procedure → `reference/`.
   SKILL.md ≤500 lines, ≤5000 tokens.
5. **Description activates on operator vocabulary.** Write trigger phrases the
   user would actually type, not internal jargon.
6. **Closeout is mandatory — and must include staleness mechanics.** Every output
   skill's CLOSEOUT must contain: (a) staleness scan — verify every cross-referenced
   file still exists; (b) symbol freshness — grep for every asserted symbol; (c)
   pattern review — prune dead patterns, annotate regression guards, encode new failure
   modes found in the current run. A friction-only CLOSEOUT will drift into a stale
   historical document within weeks. introspection.md → patch → delete is the done signal.
7. **Deterministic scripts only in `scripts/`.** Judgment belongs in body or
   reference, not scripts.

## Cross-references

- [reference/create.md](reference/create.md) — Create lane (preflight → explore → author → validate → closeout)
- [reference/refine.md](reference/refine.md) — Refine lane (audit → scope changes → apply → re-validate)
- [reference/audit.md](reference/audit.md) — Audit lane (conformance checks, output format)
- [reference/templates.md](reference/templates.md) — Output skill scaffold (SKILL.md, evals, commands)
- [reference/description-testing.md](reference/description-testing.md) — Trigger eval loop (train/validation split, iteration)
- [reference/quality-gate.md](reference/quality-gate.md) — Done checklist (all CPs must pass before declaring done)
- External: [agentskills.io/skill-creation/best-practices](https://agentskills.io/skill-creation/best-practices)
