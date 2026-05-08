Always read `~/.codex/AGENTS.md` first (global Codex rules for working on
any repo), then repo-local `AGENTS.md` (this file). Repo-local `CLAUDE.md`
is the autonomous-builder runtime contract for the Claude Agent SDK lane;
it is not the agent-facing instruction surface for Codex working on this
repo.

## Triggers

| When | Command | Purpose |
|------|---------|---------|
| Starting task | `builder memory search "<query>"` | Check repo precedent |
| After a user correction, preference, or workflow critique that should affect future runs | `builder memory search "<query>"`; `builder memory contract`; then `builder memory add --type correction|pattern ... --json`;`builder memory reindex --json`;`builder memory lint --json` | Proactively decide whether the lesson belongs in repo memory; save only reusable project-specific guidance, then prove it is indexed and lint-clean. |
| Unfamiliar workflow | `workflow --docs-dir docs summary <name>` | Load repo workflow doc |
| System-wide product improvement or real-user debugging | `workflow --docs-dir docs summary system-improvement-loop` | Reproduce, trace true owner, fix, retest |
| Reverse-engineering validation on an existing repo | `workflow --docs-dir docs summary reverse-engineering-autonomous-lifecycle-validation` | Use a disposable external repo clone as the subject; do not use `autonomous-agent-builder` itself as the reverse-engineering test target. |
| Forward/reverse lifecycle validation | `workflow --docs-dir docs summary dashboard-first-validation` | Act as a normal dashboard user. Use `builder` CLI for bootstrap, readiness, logs, observability, and read-only evidence; do not use CLI mutation to advance backlog, tasks, approvals, or dispatch. |
| Testing or workflow-validation closeout after the product run | `builder backlog item create --type incident|improvement|optimization --source validation ...`;`builder memory contract --json`;`builder memory add --type pattern --phase testing ... --json` | Track observed failures, hardening work, and efficiency improvements as maintainer closeout; memory writes must return passing `post_mutation` evidence and must not count as lifecycle-validation evidence. |
| Changing memory lifecycle behavior | `builder verify --surface memory --execute --json` | Prove memory add, relate, invalidate, template lint, reindex, and retrieval evidence before calling the change ready. |
| Runtime failure, opaque deny, or Agent-page log diagnosis | `builder logs --error`; `builder logs --info --compact --json`; `builder logs analyze --session <id-or-prefix> --json` | Check builder-owned runtime evidence first. Use `builder logs` as the canonical agent-facing debug lane; use `analyze` when prompt-by-prompt session review matters, and use the Agent page as the user-friendly view of the same run. |
| Day-0 readiness or init/onboarding routing | `builder readiness status --json`; `builder readiness assess --json`; `workflow --docs-dir docs summary day-0-readiness` | Check the canonical readiness contract before requirements, repo understanding, planning, or delivery. |
| Optimizing Autonomous Builder with Codex | `builder quality-gate claude-agent-sdk --json`; `workflow --docs-dir docs summary agent-quality-tuning-loop`; official OpenAI/Codex docs when changing Codex-facing behavior | Use Codex strengths for repo analysis, tests, docs, and quality gates to improve the Claude Agent SDK product. Keep Codex-only guidance in `AGENTS.md`, not runtime `CLAUDE.md`. |
| Changing Claude Agent SDK phase policy, specialists, hooks, permissions, or run evidence | `builder quality-gate claude-agent-sdk --json`; `builder quality-gate product-lifecycle --json`; `builder quality-gate state-integrity --json`; `builder quality-gate architecture-invariants --json` | Keep Claude SDK strengths as runtime execution mechanics while builder remains the source of truth for lifecycle, state, gates, and recommendations. |
| Changing Claude Agent SDK telemetry or observability policy | `workflow --docs-dir docs summary claude-agent-sdk-telemetry-observability`; `builder quality-gate claude-agent-sdk --json` | Load the canonical telemetry split and validate that observability changes improve builder tuning without turning OTEL into a transcript store |
| Changing runtime-switch behavior, dashboard tabs, Settings runtime controls, or runtime attribution | `workflow --docs-dir docs summary runtime-switch-dashboard-contract` | Keep SDK switching deterministic: future runs use the selected runtime, historical state keeps original runtime attribution, and backend logs record the switch in the active DB. |
| Needing Claude-Agent-SDK-specific best-practice clarification from official docs | `workflow --docs-dir docs summary agent-quality-tuning-loop` | Use the Claude docs assistant only as a bounded, docs-cited SDK advisory lane; escalate repo-behavior questions to code, logs, and tests |
| Checking whether repo-local KB is current and agent-friendly | `builder knowledge validate --json`; `builder knowledge summary "<query>"`; `builder knowledge show <doc> --section "Change guidance"` | Use `validate` for trust/freshness and `summary`/`show` for bounded retrieval quality; do not rely on only one of the two |
| Choosing retrieval lane | `builder knowledge ...`; `workflow --docs-dir docs summary <name>` | Use `builder knowledge` for repo-local feature context, system architecture, implementation state, and testing surfaces. Use `workflow --docs-dir docs` for contracts, workflows, quality gates, and other owner docs under `docs/`. |
| Changing phase boundaries, operator questioning, or per-phase tool permissions | `workflow --docs-dir docs summary phase-model` | Load the canonical phase contract before changing requirements/planning/design/implementation/verification/integration behavior. |
| Dashboard/UI assessment without requested edits | Verify the live dashboard first | Separate evaluation from implementation before proposing changes |
| Dashboard/frontend work | `workflow --docs-dir docs summary design-language`; `builder quality-gate dashboard-ux --json` | Load visual rules and prove the user-visible state/action/evidence contract |
| Task isolation or resume questions | `workflow --docs-dir docs summary task-workspace-isolation` | Load workspace contract |
| Repo-local product knowledge or state | `builder knowledge summary <query>` | Use `builder` for repo-local knowledge, memory, and delivery state |
| Cross-project precedent or external repo behavior | `workflow knowledge search "<query>"` | Use `workflow` for broader research/global doctrine; use DeepWiki MCP when GitHub repo context is needed |
| Architecture or boundary review, including Codex subagent design | `workflow --docs-dir docs summary architecture-boundary-review` | Load the bounded architecture-review lane and use `architecture_reviewer` only for explicit subagent asks or second-pass architecture audits |
| Tuning agent quality, telemetry use, or context efficiency | `builder quality-gate claude-agent-sdk --json`; `workflow --docs-dir docs summary agent-quality-tuning-loop` | Evaluate builder agent behavior through mission-aligned evidence before changing prompts, tools, models, or subagents |
| Agent-facing CLI work | `workflow quality-gate cli-for-agents`; `builder map` | Validate CLI and repo surface |
| Creating or changing quality-gate docs | `builder quality-gate <surface> --json`; then update the canonical file under `docs/quality-gate/` | Reuse the existing gate and avoid duplicate surfaces |
| Adding or renaming a builder CLI command | `builder --help`; `builder <group> --help`; `builder quality-gate builder-cli --json` | Check whether an existing command or group already owns the surface before adding a new one |
| Editing `CLAUDE.md` | `builder quality-gate claude-md --json`; `workflow --docs-dir=docs summary quality-gate/claude-md` | Check the dedicated repo-local runtime-contract gate before editing |
| Editing other runtime-boundary docs | `workflow --docs-dir=docs summary quality-gate/architecture-boundary` | Check the broader product-vs-runtime ownership contract before editing |
| Creating docs | `workflow summary workflow-doc-creation` | Use doc creation playbook |
| AFTER dashboard changes | `builder start --port 9876` | Rebuild/publish the dashboard and launch the local product |
| AFTER non-obvious decisions | `builder memory add --type decision ...` | Capture decision trace |
| AFTER repeated friction | Create `.kiro/steering/<topic>.md` | Encode recurrence guard |

## Quick Commands

| Command | Purpose |
|---------|---------|
| `builder start --port 9876` | Start server |
| `builder logs --error` | Failure-first embedded run diagnosis |
| `builder logs --info --compact --json` | Compact agent-friendly run summary |
| `builder logs analyze --session <id-or-prefix> --json` | Prompt-level session review with observability coverage |
| `builder readiness status --json` | Read the persisted Day-0 readiness contract |
| `builder readiness assess --json` | Recompute `.agent-builder/readiness.json` from local repo state |
| `lsof -nP -iTCP:9876 -sTCP:LISTEN` | Check server |
| `pytest --collect-only` | Collect tests |
| `builder map` | Bounded workspace digest |
| `builder context <task>` | Task bootstrap |
| `builder backlog item create --project <id> --type incident|improvement|optimization --source validation --evidence <text> --json` | Track validation closeout findings |
| `builder memory contract --json`; `builder memory add --type pattern --phase testing --entity <workflow-or-surface> --tags <tags> --title <title> --content-file <template.md> --json` | Save reusable validation anecdotes with passing post-mutation evidence |
| `builder quality-gate <surface>` | Retrieve quality-gate expectations |
| `builder knowledge validate --json` | Deterministic KB trust/freshness check |
| `builder knowledge summary <query>` | Bounded local KB summary |
| `builder knowledge show <doc> --section <heading>` | Expand local KB selectively |
| `builder memory list` | List memories |
| `builder memory stats` | Memory lifecycle digest |
| `workflow knowledge search "<query>"` | Search global knowledge base |
| `workflow summary <name>` | Load global workflow/ref doc |

## Ownership

- `CLAUDE.md` owns builder runtime truth, phase/state contracts, and repo-specific invariants.
- `CLAUDE.md` is the Claude Agent SDK runtime/project-instruction surface.
- `AGENTS.md` owns Codex triggers, retrieval shortcuts, validation entrypoints, and
  how Codex SDK should optimize this Claude Agent SDK builder. Codex CLI is not
  a user-facing sprint validation lane.
- `docs/references/phase-model.md` and `docs/references/phases/*.md` own the canonical phase-boundary contract.
- `docs/workflows/` owns multi-step procedures.
- Repo-specific docs stay in repo `docs/`; do not move product-runtime responsibilities into `~/.codex` surfaces.
- `builder memory` owns repo-specific decisions, patterns, and corrections.
- `builder knowledge` owns repo-local system docs, including seed extraction, maintained feature docs, and testing docs.
- `.agent-builder/readiness.json` owns the Day-0 readiness contract; `onboarding-state.json.ready` is compatibility output.
- `workflow --docs-dir docs` owns repo-local contracts, workflows, quality gates, and other canonical docs under `docs/`.

## Testing

Dashboard verification is browser-visible, not `curl`-only. Prefer Browser Use
/ in-app browser for localhost lifecycle validation when available, use Computer
Use for visible human-like desktop checks, and use Chrome DevTools MCP for
console/network/DOM diagnosis. See [chrome-devtools-dashboard-testing.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/workflows/chrome-devtools-dashboard-testing.md).

Forward/reverse lifecycle validation uses the dashboard-first contract in [dashboard-first-validation.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/references/dashboard-first-validation.md). After bootstrap and launch, prompts and lifecycle actions must go through the Agent page, Backlog, Board, Inbox, and visible approvals; `builder` CLI is evidence and diagnosis, not the substitute product path.

For autonomous-run debugging, prefer `builder logs` for agent-efficient diagnosis, and use `builder logs analyze --session <id-or-prefix> --json` when you need prompt-level session review or observability coverage. The Agent page remains the user-friendly rendering surface.

For repo-local KB checks, prefer `builder knowledge validate --json` first to establish whether the corpus is trustworthy/current, then use `builder knowledge summary` and `builder knowledge show ... --section "Change guidance"` to check whether retrieval is bounded and useful for agents.
