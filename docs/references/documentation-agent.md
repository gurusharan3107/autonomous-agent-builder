# Documentation Agent

Canonical reference for the repo-local documentation specialist used by the
main chat agent.

Use this doc as the owner surface when changing:
- when the main agent should delegate documentation work
- what the documentation agent is allowed to read or mutate
- how documentation updates should be verified before reporting success
- how documentation work maps to the repo mission and KB ownership model

Use the quality gate in
[documentation-agent.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/quality-gate/documentation-agent.md)
to verify changes against this contract.

For the mission-aligned placement of documentation refresh inside builder-owned
delivery flow, see
[autonomous-delivery-documentation-refresh.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/autonomous-delivery-documentation-refresh.md).

## Purpose

The documentation agent is an internal specialist, not a second user-facing
persona.

The user stays in the main chat pane. The main agent owns:
- user interaction
- intent interpretation
- task context
- approval flow
- final reporting

The documentation agent exists to keep repo-local documentation and knowledge
surfaces current without forcing the user to write implementation-shaped
prompts.

The target output is dual-audience by contract:
- the authored document should remain readable on the page for human operators
- the `builder` retrieval surface should adapt that document into bounded,
  agent-friendly output for runtime consumption

## User Experience Contract

The user should be able to say things like:
- `is documentation updated?`
- `update the docs for this feature`
- `is the knowledge base current?`
- `create the missing feature and testing docs`

The system should translate that intent into bounded documentation work.

The user should not need to specify:
- which doc types to create
- which tool lane to use
- which KB validation command to run
- whether the work belongs in a maintained doc, testing doc, or quality-gate
  surface

Those are system responsibilities.

That applies to automation too. CI or post-merge workflows should not bypass
this owner surface with an ad hoc Claude prompt. They should call a repo-owned
documentation-agent bridge that delegates into this specialist with the bounded
builder-owned tool and approval surface already defined here.

## Ownership Contract

### Main agent owns

- deciding whether the user intent matches documentation or KB maintenance
- deciding whether a documentation specialist is justified
- collecting any user clarification that cannot be inferred safely
- providing task/feature context to the documentation agent
- merging documentation results back into the main conversation
- exposing any repo-owned automation bridge that invokes the documentation
  agent for CI or post-merge freshness work

### Documentation agent owns

- checking whether repo-local maintained docs or KB entries are missing or stale
- updating the canonical repo-local documentation and KB surfaces for the
  current task or feature
- creating missing maintained feature and testing docs when the current task
  requires them
- verifying that written docs are retrievable and still pass the relevant local
  contracts
- reporting bounded gaps instead of drifting into unrelated fixes

Canonical maintained-doc freshness is anchored to `main`.
Use [main-commit-reference.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/main-commit-reference.md)
as the owner surface for the baseline contract.

For maintained `feature` and `testing` docs, the documentation agent should
follow the `main` baseline contract in
[main-commit-reference.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/main-commit-reference.md):
- resolve the current `main` HEAD before deciding what needs refresh
- compare each maintained doc's `documented_against_commit` to `main`
- use `owned_paths` plus feature/task linkage to keep candidate selection
  diff-bounded instead of rereading the whole maintained corpus
- treat non-`main` branch runs as advisory-only: inspect and report likely stale
  docs, but do not advance canonical `documented_against_commit` baselines
- stamp `documented_against_commit`, `documented_against_ref=main`, and
  `owned_paths` whenever a canonical `main` refresh creates or updates a
  maintained doc

It should not solve agent-friendliness by making the authored document itself
read like a machine payload. Human readability belongs in the document;
context-efficiency belongs in the `builder` CLI retrieval contract.

### It does not own

- direct conversation with the user
- broad product planning
- code changes unrelated to documentation truth
- global `~/.codex` mutations
- raw file or database writes that bypass the canonical builder-owned doc/KB
  surfaces

## Invocation Model

The main agent should invoke the documentation agent only when the user intent
or active task implies documentation work.

Typical triggers:
- documentation freshness checks
- KB update requests
- maintained feature-doc creation
- maintained testing-doc creation
- doc verification after a feature change
- bounded doc gap analysis for a specific task, feature, or workflow

Do not invoke it for:
- generic code search
- architecture review without a documentation deliverable
- broad repo exploration when no doc action is needed
- unrelated bug fixing discovered during a doc scan

## Tool And Permission Contract

The documentation agent should be constrained to the minimum tools needed for
repo-local documentation work.

Prefer:
- canonical builder doc and KB read/write surfaces
- bounded retrieval commands for repo docs and local knowledge
- validation commands that prove the updated docs are usable

Avoid:
- broad `bypassPermissions`
- ad hoc shell-based mutation when a builder-owned publish surface exists
- direct file edits for maintained KB docs when `builder knowledge add` or
  `builder knowledge update` is the canonical path

The permission model should make the intended write lane explicit rather than
depending on prompt wording alone.

For documentation-routed chat turns, the documentation agent's canonical
builder task/KB tools should run without interactive approve/deny cards. The
bounded allowlist is the documentation-agent tool set itself, not a broad
permission bypass for unrelated tools such as `Bash`.

For automation bridges, the same rule applies:
- the parent bridge may expose only the `Agent` tool
- the pre-approved tool envelope should cover only the documentation-agent's
  canonical builder KB/task tools
- the bridge should not grant broad `Bash`, `Write`, or unrelated repo mutation
  access just because the run is in CI

## Canonical Write Paths

The documentation agent must use the canonical owner surface for the target
artifact.

### Repo docs under `docs/`

Use the repo-owned doc surfaces and keep the doc in the correct owner path:
- `docs/references/` for stable contracts
- `docs/workflows/` for ordered procedures
- `docs/quality-gate/` for review contracts

### Repo-local knowledge under `.agent-builder/knowledge/`

Use:
- `builder knowledge add`
- `builder knowledge update`
- `builder knowledge validate`
- `builder knowledge summary`
- `builder knowledge show`

Do not treat raw file mutation as the default lane for maintained knowledge
docs.

## CLI Consumption Contract

When the documentation agent consumes `builder` output, it should prefer the
compact machine contract over human-oriented prose.

Prefer these fields first when present:
- `ok`
- `exit_code`
- `status`
- `code`
- `matched_on`
- `degraded`
- `source`
- `next`

Interpretation rule:
- use direct command fields such as `next` before parsing sentence-style
  `hint` or `next_step`
- use symbolic fields such as `code=connectivity_error` or
  `matched_on=search` before reading longer explanation text
- treat prose as secondary context, not the primary control surface

Examples:
- if a KB read returns `next: "builder knowledge search \"<query>\" --json"`,
  use that directly instead of parsing a longer recovery sentence
- if a validation or retrieval call returns `exit_code: 3` with
  `code: connectivity_error`, treat that as a retry/startup problem rather
  than a content failure
- if a read result returns `matched_on: search`, accept that as proof that the
  normal retrieval path resolved the target artifact

The documentation agent should stay context-efficient:
- prefer compact JSON fields over repeated explanatory text in summaries
- only quote or restate prose when the symbolic fields are insufficient to
  explain the remaining gap

## Verification Contract

Documentation work is not complete when the write succeeds.

The documentation agent must verify, in a bounded way, that:
1. the expected doc or KB artifact exists in the canonical surface
2. the updated artifact is retrievable through the normal read path
3. canonical maintained docs now reflect the latest `main` commit when the run
   is allowed to advance baselines
4. the relevant local validation contract still passes, or the remaining gap is
   stated explicitly

Good completion states:
- `already current`
- `updated and verified`
- `partially updated; remaining gap: <specific gap>`

Bad completion states:
- `updated` without retrieval proof
- success claims based only on file presence
- drifting into unrelated cleanup before reporting the requested status

## Failure And Escalation Rules

The documentation agent should stop and return control to the main agent when:
- the intended owner surface is ambiguous
- the required write lane is unavailable
- the task actually requires architecture or product decisions, not documentation
  maintenance
- the requested change would require mutating surfaces outside its allowed
  boundary

In those cases, the main agent should either:
- ask the user one focused clarification
- route to a different specialist
- or report the exact blocking boundary

## Related Docs

- [MISSION.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/MISSION.md)
- [claude-agent-sdk-integration.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/claude-agent-sdk-integration.md)
- [knowledge-base.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/quality-gate/knowledge-base.md)
- [architecture-boundary.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/quality-gate/architecture-boundary.md)
- [main-commit-reference.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/main-commit-reference.md)
