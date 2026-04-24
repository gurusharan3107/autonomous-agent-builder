Always read `~/.claude/CLAUDE.md` first, then repo-local `CLAUDE.md`.

## Triggers

| When | Command | Purpose |
|------|---------|---------|
| Starting task | `builder memory search "<query>"` | Check repo precedent |
| Unfamiliar workflow | `workflow --docs-dir docs summary <name>` | Load repo workflow doc |
| System-wide product improvement or real-user debugging | `workflow --docs-dir docs summary system-improvement-loop` | Reproduce, trace true owner, fix, retest |
| Reverse-engineering validation on an existing repo | `workflow --docs-dir docs summary reverse-engineering-autonomous-lifecycle-validation` | Use a disposable external repo clone as the subject; do not use `autonomous-agent-builder` itself as the reverse-engineering test target. |
| Runtime failure, opaque deny, or Agent-page log diagnosis | `builder logs --error`; `builder logs --info --compact --json` | Check builder-owned runtime evidence first. Use `builder logs` as the canonical agent-facing debug lane; use the Agent page as the user-friendly view of the same run. |
| Checking whether repo-local KB is current and agent-friendly | `builder knowledge validate --json`; `builder knowledge summary "<query>"`; `builder knowledge show <doc> --section "Change guidance"` | Use `validate` for trust/freshness and `summary`/`show` for bounded retrieval quality; do not rely on only one of the two |
| Choosing retrieval lane | `builder knowledge ...`; `workflow --docs-dir docs summary <name>` | Use `builder knowledge` for repo-local feature context, system architecture, implementation state, and testing surfaces. Use `workflow --docs-dir docs` for contracts, workflows, quality gates, and other owner docs under `docs/`. |
| Changing phase boundaries, operator questioning, or per-phase tool permissions | `workflow --docs-dir docs summary phase-model` | Load the canonical phase contract before changing requirements/planning/design/implementation/verification/integration behavior. |
| Dashboard/UI assessment without requested edits | Verify the live dashboard first | Separate evaluation from implementation before proposing changes |
| Dashboard/frontend work | `workflow --docs-dir docs summary design-language` | Load visual rules |
| Task isolation or resume questions | `workflow --docs-dir docs summary task-workspace-isolation` | Load workspace contract |
| Repo-local product knowledge or state | `builder knowledge summary <query>` | Use `builder` for repo-local knowledge, memory, and delivery state |
| Cross-project precedent or external repo behavior | `workflow knowledge search "<query>"` | Use `workflow` for broader research/global doctrine; use DeepWiki MCP when GitHub repo context is needed |
| Architecture or boundary review, including Codex subagent design | `workflow --docs-dir docs summary architecture-boundary-review` | Load the bounded architecture-review lane and use `architecture_reviewer` only for explicit subagent asks or second-pass architecture audits |
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
| `lsof -nP -iTCP:9876 -sTCP:LISTEN` | Check server |
| `pytest --collect-only` | Collect tests |
| `builder map` | Bounded workspace digest |
| `builder context <task>` | Task bootstrap |
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
- `AGENTS.md` owns triggers, retrieval shortcuts, and validation entrypoints.
- `docs/references/phase-model.md` and `docs/references/phases/*.md` own the canonical phase-boundary contract.
- `docs/workflows/` owns multi-step procedures.
- Repo-specific docs stay in repo `docs/`; do not move product-runtime responsibilities into `~/.codex` surfaces.
- `builder memory` owns repo-specific decisions, patterns, and corrections.
- `builder knowledge` owns repo-local system docs, including seed extraction, maintained feature docs, and testing docs.
- `workflow --docs-dir docs` owns repo-local contracts, workflows, quality gates, and other canonical docs under `docs/`.

## Testing
Dashboard verification uses Chrome DevTools MCP, not `curl`. See [chrome-devtools-dashboard-testing.md](/Users/gurusharan/Documents/remote-claude/active/apps/autonomous-agent-builder/docs/workflows/chrome-devtools-dashboard-testing.md).

For autonomous-run debugging, prefer `builder logs` for agent-efficient diagnosis and use the Agent page as the user-friendly rendering surface.

For repo-local KB checks, prefer `builder knowledge validate --json` first to establish whether the corpus is trustworthy/current, then use `builder knowledge summary` and `builder knowledge show ... --section "Change guidance"` to check whether retrieval is bounded and useful for agents.
