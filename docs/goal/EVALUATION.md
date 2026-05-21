# Evaluation — Tiered Scorecard

> **Read [README.md](README.md) and [NORTH-STAR.md](NORTH-STAR.md) first.**

Three tiers gate the work in [ROADMAP.md](ROADMAP.md). A milestone is *not* `done` until the tier of evaluation it claims to satisfy passes with cited evidence. A roadmap item is *not* `[x]` until its underlying evaluation rule passes.

| Tier | Cadence | Question it answers | Gates which roadmap content |
| --- | --- | --- | --- |
| **Tier 1 — Token + UX** | Every release; every sprint closeout | "Is the product currently usable and economically viable in both lanes?" | Every Epoch 1 milestone; baseline check for Epochs 2 and 3. |
| **Tier 2 — Lifecycle Coverage** | Every milestone closeout | "Does the product own the full SDLC the way no other tool does?" | Every Epoch 2 milestone; all of Epoch 3. |
| **Tier 3 — Head-to-Head** | Once before declaring "preferred"; revalidate quarterly | "Does Builder demonstrably win against Codex CLI and Claude Code on the same task?" | Epoch 3 only. |

Every tier is enforced through Builder-owned CLI evidence, dashboard-visible state, and (where stated) browser-visible proof. Assistant-summary text is never accepted as evidence.

---

## Tier 1 — Token + UX Bars (every release)

This tier is the floor. The product cannot regress below these bars in any release, on either runtime lane.

### 1.1 — Token efficiency bars (per session, per shipped feature)

| Bar | Threshold | Verification |
| --- | --- | --- |
| Cache ratio after turn 2 | `cache_ratio > 5x` for every subsequent agent turn | `builder logs analyze --session <id> --json` |
| Chunk pressure | `chunk_pressure_risk: false` across the entire feature run | `builder metrics show --json --full` |
| Avoidable cost flags | `avoidable_cost_flags: []` at session close | `builder metrics show --json --full` |
| Recent risky / large-output runs | `recent_risky_runs: 0`, `recent_large_output_runs: 0` for the shipped feature | `builder metrics show --json --full --limit 8` |
| Recommended next change | `maintain_current_flow` on clean active evidence | `builder metrics show --json --full` |
| CLI / UI surface parity | `builder metrics show` and the Metrics page agree with `builder logs --compact` raw cost data | Cross-check command output against dashboard |

A `false` for any bar is a Tier 1 failure. Root-cause it; do not paper over.

### 1.2 — Operator UX bars (per session)

| Bar | Pass signal | Verification |
| --- | --- | --- |
| Banned terms absent | Zero leakage of banned operator-facing terms (see [OPERATOR-LANGUAGE.md § Banned Operator-Facing Terms](OPERATOR-LANGUAGE.md#banned-operator-facing-terms)) | Manual transcript audit of Agent page + Voice tab + Board + Backlog + Inbox + Settings |
| Readable question/approval cards | All pending cards render readable labels (no `[object Object]`, no raw payload, no internal payload keys) | Browser inspection during the run |
| Inline decision controls | Question/approval response controls live in the composer/footer, not as a second control owner in the timeline | Browser inspection |
| Zero stale messages | After a successful flow, no superseded "I do not have a captured improvement" / stale status / wrong-state messages remain visible | `/api/agent/chat/history` audit + browser refresh |
| Recover button only when recoverable | Board renders Recover only when the task's blocked-reason is actually recoverable; otherwise an actionable next-step message | Browser inspection during a blocked-state test |
| Voice transcript labels | `Operator` / `Samantha` labels (not `Operator to Samantha`, not `thinking · Samantha`) | Voice tab inspection |

### 1.3 — Both-lane parity bar

Every Tier 1.1 and 1.2 bar must hold on **both** runtimes for the **same operator wording** on the **same workspace**. Lane-asymmetric wins are tracked as gaps in [STATUS.md](STATUS.md), not silently accepted.

Verification command per lane:

```bash
# Claude Agent SDK lane
builder agent runtime set --sdk claude --provider claude_agent_sdk --json
# ...run the operator scenario...
builder logs analyze --session <id> --json
builder metrics show --json --full

# Codex SDK lane
builder agent runtime set --sdk codex_sdk --provider codex_subscription --json
# ...same operator scenario, same wording...
builder logs analyze --session <id> --json
builder metrics show --json --full
```

### 1.4 — Builder-owned evidence bars

| Bar | Verification |
| --- | --- |
| Quality gate clean for touched surfaces | `builder quality-gate <surface> --json` returns `ok` for every surface in the change |
| Complexity ratchet not regressed | `builder lint --complexity-report --json` reports `0 violations` |
| Knowledge base validated | `builder knowledge validate --json` returns `ok` for any change affecting maintained docs |
| Memory write contract | `builder memory lint --json` clean; durable learnings have a memory entry per the closeout rule in [FIX-STANDARD.md § Step 7](FIX-STANDARD.md#step-7--write-memory-back-if-the-learning-is-durable) |

---

## Tier 2 — Lifecycle Coverage Bars (every milestone)

This tier proves the product owns the full SDLC the way no other tool does. Tier 2 always runs after Tier 1 passes.

### 2.1 — Full SDLC dashboard visibility

For the milestone's chosen scenario, every lifecycle phase produces visible product evidence:

- Requirements: intake transcript captured; clarification questions answered inline.
- Design: design document persisted in the design phase drawer.
- Backlog: backlog item created with type (`feature` / `improvement` / `optimization` / `incident`) and source.
- Sprint planning: sprint plan persisted; approval card visible and resolved.
- Implementation: task dispatched, code-gen run visible with token/turn evidence.
- Verification: deterministic gates (`build_verify` / `change_evidence`) and (when applicable) feature acceptance / browser proof.
- Ship: Board card moves to `shipped`; closeout event in Agent timeline; final token totals.
- Optimization: post-ship recommendations visible in the Metrics page Observability lane.

Missing any phase evidence = Tier 2 failure for the milestone.

### 2.2 — Resumability bars

| Bar | Test | Pass signal |
| --- | --- | --- |
| Mid-sprint dashboard restart | Kill the dashboard mid-sprint; restart from current Builder checkout | Same Board lanes, same Backlog state, same Agent transcript, same Inbox; no stale running marker |
| Mid-project runtime switch | Switch from `claude` → `codex_sdk` (or back) between sprints | Historical attribution preserved; future work uses the new lane; no metric/log/observability mixing |
| Session drop + fresh agent resume | Wipe agent context; new agent reads `docs/goal/STATUS.md` and resumes | New agent identifies current milestone and next action correctly from STATUS.md alone |
| Long-horizon resume | Return to a project after a defined gap (target: 30+ days for Epoch 3) | Memory and KB still relevant; no orphaned approvals; Inbox shows true pending state |

### 2.3 — Workspace rotation bar

Tier 2 requires both:

| Scenario | Both lanes? | Evidence |
| --- | --- | --- |
| Forward-engineering: fresh app from scratch | Yes | Fresh workspace boot → intake → ship → browser-visible feature |
| Reverse-engineering: operate on existing app | Yes | Existing workspace (todo-app / external clone) → "Add a search box" or "Fix this button" → ship → browser-visible delta |

Rotating workspaces every milestone is the contract. Don't always test on the same workspace. See [ROADMAP § M1.4](ROADMAP.md#m14--two-workspace-validation-rotation).

### 2.4 — Memory and knowledge compounding bar

For the milestone's chosen topic, prove that the system's memory/KB makes a *future* session faster or more correct than the *original* session:

- Identify the topic and the relevant memory entries (`builder memory search "<topic>"`).
- Run a fresh session that hits the same class of decision.
- Verify the fresh session retrieves precedent and reaches the right call without re-litigation.
- If not, the memory entry is wrong or the retrieval workflow is broken — fix and retry.

### 2.5 — Rubric / quality-gate pass bar

Every milestone in scope must pass its owning rubrics and quality gates listed in [INDEX.md § External Owner Map](INDEX.md#external-owner-map). The full active set today:

- `docs/rubric/sdk-backed-agent-page-agent.md`
- `docs/rubric/realtime-voice-agent-page-agent.md`
- `docs/rubric/operator-limits.md`
- `docs/rubric/autonomous-builder-agents.md`
- `docs/rubric/deterministic-vs-model-backed-agent-behavior.md`
- `docs/rubric/frontend-react-architecture.md`
- `docs/rubric/backend-service-architecture.md`
- `docs/quality-gate/claude-agent-sdk.md`
- `docs/quality-gate/modular-runtime.md`
- `docs/quality-gate/product-lifecycle.md`
- `docs/quality-gate/state-integrity.md`
- `docs/quality-gate/agent-quality.md`
- `docs/quality-gate/architecture-invariants.md`
- `docs/quality-gate/architecture-boundary.md`
- `docs/quality-gate/dashboard-ux.md`
- `docs/quality-gate/complexity.md`
- `docs/quality-gate/approval.md`
- `docs/quality-gate/builder-cli.md`
- `docs/quality-gate/knowledge-base.md`

---

## Tier 3 — Head-to-Head Bars (to declare "preferred")

This tier exists to make the "preferred" claim defensible against scrutiny. Tier 3 only runs at the start of Epoch 3 and at quarterly cadence thereafter.

### 3.1 — Canonical task set

Defined at the start of Epoch 3 (see [ROADMAP § M3.4](ROADMAP.md#m34--head-to-head-benchmark-wins)). The set must include:

- A simple forward-engineering task (one feature in a fresh app).
- A non-trivial forward-engineering task (multi-feature project with persistence and UI).
- A reverse-engineering bug fix in an existing repo.
- A reverse-engineering feature addition in an existing repo.
- A lifecycle-coverage task: ship → 30-day gap → resume → add a second feature on the same project. *This task is the structural test — Codex CLI and Claude Code cannot complete it because they lack durable lifecycle state.*

### 3.2 — Measurement protocol

For each task and each tool (Codex CLI, Claude Code, Builder `claude` lane, Builder `codex_sdk` lane):

| Metric | Captured by |
| --- | --- |
| Total tokens (raw, cached, non-cached+output) | Tool-native telemetry; for Builder, `builder logs analyze --session <id> --json` |
| Total turns | Tool-native telemetry |
| Total wall-clock seconds | Wall clock from operator's first prompt to "shipped" |
| Operator interventions | Count of operator messages required after the initial prompt to reach shipped |
| Success without intervention | Binary: did the tool ship the feature with zero corrective operator turns? |
| Durable state at end | Inspect: backlog/memory/KB/metrics — does anything persist for a future session? |

### 3.3 — Win bars

To declare "preferred over Codex CLI and Claude Code":

- Builder wins on **tokens-per-shipped-feature** on a majority of canonical tasks in both lanes.
- Builder wins on **success-without-intervention** on a majority of canonical tasks in both lanes.
- Builder wins on **wall-clock-to-shipped** (including operator time) on a majority of canonical tasks in both lanes.
- Builder is the **sole completer** of the lifecycle-coverage task.

A single tie or single loss is acceptable per metric; a majority loss on any metric blocks the claim.

### 3.4 — Evidence archive

All Tier 3 measurement runs persist under `docs/goal/benchmarks/` (subfolder created when Tier 3 is first run). Each run records: tool, lane (if applicable), task ID, prompt verbatim, token/turn/wall-clock evidence, operator-intervention log, and final state.

### 3.5 — Relationship to autoresearch (Track B)

Tier 3 and the autoresearch loop in [`docs/autoresearch/`](../autoresearch/README.md) are tightly coupled:

- **Autoresearch produces Tier 3 evidence.** Each `keep`-status row in `docs/autoresearch/optimize_results.tsv` is an attested composite-metric improvement, gate-passing, in both runtime lanes. That is exactly the per-task evidence Tier 3 needs.
- **Tier 3 raises the bar autoresearch optimizes for.** The canonical task set in [§ 3.1](#31--canonical-task-set) becomes the long-form fixture set for the autoresearch loop once short fixtures (A–E in [`docs/autoresearch/fixtures.md`](../autoresearch/fixtures.md)) plateau.
- **Promotion path.** An optimization the autoresearch loop kept against fixtures A–E becomes a Tier 3 candidate only after it ships against the canonical task set with all hard gates still passing.
- **Activation order is fixed.** Tier 3 head-to-head benchmarks run only after [ROADMAP.md § M3.4](ROADMAP.md#m34--head-to-head-benchmark-wins) starts; autoresearch activates only at [ROADMAP.md § M3.5](ROADMAP.md#m35--optimization-loop-activation-autoresearch-track-b). M3.4 informs M3.5 (what to optimize for); M3.5 supplies M3.4 (with proven wins).

---

## How To Run Each Tier

```bash
# Tier 1 — after every shipped feature
SESSION_ID=<the agent session id>
builder logs analyze --session "$SESSION_ID" --json
builder metrics show --json --full --limit 8
builder logs --error --compact --json
builder board show --json
builder quality-gate <touched-surface> --json
builder lint --complexity-report --json
builder memory lint --json

# Tier 2 — at milestone closeout
# 1. Run the milestone scenario in both lanes (see Tier 1.3 commands)
# 2. Walk every lifecycle phase via dashboard
# 3. Execute the resumability test relevant to the milestone (2.2 table)
# 4. Run the rubric / quality-gate checks listed in 2.5
# 5. Update STATUS.md with evidence pointers per phase

# Tier 3 — to declare "preferred" (Epoch 3 only)
# 1. Run the canonical task set through Codex CLI
# 2. Run the canonical task set through Claude Code
# 3. Run the canonical task set through Builder claude lane
# 4. Run the canonical task set through Builder codex_sdk lane
# 5. Persist all evidence under docs/goal/benchmarks/
# 6. Apply the win bars (3.3) and record result in STATUS.md
```

## When This File Changes

`EVALUATION.md` changes when a bar is added, tightened, loosened, or retired. Every change must be paired with a justification in [STATUS.md § Recent Decisions](STATUS.md#recent-decisions) and (where it affects the roadmap) a roadmap update in the same change.
