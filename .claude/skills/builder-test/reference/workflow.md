# Workflow — builder-test

Detailed expansion of the 6-phase verification loop.

---

## Phase 0 — PRECONDITIONS

**Abort on any failure here. All other phases depend on this.**

```bash
# 1. Is the builder process running?
ps aux | grep "builder start" | grep -v grep

# 2. Is it on the right port? (health endpoint is /health not /api/health)
curl -s http://localhost:9876/health | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status'))"

# 3. Does the project load? (must return devpulse project, not empty)
curl -s http://localhost:9876/api/projects/ | python3 -c "
import sys,json; d=json.load(sys.stdin)
items = d if isinstance(d,list) else d.get('items',[])
print(f'{len(items)} project(s): {[x[\"name\"] for x in items]}')
"
```

**If builder not running:**
```bash
cd /home/gurusharangupta/Builder-Workspace/devpulse
builder start --port 9876 &>/tmp/builder-test.log &
sleep 8
# Re-run checks above
```

**Critical**: if health returns `{"error": "No .agent-builder/ directory found"}` it
means builder started from the wrong directory. Kill and restart from
`/home/gurusharangupta/Builder-Workspace/devpulse`.

**Phase 0 artifact**: health check output + project name logged.

---

## Phase 1 — STATIC

**Flag findings, do NOT abort.**

### 1a. Pyright new warnings
```bash
# Run from source repo root; compare against known pre-existing warnings
cd /home/gurusharangupta/code/autonomous-agent-builder-codex-architecture-review/autonomous-agent-builder-codex-architecture-review
python3 -m pyright src/autonomous_agent_builder/embedded/server/ 2>&1 | grep "error:\|warning:" | grep -v "is not accessed" | head -20
```

Only flag warnings that are NEW (i.e., not the pre-existing "is not accessed"
false positives for private functions accessed via imports).

### 1b. Bad-string grep
Load `reference/assertions.md` §Known Bad Patterns. Run each grep against
changed files. Any match is a WARN finding with file:line citation.

```bash
# Example: check for hardcoded delivery phrases in publisher
grep -n "Ready for Builder to start now\|should I hold" \
  src/autonomous_agent_builder/embedded/server/agent_chat_result_publisher.py

# Check for plain-text question patterns in prompt builders
grep -n "Ready for Builder to start now" \
  src/autonomous_agent_builder/embedded/server/agent_prompt_builders.py
```

**Phase 1 artifact**: list of new Pyright warnings + bad-string hits (may be empty).

---

## Phase 2 — UNIT

**Per-function behavioral assertions. Flag failures, do NOT abort.**

Run assertions from `reference/assertions.md` §Unit Assertions. Each assertion
maps to a specific function; call it inline with Python -c or a short script.

```bash
cd /home/gurusharangupta/code/autonomous-agent-builder-codex-architecture-review/autonomous-agent-builder-codex-architecture-review

# Intent classifier assertions
python3 -c "
import sys; sys.path.insert(0,'src')
from autonomous_agent_builder.embedded.server.agent_message_intent import message_requests_read_only_status

cases = [
    # (message, expected_read_only, label)
    ('what is the status of the backlog', True,  'status query → read-only'),
    ('check the current board', True,  'check board → read-only'),
    ('verify the sprint status', True,  'verify sprint → read-only'),
    ('implement fix for the backlog', False, 'implement → NOT read-only'),
    ('fix the intent classifier', False, 'fix → NOT read-only'),
    ('create a new feature for backlog', False, 'create → NOT read-only'),
    ('dispatch the next task', False, 'dispatch → NOT read-only'),
    ('update the status of item X', False, 'update → NOT read-only'),
]
fails = []
for msg, expected, label in cases:
    got = message_requests_read_only_status(msg)
    status = 'PASS' if got == expected else 'FAIL'
    if status == 'FAIL':
        fails.append(f'  FAIL: {label!r} expected={expected} got={got}')
    print(f'{status}: {label}')
if fails:
    print('\nFAILED:')
    for f in fails: print(f)
    sys.exit(1)
else:
    print('\nAll intent classifier assertions passed.')
"
```

Also assert:
- `mcp__builder__backlog_item_update` present in tool registry
- Chat agent definition has `AskUserQuestion` tool
- `feature_captured = False` initialization present in publisher (grep)

**Phase 2 artifact**: per-assertion PASS/FAIL + failing cases with expected vs got.

---

## Phase 3 — INTEGRATION

**REST API smoke tests. Abort E2E if any endpoint unreachable.**

```bash
# Get project ID first (required for backlog endpoint)
PROJECT_ID=$(curl -s http://localhost:9876/api/projects/ | python3 -c "
import sys,json; d=json.load(sys.stdin)
items = d if isinstance(d,list) else d.get('items',[])
print(items[0]['id'] if items else '')
")

# Backlog items endpoint (project-scoped path)
curl -sf "http://localhost:9876/api/projects/${PROJECT_ID}/backlog/items" | python3 -c "
import sys,json; d=json.load(sys.stdin)
items = d if isinstance(d,list) else d.get('items',[])
print(f'backlog/items: {len(items)} item(s) — OK')
"

# Board endpoint (dashboard-scoped path)
curl -sf http://localhost:9876/api/dashboard/board | python3 -c "
import sys,json; d=json.load(sys.stdin); print('dashboard/board: OK — keys:', list(d.keys())[:5])
"

# Builder CLI round-trip (requires AAB_API_URL — not AAB_PORT, which is server-only)
AAB_API_URL=http://localhost:9876 builder backlog item list --json 2>&1 | python3 -c "
import sys,json; d=json.load(sys.stdin)
items = d.get('data', d if isinstance(d,list) else d.get('items',[]))
print(f'builder CLI: {len(items)} item(s) — OK')
"
```

**Phase 3 artifact**: endpoint reachability + item counts.

---

## Phase 4 — E2E

**Submit operator instruction. Observe session behavior. Verify side-effects.**

### 4a. Submit instruction via dashboard (webwright)

Navigate to `http://localhost:9876` (Agent page). Type the operator instruction
appropriate to what was changed. Click Send. Wait for session to complete or
reach a question/approval state.

### 4b. Observe session

```bash
# After session completes, list recent sessions via REST API (CLI --full flag is unreliable)
curl -s "http://localhost:9876/api/agent/chat/sessions?limit=3" | python3 -c "
import sys,json
d=json.load(sys.stdin)
sessions = d if isinstance(d,list) else d.get('sessions', d.get('results',[]))
for s in sessions[:3]:
    print('session_id:', s.get('id', s.get('session_id','?')))
    print('stop_reason:', s.get('stop_reason','?'))
    print('turn_count:', s.get('turn_count','?'))
    print('cost_usd:', s.get('cost_usd','?'))
    print('---')
"
```

**Key observations**:
- `stop_reason` should be `end_turn` or `delivery_permission_*` — NOT `max_turns`
- Turn count should be ≤ configured dispatch discipline cap (≤3 exploration turns)
- Tool call sequence: should include `mcp__builder__task_dispatch` if implementation requested

### 4c. Verify output type (NOT content)
```bash
# Check last assistant message event type via REST API
SESSION_ID="<id from 4b>"
curl -s "http://localhost:9876/api/agent/chat/history?session_id=${SESSION_ID}" | python3 -c "
import sys,json
d=json.load(sys.stdin)
events = d if isinstance(d,list) else d.get('events', d.get('messages',[]))
roles = [e.get('role', e.get('event_type','?')) for e in events]
ask_q = [e for e in events if 'ask_user' in str(e.get('event_type','')).lower()]
print(f'Total events: {len(events)}')
print(f'ask_user_question events: {len(ask_q)}')
for e in events[-2:]:
    role = e.get('role', e.get('event_type','?'))
    content = str(e.get('content',''))[:120]
    print(f'[{role}]: {content}')
if ask_q:
    print('AskUserQuestion fired — PASS')
else:
    print('No AskUserQuestion — OK for read-only queries; WARN for implementation requests')
"
```

### 4d. Side-effect verification
```bash
# Backlog items BEFORE and AFTER — check for duplicates
AAB_API_URL=http://localhost:9876 builder backlog item list --json 2>&1 | python3 -c "
import sys,json
from collections import Counter
d=json.load(sys.stdin)
items = d.get('data', d if isinstance(d,list) else d.get('items',[]))
titles = [x.get('title','') for x in items]
dupes = {t:c for t,c in Counter(titles).items() if c>1}
if dupes:
    print('WARN — duplicate backlog items:', dupes)
else:
    print(f'No duplicates — {len(items)} item(s) — OK')
"
```

**Phase 4 artifact**: session JSON (turns, stop_reason, cost) + event type counts + duplicate check result.

---

## Phase 5 — VERDICT

Produce PASS/WARN/FAIL table. Use evidence from Phases 0–4.

```
| Phase        | Status | Finding                         | Evidence        |
|--------------|--------|---------------------------------|-----------------|
| 0 Precond    | PASS   | builder on :9876, devpulse loads | health + proj   |
| 1 Static     | WARN   | 2 pre-existing Pyright warnings  | pyright output  |
| 2 Unit       | PASS   | 8/8 intent assertions passed     | assertion log   |
| 3 Integration| PASS   | all endpoints reachable          | curl outputs    |
| 4 E2E        | PASS   | ask_user_question fired, 0 dupes | session JSON    |
| Overall      | WARN   | pre-existing warnings only       |                 |
```

**Overall verdict rules**:
- `PASS` — no FAILs in any phase
- `WARN` — at least one WARN, no FAILs (proceed with caveats)
- `FAIL` — at least one FAIL → proceed to FIX step before CLOSEOUT

---

## Phase 5b — FIX (only when verdict contains FAILs)

For each FAIL row in the verdict table:

### 1. Diagnose root cause

Ask: where does the issue actually live?

| Issue location | Fix target |
|---|---|
| Wrong value/behavior in builder source code | Fix in `src/` — surgical, minimal change |
| Stale test data (assertion expects old behavior) | Update the assertion in `reference/assertions.md` |
| Wrong command in skill procedure | Fix the command in `reference/workflow.md` |
| Wrong environment variable or path in procedure | Fix where it appears — do NOT add a workaround |

**Never add a Gotcha or workaround to the skill when the underlying cause can be fixed.
Patching symptoms hides real problems and degrades test fidelity over time.**

### 2. Apply the fix

Fix the root cause directly. If the fix is in `src/`:
- Read the relevant file first
- Make the minimal change that addresses the issue
- Do not refactor surrounding code or fix unrelated things

If the fix is in test data or procedure:
- Update only the specific assertion row or command that was wrong
- Explain why the old form was wrong in a comment or note

### 3. Re-run the affected phase

```bash
# Example: re-run unit assertions after fixing intent classifier or updating assertions
python3 -c "
import sys; sys.path.insert(0,'src')
# ... paste the phase assertion script here
"
```

Every FAIL must reach PASS or WARN before moving to CLOSEOUT.
If a FAIL cannot be fixed (genuine external limitation), document it explicitly
in the verdict table with `KNOWN-LIMITATION` status and a one-line reason.

---

## Phase 6 — CLOSEOUT

**Mandatory after every run, including PASS runs.** This is what keeps the skill
self-evolving. Skip it and the skill will drift into a historical document.

### 6a. Staleness scan

```bash
# Verify every cross-referenced file still exists at its stated path
python3 - <<'PY'
from pathlib import Path
cross_refs = [
    "src/autonomous_agent_builder/embedded/server/agent_message_intent.py",
    "src/autonomous_agent_builder/embedded/server/agent_chat_result_publisher.py",
    "src/autonomous_agent_builder/embedded/server/agent_chat_transcript.py",
    "src/autonomous_agent_builder/agents/definitions.py",
    "src/autonomous_agent_builder/agents/tool_registry.py",
    "src/autonomous_agent_builder/embedded/server/agent_sprint_planning.py",
]
for p in cross_refs:
    status = "OK " if Path(p).exists() else "STALE — remove or update cross-reference"
    print(f"{status}  {p}")
PY
```

For each STALE result: update the cross-reference in `SKILL.md` to the new path,
or remove it if the file was deleted. Never leave a broken cross-reference.

### 6b. Assertion freshness check

For each unit assertion in `reference/assertions.md`, verify the symbol still exists:

```bash
# Intent classifier function
grep -q "message_requests_read_only_status" \
  src/autonomous_agent_builder/embedded/server/agent_message_intent.py \
  && echo "OK  message_requests_read_only_status" || echo "STALE — update assertion"

# Tool registry entry
grep -q "mcp__builder__backlog_item_update" \
  src/autonomous_agent_builder/agents/tool_registry.py \
  && echo "OK  backlog_item_update" || echo "STALE — update assertion"

# Publisher feature_captured pattern
grep -q "feature_captured" \
  src/autonomous_agent_builder/embedded/server/agent_chat_result_publisher.py \
  && echo "OK  feature_captured" || echo "STALE — update assertion"

# force parameter in sprint planning
grep -q "force: bool = False" \
  src/autonomous_agent_builder/embedded/server/agent_sprint_planning.py \
  && echo "OK  force param" || echo "STALE — update assertion"
```

**If STALE**: update or remove the assertion in `reference/assertions.md`. A stale
assertion that always passes because the symbol doesn't exist is worse than no
assertion — it gives false confidence.

### 6c. Bad-string pattern review

For each pattern in `reference/assertions.md §Known Bad Patterns`:
- **0 matches + the fix is guarded in code** → keep as regression guard, add a
  comment confirming "fixed in commit X, kept as regression guard"
- **0 matches + no guard in code** → the pattern may no longer exist; remove it
  and add a note in introspection.md
- **Matches found** → FAIL was already reported in Phase 1; no further action here

```bash
# Quick check: do any bad patterns still match anywhere in the codebase?
grep -rn "Ready for Builder to start now\|should I hold" \
  src/autonomous_agent_builder/embedded/server/ 2>/dev/null \
  && echo "STILL PRESENT" || echo "CLEAN — regression guard only"
```

### 6d. New patterns from this run

If Phase 4 E2E or Phase 2 Unit surfaced a failure mode **not currently in
`reference/assertions.md`**, add it now:

- New bad string → add a grep block to §Known Bad Patterns with `Why:` explanation
- New unit regression → add a row to the relevant assertion table
- New E2E observation → add a row to the E2E Observation Checklist

If the failure was a new Gotcha (something that bit you that violated a reasonable
assumption), add it to `SKILL.md §Gotchas`.

### 6e. Write introspection, apply, delete

```markdown
# introspection.md — builder-test run <date>

## What went perfectly
- [phase name]: zero corrections needed.

## Staleness found and fixed
| Item | Was | Now | File |
|---|---|---|---|
| cross-ref | old path | new path | SKILL.md |

## New patterns added
| Pattern | Why | File |
|---|---|---|
| grep for X | found in E2E | assertions.md |

## Patterns removed (stale)
| Pattern | Reason for removal |
|---|---|
| grep for Y | fixed in source + no guard needed |

## Friction points
| # | Symptom | Root cause | Fix type | Target |
|---|---|---|---|---|
```

Apply every row. Then:

```bash
rm -f outputs/builder-test-run/introspection.md
echo "Closeout complete — skill updated."
```

**The skill is only done when introspection.md is deleted.** If it still exists,
the loop is open and the skill has not yet self-improved from this run.
