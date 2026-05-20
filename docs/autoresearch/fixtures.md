# Fixtures — scripted operator prompts

Every loop iteration drives the same prompts in the same order so runs are comparable. Adding fixtures is fine; **changing or removing fixtures invalidates prior baselines** — recompute variance per [`baseline_variance.md`](baseline_variance.md).

Each fixture is a single operator session: start fresh devpulse, send prompt 1, answer follow-up cards as specified, observe shipping.

Use the same fresh `.seed/devpulse` snapshot for every fixture. Each fixture is independent — no carry-over.

---

## Fixture A — short-feature

**Intent**: minimum-viable feature creation, single small surface. Tests the happy path with low context cost.

**Prompt 1**: `Add a button on the homepage that shows the current time when clicked.`

**Expected intake**: zero or one clarifying question. If the agent asks, answer with the first `(Recommended)` option.

**Expected shipping**: 2–4 generated tasks. Single UI surface. No persistence.

**Pass criteria**:
- Feature visible in devpulse browser at the live port.
- Click shows current time.
- `npm run build && npm run test` passes.

---

## Fixture B — long-feature

**Intent**: medium-complexity feature with persistence + UI + behavior. Tests the full 5-task sprint pattern.

**Prompt 1**: `I want to add a notes feature so I can write short text notes that persist between visits.`

**Expected intake**: 1–3 clarifying questions. Answer all with first `(Recommended)` options.

**Expected shipping**: 4–6 generated tasks covering domain model, UI, behavior, persistence, verification.

**Pass criteria**:
- Notes can be created, saved, and reload after browser refresh.
- `npm run build && npm run test` passes.

---

## Fixture C — ambiguous-request

**Intent**: prompt that requires real clarification. Tests intake quality and operator-turn count.

**Prompt 1**: `Make the app better for power users.`

**Expected intake**: 2–4 clarifying questions. Answer with first `(Recommended)` options.

**Expected shipping**: whatever Builder scopes from the clarifications.

**Pass criteria**:
- Feature ships (board reaches `done`).
- No more than 5 operator turns to reach approval.
- `npm run build && npm run test` passes.

**This is the fixture most sensitive to context-bloat and operator-turn-count regressions.**

---

## Fixture D — vague-request

**Intent**: minimal info, tests whether Builder asks for what it actually needs vs. assuming.

**Prompt 1**: `Improve search.`

**Expected intake**: at minimum, agent must ask what's being searched. Answer: `Notes by their text content.`

**Pass criteria**:
- Feature ships.
- Agent did not assume scope without asking.
- `npm run build && npm run test` passes.

---

## Fixture E — edge-case (multi-turn intake)

**Intent**: explicitly multi-turn intake to detect context-loss regressions (the IMP-001 class).

**Prompt 1**: `I want to track something on the dashboard.`

**Prompt 2** (after agent's clarifying question): `Time spent per task this week.`

**Prompt 3** (after second clarifying question): `Just a number is fine, no chart needed.`

**Pass criteria**:
- Agent maintains context across all three turns — at turn 3 it must reference the original tracking intent without re-asking.
- Feature ships.
- `npm run build && npm run test` passes.

**This fixture must pass before Track B activates. If IMP-001 regresses, this fixture catches it.**

---

## Running a fixture

```bash
# 1. Fresh workspace from seed
rm -rf /tmp/devpulse-run-<id>
cp -r /home/gurusharangupta/.seed/devpulse /tmp/devpulse-run-<id>

# 2. Start builder on unique port
cd /tmp/devpulse-run-<id>
builder start --port <unique-port> --force &

# 3. Drive the prompt (browser or API harness — same script for every run)
#    Use the same delay between prompts to reduce timing variance.

# 4. Wait for board.current_sprint.active_phase == 'shipped' OR hard timeout 25 min

# 5. Capture evidence
builder logs analyze --session <session-id> --json > /tmp/run-<id>-analysis.json
builder metrics show --json --full > /tmp/run-<id>-metrics.json
builder board show --json > /tmp/run-<id>-board.json
cd /tmp/devpulse-run-<id> && npm run build && npm run test

# 6. Append row to optimize_results.tsv (or baseline_runs.tsv)

# 7. Teardown
builder server stop --port <unique-port>
rm -rf /tmp/devpulse-run-<id>
```

A harness script that automates steps 1–7 belongs in `scripts/` once Track A closes — not before. The loop docs above must be runnable manually first to validate the contract.

## Notes

- Fixtures here exercise feature-creation. They do not test improvement-of-existing-features. Add `Fixture F — improvement` once the base loop is proven and improvement cycles are stable.
- All fixtures must answer follow-up cards with `(Recommended)` to be deterministic. If a fixture uses a non-recommended option, that becomes the locked-in answer for that fixture forever.
