# Autoresearch Known Hang Patterns

Catalogue of every diagnosed hang/blocker the autoresearch loop has surfaced.
Each entry is a self-contained postmortem: how the symptom looked in the
forensic dump, exactly how to confirm it's *this* pattern and not a similar
one, and where the fix lives. The patterns are listed roughly in order of
discovery; the diagnoser walks them sequentially and reports the highest-
confidence match.

This file is the source of truth that
`.claude/skills/autoresearch/scripts/diagnose_hang.py` consults. When a Fix
lane closes a new hang class, add an entry here AND extend the diagnoser's
matcher list. The two must stay in sync — drift between them is a freshness-
sweep finding.

## How to use

```bash
python3 .claude/skills/autoresearch/scripts/diagnose_hang.py <dump-dir>
# e.g.
python3 .claude/skills/autoresearch/scripts/diagnose_hang.py \
    /tmp/autoresearch/diagnostics/20260523T084141Z-pid1668336
```

The script prints `{pattern_id, confidence, evidence, fix_pointer}` for the
top match, or `unknown` if no pattern fits. When `unknown` fires, treat it as
the next Fix lane: diagnose by hand, then add the pattern here.

A pattern's `evidence` predicate is intentionally narrow. Two hangs with the
same *symptom* (e.g., "main thread idle") can have different root causes. The
evidence query must distinguish them.

---

## P1 — Harness API contract drift (chat history + respond)

- **First seen:** 2026-05-23, cycle 2
- **Wallclock to repro:** ~3 min (watchdog fires at idle threshold)
- **Status:** Fixed (run.py aligned to current `agent_api_models.py`)

**Symptom.** Watchdog fires while builder is healthy and the chat session has
a `chat_event` of type `ask_user_question` with `status='pending'`. raw_bodies
shows ~3 model API calls (the intake exchange) then stops.

**Evidence query.**

1. `chat_events` table for the active session has at least one row with
   `event_type='ask_user_question' AND status='pending' AND payload_json
   contains "answered":false`.
2. There is **no** matching `ask_user_question_answer` event.
3. `raw_bodies/` file count is small (under ~10) — the harness made the
   initial chat POST and then nothing.
4. Main thread `wchan=do_epoll_wait`, all workers `futex_wait_queue` — builder
   is healthy, waiting on operator input that never comes.

**Why it happens.** Two contracts must align across separate files:

| Symbol | Definition source (truth) | Harness expected (was wrong) |
|---|---|---|
| `ChatHistoryResponse.items` | `src/autonomous_agent_builder/embedded/server/agent_api_models.py:40-51` | `events` |
| `TimelineItem.status` | same file:32-37 | `state` |
| `ChatRespondRequest.event_id` | same file:93-100 | `request_id` |
| `ChatRespondRequest.selected_options` | same file | `option_index` |
| `ChatRespondRequest.custom_text` | same file | `text` |

**Fix pointer.** `scripts/autoresearch/run.py:get_pending_question` +
`send_chat_respond`. Aligned 2026-05-23 (cycle 2 close). Roadmap line: M3.5
"three-way intake contract drift with Builder chat agent".

**Recurrence prevention.** Add a CI test that imports both files and asserts
`{ChatHistoryResponse, ChatRespondRequest, TimelineItem}` field-name presence
matches what `run.py` reads. If `agent_api_models.py` is renamed again, CI
catches it instead of autoresearch.

---

## P2 — Builder chat agent ends in free-text scoping (no structured question)

- **First seen:** 2026-05-23, cycle 3
- **Wallclock to repro:** ~6 min wallclock; ~3 min idle
- **Status:** Fixed (proceed_needed outcome + auto-continue)

**Symptom.** P1 fix is applied (field names correct). Watchdog fires while
the session's most recent `chat_event` is an `assistant_message` containing
markdown numbered questions ("1. How should... 2. Where should... 3. What
format..."). Latest `run_status` says `running=false, stop_reason=end_turn`.
**There is no `ask_user_question` event** — the model asked in free text only.

**Evidence query.**

1. Latest `chat_events` row for the session is `event_type='assistant_message'`
   AND payload content matches `/\?|^\s*\d+\.\s/m` (interrogative or numbered).
2. Latest `run_status` event has `running=false`.
3. No `ask_user_question` event exists with `status='pending'` in this session.
4. `tasks WHERE chat_session_id=<sess>` returns zero rows — no delivery plan
   was triggered.

**Why it happens.** Builder's chat agent has two intake paths:

- *Structured intake:* the chat agent fires a delivery-permission
  `ask_user_question` event after scoping. The harness handles this via P1's
  `get_pending_question` / `send_chat_respond`.
- *Free-text intake:* the chat agent emits a markdown follow-up question
  inside an `assistant_message` and ends the run. This is normal Builder
  behavior for short or ambiguous prompts. There is no structured event for
  the harness to detect, and `run_status.running=false` so polling for a
  question is futile.

**Fix pointer.** `scripts/autoresearch/run.py:wait_for_question_or_ship` —
adds the `proceed_needed` outcome (returned when `running=false` and the
latest event is `assistant_message`); the outer main loop sees this and sends
a "proceed with reasonable defaults" `send_chat` continuation. Capped by
`max_questions=25` so an infinitely-asking model cannot loop forever.

**Recurrence prevention.** None at CI time — the chat agent's intake path is
a model behavior, not a contract. The fix is the right defensive boundary.

---

## P3 — Hang-watchdog single-signal false positive

- **First seen:** 2026-05-23, cycle 4
- **Wallclock to repro:** ~7 min total; watchdog fired at 3:22
- **Status:** Fixed (dual signal)

**Symptom.** Watchdog dumps a STUCK_DETECTED for a builder that was, in fact,
making progress: `raw_bodies/` grew steadily during the alleged hang window
(many more model API calls happened *after* the WAL went idle).

**Evidence query.**

1. `STUCK_DETECTED.json` shows `wal_last_mtime_iso` stale > idle threshold.
2. BUT one or more `raw_bodies/*` files were written *within* the idle
   threshold (i.e., raw_bodies kept advancing while the WAL stayed flat).
3. `agent_runs` for the active task has `status='running'` with multiple
   `agent_run_events` rows. The model loop is alive; intermediate state just
   wasn't being persisted to the DB.

**Why it happens.** Builder's code-gen agent can spend several minutes inside
a tool-use chain. Each tool result triggers a model API call (raw_bodies++)
but not necessarily an `agent_run_events` insert (those are written at agent
boundaries, not every tool call). WAL idle alone overcounts hangs.

**Fix pointer.**
`.claude/skills/autoresearch/scripts/hang_watchdog.py:_raw_bodies_max_mtime`
plus dual-signal logic in main loop: `live_mt = max(WAL_mtime,
raw_bodies_max_mtime)`. STUCK_DETECTED metadata now records both timestamps
separately so future false positives are obvious in the dump.

**Recurrence prevention.** Watchdog smoke test on `--once`: ensures the
script exits 0 with no autoresearch workspaces running. Manual review of any
new STUCK_DETECTED is cheap — if raw_bodies idle < WAL idle by > 30s,
re-examine for false-positive class.

---

## P4 — subprocess pipe deadlock (run.py captured stdout/stderr without draining)

- **First seen:** 2026-05-23, cycle 4
- **Wallclock to repro:** ~6 min wallclock; hang triggered after 153 API calls
- **Status:** Fixed (redirect to log file)

**Symptom.** True dual-signal hang (P3-protected): both WAL and raw_bodies go
silent simultaneously. Thread states show **main thread `wchan=pipe_write`**
(not `epoll_wait`) and multiple CLOSE-WAIT sockets on builder's port with
non-zero `Recv-Q`.

**Evidence query.**

1. `process_threads.txt` contains a line `tid=<main> wchan=pipe_write` for
   builder's main thread.
2. `process_sockets.txt` contains 3+ rows with `State=CLOSE-WAIT` for builder's
   port (`Local Address:Port = 127.0.0.1:<port>`) AND `Recv-Q > 0` (data
   queued, not being read).
3. `process_fds.txt` shows fd 1 and fd 2 both pointing to `pipe:[<inode>]` —
   the inodes are the parent's PIPE buffers.

**Why it happens.** `subprocess.Popen(..., stdout=PIPE, stderr=PIPE)` allocates
~64KB pipe buffers per stream. The harness never reads from them. After
~MB of code-gen log output, the buffers fill, and builder's next stdout/stderr
write blocks. The blocking write happens inside builder's main thread, which
is also the asyncio event loop thread; once it blocks on the pipe, every
coroutine (including HTTP request handling — hence the CLOSE-WAIT pile-up)
stops making progress.

**Fix pointer.** `scripts/autoresearch/run.py:main` — Popen now writes to
`evidence_dir/builder_stdout_stderr.log` (file handle, never blocks). Closed
in the `finally` cleanup so the file isn't leaked.

**Recurrence prevention.** Lint rule (informal): no `stdout=subprocess.PIPE`
on a long-lived Popen without an explicit drainer thread. Catchable at code
review.

---

## P5 — Sprint merge fails on `git checkout main` when seed default branch is `master`

- **First seen:** 2026-05-22 (Sprint 2 from prior session), reproduced 2026-05-23 cycle 5
- **Wallclock to repro:** ~9 min; sprint completes all tasks then blocks at merge
- **Status:** Fixed (skill-side); proper Builder-side fix tracked separately

**Symptom.** Every fixture A task completes successfully (`status='done'`,
every `gate_results.status='pass'`, feature-acceptance-tests pass,
build-verifier passes). Sprint never reaches `phase='shipped'`. Watchdog
fires because once verification is "blocked" no further state changes
happen.

**Evidence query.**

1. All `tasks WHERE chat_session_id=<sess>` rows have `status='done'`.
2. Latest `sprints` row for the project has `phase='blocked' AND
   verification_status='blocked'`.
3. `sprints.verification_evidence` JSON contains
   `"sprint_merge_error"` containing the string `"could not check out main"`.
4. The dumped DB's `agent_builder.db-wal` mtime equals roughly the
   `sprints.updated_at` (sprint moves to blocked, then nothing else writes).

**Why it happens.** Builder's `services/sprint_execution.py` sprint-merge
step does `git checkout main`. The devpulse template uses `master` as its
default branch (so does its upstream), and the immutable seed inherits that.
No `main` branch exists, so the merge step errors out — but every other
verification step (tests, build, gates) already passed.

**Fix pointer.** `scripts/autoresearch/run.py:restore_seed` — two changes:
**(1)** create `main` from current HEAD; **(2)** *more importantly*, repoint
`projects.repo_url` in the freshly-copied seed's SQLite DB to the ephemeral
workspace path. Without (2), `sprint_maybe_ff_merge` (in
`orchestrator/sprint_lifecycle.py:467-487`) reads
`task.feature.project.repo_url` which the seed had baked as
`~/Builder-Workspace/devpulse` (the upstream), and the merge runs there — not
the ephemeral. Cycle 6 (2026-05-23) re-hit P5 after the cycle-5 main-branch
fix because of this: the diagnoser matched P5 again with confidence 0.95
**even though main now existed in the ephemeral**, which forced re-reading
the sprint-lifecycle source and finding the repo_url issue. The proper
Builder-side fix (resolve project default branch dynamically instead of
hardcoding `main`) is a separate ROADMAP item under M2.3.

**Note for diagnoser.** P5 evidence query currently matches the *symptom*
(`sprint_merge_error contains "could not check out main"`). After this fix,
if the symptom recurs in cycle 7+, the diagnoser will still match P5 — which
means either the repo_url UPDATE didn't take, or there's a *third* layer
(e.g., Builder reading the URL from a cached config). Re-investigate, don't
assume the existing fix is sufficient.

**Recurrence prevention.** None until the Builder-side fix lands. The
skill-side workaround in `restore_seed` is idempotent and survives Builder
updates.

---

## P6 — Sprint merge post-check fails on tracked `.venv` entries

- **First seen:** 2026-05-23, cycle 7
- **Wallclock to repro:** ~11 min; surfaces after sprint completes everything
- **Status:** Fixed (untrack .venv in restore_seed)

**Symptom.** Same surface symptom as P5 (sprint phase=blocked,
verification_status=blocked, all tasks done) BUT the `sprint_merge_error`
contains `"tracked non-guidance changes after sprint merge"` plus a path
under `.venv/` — not `"could not check out main"`.

**Evidence query.**

1. All `tasks WHERE chat_session_id=<sess>` rows have `status='done'`.
2. Latest sprint `phase='blocked' AND verification_status='blocked'`.
3. `sprints.verification_evidence` JSON `sprint_merge_error` matches
   `/tracked non-guidance changes after sprint merge:.*\.venv/`.
4. `projects.repo_url` already points at the ephemeral workspace (P5 fix is
   in place — this is *after* P5).

**Why it happens.** The devpulse seed commits part of `.venv/` to git
(notably the `lib64` symlink). When task code-gen recreates `.venv`
fresh in the per-task workspace, those tracked entries no longer match what
git expects and show up as `D .venv/lib64` in `git status`. Builder's
`sprint_verify_clean_after_merge` (in `orchestrator/sprint_lifecycle.py`)
treats any tracked non-guidance change as a merge failure, so the sprint is
marked blocked even though every task, gate, and verification passed.

**Fix pointer.** `scripts/autoresearch/run.py:restore_seed` — after copying
the seed, `git rm -r --cached --ignore-unmatch .venv` then commit the
untracking. Working tree's `.venv` stays intact; git's index no longer tracks
it; subsequent merges don't see a phantom delete.

**Recurrence prevention.** Proper fix at the seed: don't commit `.venv` in
the first place (`echo .venv/ >> .gitignore && git rm -r --cached .venv`).
That requires recapturing the immutable seed, which is a Hard Rule 4 ritual.
The skill-side workaround in `restore_seed` is idempotent and safer for now.

---

## P7 — `latest_chat_state` reads `run_status` instead of the latest content event

- **First seen:** 2026-05-23, cycle 8 (regression in the P2 fix helper)
- **Wallclock to repro:** ~4 min (watchdog idle threshold, chat is alive but harness doesn't continue)
- **Status:** Fixed

**Symptom.** Same external symptom as P2 (chat ended, no ask_user_question
event, no tasks, no sprint) — but the P2 `proceed_needed` continuation
*never fires*. The harness sat polling for the full 25-min per-question
timeout. Cycle 8 hit this less than 4 min after starting because the chat
agent gave a clean "I'll proceed with reasonable defaults" intake response,
exactly the case `proceed_needed` was supposed to handle.

**Evidence query.**

1. `chat_events` last event is `run_status` with `running=false`.
2. The latest *non-`run_status`, non-`context_budget`* event is
   `assistant_message`.
3. No `ask_user_question` with `status='pending'`.
4. No tasks created.
5. The P2 fix is already in `run.py` (i.e., `proceed_needed` outcome exists)
   but it didn't fire.

Bullet 5 is what distinguishes P7 from P2: P2 is "no continuation path
exists", P7 is "the continuation path exists but its trigger predicate is
wrong".

**Why it happens.** `latest_chat_state()` had a bug: it iterated events in
reverse and set `last_event_type = item.get("type")` on the *first* item it
saw (the absolute most recent). Every chat ends with a `run_status` event
(running=false marker), so `last_event_type` always read `"run_status"` —
never `"assistant_message"`. The `proceed_needed` branch in
`wait_for_question_or_ship` only fires when `last_event_type ==
"assistant_message"`, so it never triggered.

**Fix pointer.** `scripts/autoresearch/run.py:latest_chat_state` — track
`last_content_event_type` separately, filtered to a whitelist of content
events (`assistant_message`, `ask_user_question`, `user_message`,
`tool_approval_request`). The `wait_for_question_or_ship` predicate reads
`last_content_event_type` instead of the all-types `last_event_type`.

**Recurrence prevention.** Add a unit test of `latest_chat_state` with a
mocked history containing `assistant_message` followed by `run_status`. The
test asserts `last_content_event_type == "assistant_message"`. Catches any
future "skip non-content events" regression at CI time.

---

## P8 — `run_status` events are not returned by `/api/agent/chat/history`

- **First seen:** 2026-05-23, cycle 9 (yet another regression in the P2 family)
- **Wallclock to repro:** ~4 min
- **Status:** Fixed

**Symptom.** Identical to P2 + P7: chat ends with a markdown clarifying
response, harness sits polling, watchdog fires. The P7 refinement (track
`last_content_event_type` separately) made `latest_chat_state` *capable* of
detecting the assistant_message correctly — but `state["running"]` still
read True, so the `proceed_needed` branch (`not state["running"] and
last_content_event_type == "assistant_message"`) never short-circuited.

**Evidence query.**

1. Same as P2/P7 evidence (chat ended, assistant_message latest, no question
   pending, no tasks).
2. The latest `assistant_message.payload.final == true` (Builder's actual
   "chat is done" marker).
3. P2 and P7 fixes are already in `run.py` — `proceed_needed` outcome exists
   AND `latest_chat_state` filters content events — yet the continuation
   never fired.

**Why it happens.** `latest_chat_state` was reading "chat is done" off
`run_status.running == False`. But the server's `VISIBLE_EVENT_TYPES`
(`src/.../embedded/server/agent_chat_transcript.py:11-25`) **does not
include `run_status`**. The history API filters it out before returning, so
the harness never sees a `run_status` row in `items`. `running` stays at its
True default, and the proceed_needed guard never opens.

**Fix pointer.** `scripts/autoresearch/run.py:latest_chat_state` — derive
`running` from `assistant_message.payload.final`. When the latest
assistant_message has `final=True`, the chat agent has yielded back to the
operator and the harness must drive the next step. No reliance on
`run_status` (which is invisible to the API).

**Recurrence prevention.** Two-pronged: **(a)** the
`test_autoresearch_harness_contract.py` unit test (still TODO) should assert
both that `run_status` is **not** in `VISIBLE_EVENT_TYPES` AND that
`latest_chat_state` does not look for it; **(b)** any future broadening of
the API's visible types should not change harness behavior — derive chat
liveness from content events only.

---

## P9 — Sprint merge `git checkout main` overwrites untracked `.venv/` files

- **First seen:** 2026-05-23, cycle 10 (second-layer P6)
- **Wallclock to repro:** ~6 min; iteration completes with `status=crash`
- **Status:** Fixed

**Symptom.** All tasks done, gates partially pass, sprint merge attempted —
sprint_merge_error contains `"could not check out main: Updating the
following directories would lose untracked files in them: .venv/lib64"`
plus a long list of files under `.venv/bin/`, `.venv/lib/python3.12/...`.

This is *not* P6 — the `.venv/lib64` here is *untracked*, not `D`-state. The
P6 fix (untrack `.venv` from the index) removed the "tracked deleted"
problem but left the workspace `.venv/` directory as untracked files that
`git checkout main` refuses to overwrite.

**Evidence query.**

1. `sprints.verification_evidence` JSON `sprint_merge_error` matches
   `/Updating the following directories would lose untracked files.*\.venv/`.
2. Distinguished from P6 by: P6 says `tracked non-guidance changes` and
   shows `D <path>`; P9 says `Updating the following directories` and lists
   untracked files.

**Why it happens.** `git checkout main` (or any checkout) treats `.venv/`
files as untracked because the P6 fix removed them from the index. When
the target branch (`main`) has versions of those files (which it doesn't,
in our case — but git's safety check is conservative), or when the
checkout would touch directories containing untracked files, git aborts to
prevent data loss.

**Fix pointer.** `scripts/autoresearch/run.py:restore_seed` — extend the P6
fix: in addition to `git rm --cached`, also append `.venv/` to the
workspace's `.gitignore` (idempotent — check first), then commit the
`.gitignore` change. Ignored files don't trigger the "untracked overwrite"
check; subsequent checkouts succeed.

**Recurrence prevention.** The Builder-side fix lives in the seed: commit
`.venv/` into `.gitignore` at devpulse template capture time. Until that
lands, the skill-side workaround in `restore_seed` is the safety net.

---

## P10 — `/api/agent/chat/respond` returns 400 mid-iteration; iteration crashes

- **First seen:** 2026-05-23, cycle 10
- **Wallclock to repro:** ~7 min; iteration completes with `status=crash`
- **Status:** Fixed (defensive fallback)

**Symptom.** Long after the initial intake — typically after the first
sprint completes (or fails to ship) — the chat agent surfaces a new
`ask_user_question` or `tool_approval_request`. The harness's
`send_chat_respond` POST gets back HTTP 400 ("Select an option or provide
a custom answer"), `requests.HTTPError` bubbles up, the outer try/except
in `main()` writes `crash.log` and marks the iteration `decision_status=crash`.

**Evidence query.**

1. `evidence_dir/crash.log` contains `400 Client Error: Bad Request for url:
   .../api/agent/chat/respond`.
2. `builder_stdout_stderr.log` contains
   `POST /api/agent/chat/respond HTTP/1.1" 400 Bad Request` near the end.
3. The iteration TSV row has `notes=status=crash`.

**Why it happens.** The respond endpoint's handler (see
`src/.../embedded/server/routes/agent.py:1196-1227`) raises 400 if both
`selected_options` and `custom_text` strip to empty. The harness's
"recommended" path picks the option at `recommended_index`, but if the
question's `options` list is malformed (empty, or all options missing
`label`), the payload defaults to `custom_text="recommended"` — which
should *not* be empty, but observed instances suggest some questions arrive
with structure the harness's `send_chat_respond` can't satisfy. Could also
be `tool_approval_request` events whose contract differs from
`ask_user_question`.

**Fix pointer.** `scripts/autoresearch/run.py` `send_chat_respond` — now
handles `tool_approval_request` separately (sends `decision=allow`). The P10
`except 400` fallback now breaks the loop cleanly instead of calling
`send_chat` (which causes P11). See P11 for why `send_chat` fallback was wrong.

**Recurrence prevention.** Any new pending interaction type must be handled
inside `send_chat_respond` (not via `send_chat` fallback). The P10 catch is
a last-resort break, not an active recovery path.

---

## P11 — `send_chat` fallback on 400-respond causes 409 Conflict

- **First seen:** 2026-05-23, cycle 12 (N=5 baseline attempt)
- **Wallclock to repro:** ~26s; iteration completes with `status=crash`
- **Status:** Fixed (P11 fix in `send_chat_respond` + corrected P10 fallback)

**Symptom.** A `tool_approval_request` surfaces mid-iteration. The P10
fallback calls `send_chat("Continue with reasonable defaults.", session_id=...)`.
The server rejects with HTTP 409 "This chat session is waiting on the current
run." `requests.HTTPError` bubbles up; iteration `decision_status=crash`.

**Evidence query.**

1. `evidence_dir/crash.log` contains `409 Client Error: Conflict for url:
   .../api/agent/chat`.
2. `builder_stdout_stderr.log` contains `POST /api/agent/chat/respond HTTP/1.1"
   400 Bad Request` immediately followed by `POST /api/agent/chat HTTP/1.1"
   409 Conflict`.
3. The iteration TSV row has `notes=status=crash`, `wallclock_s` < 60s.

**Why it happens.** When `chat/respond` returns 400 (because
`send_chat_respond` built a `selected_options`/`custom_text` payload for a
`tool_approval_request` event that requires `decision=allow|deny`), the
session still has a reserved/running turn awaiting the respond answer. The P10
fallback then calls `send_chat()` which tries to start a NEW turn on the same
session — blocked with 409 by the `hub.reserve_run()` guard.

**Fix pointer.** `scripts/autoresearch/run.py` `send_chat_respond` — check
`pending_item["type"]`: if `"tool_approval_request"`, set `payload["decision"]
= "allow"` and `payload["reason"] = "autoresearch harness: auto-allow"`.
P10 except-400 fallback changed to `break` (incomplete, not crash) instead of
`send_chat` (which 409s on an active session).

**Recurrence prevention.** Never call `send_chat()` as a fallback when a
`chat/respond` fails — the session will have a live run reservation. Always
resolve pending interactions through `chat/respond` or let the loop break
cleanly. New interaction types → add a branch in `send_chat_respond` before
they reach production.

---

## P12 — `feature_correct` always False: wrong metrics key + missing deps + wrong cwd

- **First seen:** 2026-05-23, baseline attempt (post-P11)
- **Wallclock to repro:** every run; `feature_correct=False` in all TSV rows
- **Status:** Fixed (3 compounding issues resolved)

**Symptom.** `feature_correct=False` and `chunk_pressure_risk_false=False` on every shipped iteration despite builder's own testing gate passing.

**Evidence query.**

1. TSV column `feature_correct` = `False` for all rows.
2. TSV column `chunk_pressure_risk` = empty/null for all rows.
3. Manual `evaluate_hard_gates` against evidence: `chunk_pressure_risk_false: False`, `feature_correct: False`.

**Why it happens.** Three independent bugs compound:

1. **Wrong metrics key:** `evaluate_hard_gates` and `write_session_row` read `metrics.get("optimization")` but the builder metrics response uses `"optimization_summary"`. Result: `optimization = {}`, `chunk_pressure = {}`, `gate_chunk = False` always.
2. **Missing deps:** `run_feature_check` runs pytest without installing `requirements.txt` first. Seed `.venv` is minimal (no jinja2, httpx, etc). Collection fails with `ModuleNotFoundError`.
3. **Wrong cwd:** pytest invoked from repo cwd, not workspace. `app.main` mounts `StaticFiles(directory="app/static")` which resolves relative to cwd → `RuntimeError: Directory 'app/static' does not exist` at import time.
4. **Missing exclusion:** `test_github.py` async tests use `@pytest.mark.asyncio` but `pytest-asyncio` is not in `requirements.txt` — 3 tests fail every run.

**Fix pointer.** `scripts/autoresearch/run.py`:
- `evaluate_hard_gates` / `write_session_row`: use `metrics.get("optimization_summary") or metrics.get("optimization")`.
- `run_feature_check`: `pip install -q -r requirements.txt` before pytest; add `cwd=workspace` to pytest subprocess; add `--ignore-glob=*test_github*`.

**Recurrence prevention.** When adding new evidence captures that read `metrics.json`, verify the key path against a live `builder metrics show --json` response — the schema is `optimization_summary`, not `optimization`. Always run `run_feature_check` with `cwd=workspace` for any repo that mounts static files relative to cwd.

---

## P13 — `feature_correct` False: Builder's sprint fast-forward deletes `.venv` from workspace

- **First seen:** 2026-05-23, baseline attempt (post-P12)
- **Wallclock to repro:** every run; `feature_correct=False` in all TSV rows after P12 fix
- **Status:** Fixed

**Symptom.** `feature_correct=False` on shipped runs even after P12 fixes; `gate_pass_rate=0.8333` (5/6). PEP 668 error (`--break-system-packages` hint) visible in baseline stderr.

**Evidence query.**

1. TSV column `feature_correct` = `False` for shipped rows.
2. `gate_pass_rate=0.8333` (5/6), not 6/6.
3. Baseline stdout/stderr log contains: `"PEP 668"` or `"break-system-packages"` — pip tried the system Python.

**Why it happens.** Builder's task workspace at `/tmp/aab-workspaces/<task_id>` commits `.venv` deletions on the task branch (the code-gen creates a fresh venv there and the seed `.venv` shows as deleted). `workspace_integrated_fast_forward` merges those deletions into the sprint branch in the project workspace. When Builder checks out the sprint branch, git applies the `.venv` deletions to the project working tree (`/tmp/devpulse-<uuid>/.venv` disappears). By the time `run_feature_check` runs (after Builder is terminated), `venv_py.exists()` is `False` → falls back to `sys.executable` (system python3) → pip install blocked by PEP 668 → `CalledProcessError` caught → returns `False`.

**Fix pointer.** `scripts/autoresearch/run.py` `run_feature_check`:
- Before pip install, check `venv_py.exists()`; if missing, `subprocess.run([sys.executable, "-m", "venv", str(workspace / ".venv")], check=True)`.
- Remove the `else sys.executable` fallback; always use `str(venv_py)` after the venv-creation guard.

**Recurrence prevention.** Never rely on the seed `.venv` surviving the Builder run. The sprint fast-forward deletes it whenever the task branch was created from a commit that tracked `.venv` entries. Always ensure the workspace venv exists before pip/pytest; recreate it if it's gone.

---

## P14 — Direct 409 on `chat/respond`: pending item already auto-handled

- **First seen:** 2026-05-23, baseline A/run-4 (iter 5/5, 14 turns, 504s wallclock)
- **Wallclock to repro:** sporadic; depends on Builder auto-approving tool requests before harness polls
- **Status:** Fixed

**Symptom.** `status=crash`, `gate_pass_rate=0.6667` (4/6), `feature_correct=True`. `crash.log` contains: `HTTPError: 409 Client Error: Conflict for url: http://127.0.0.1:<port>/api/agent/chat/respond`.

**Evidence query.**

1. `crash.log` → `HTTPError: 409 … /api/agent/chat/respond` (not `send_chat`).
2. `feature_correct=True` (P13 fix held).
3. Wallclock short-to-medium; `operator_turns` 10–20.

**Why it happens.** The harness polls `get_pending_question()` and finds a `tool_approval_request` or `ask_user_question` item. Between the poll and the `send_chat_respond()` call, Builder auto-handles the pending event internally (auto-approve tool request, or a concurrent agent turn resolves it). By the time the harness POSTs to `/api/agent/chat/respond`, the session has no active pending question → 409 Conflict. The existing `except` block only catches status 400 (`break`) and re-raises all others, so 409 propagates as an uncaught `HTTPError` → `decision_status = "crash"`.

**Fix pointer.** `scripts/autoresearch/run.py` question-answering loop `except requests.HTTPError` block:
- Add `elif status_code == 409: continue` — re-enter the poll loop so `wait_for_question_or_ship` reassesses the session. Do NOT `break` (session is still running; `break` would prematurely call `ship_or_timeout`). Do NOT raise (not a fatal error).

**Recurrence prevention.** Any time `send_chat_respond` or `send_chat` can 409, `continue` (not `break`) is the correct recovery when the session is still active. 409 = "wrong moment to respond, poll again." Reserve `break` for 400 = "payload format rejected by the API contract."

---

## P15 — Composite formula reads wrong metrics key (composite=0 for every run)

- **First seen:** 2026-05-23, post-P12 fixture-A N=5 baseline closeout
- **Wallclock to repro:** appears across every baseline + iteration row in the TSV
- **Status:** Fixed

**Symptom.** Every baseline / iteration row in `docs/autoresearch/baseline_runs.tsv` and `optimize_results.tsv` has `composite=0` despite non-zero `noncached_plus_output_tokens` (column 9), non-zero `wallclock_s`, non-zero `operator_turns`. `baseline_runs_summary.json` shows `status=unstable, stable_runs=0` regardless of how many runs shipped at 6/6. `iterations.html` headline shows `mean=null, stdev=null, fixtures_stable=0`. `INTROSPECTION.md` says "No per-prompt rows yet" with 5+ real runs in the TSV.

**Evidence query.**

1. `baseline_runs.tsv` column 17 (composite) is `0` on rows where column 9 (noncached_plus_output_tokens) is non-zero.
2. `baseline_runs_summary.json` `status="unstable"` for every fixture with `stable_runs=0` but raw TSV has multiple `gates_passed="6/6"` rows.
3. `grep 'composite = int' scripts/autoresearch/run.py` shows `metrics.get("optimization")` instead of `metrics.get("optimization_summary")`.

**Why it happens.** P12 fixed `evaluate_hard_gates` to read `metrics["optimization_summary"]` (the actual response key) but missed the parallel composite-computation site in `run.py:main`. The wrong key returns empty `{}`, so `noncached_plus_output_tokens` resolves to `0`, the product is `0`, and `baseline.py:compute_summary` filters every row out via `if r.get("composite")` (falsy for 0).

**Fix pointer.** `scripts/autoresearch/run.py:main` composite calculation:
- Read `metrics["optimization_summary"]` first with fallback to `metrics["optimization"]` (mirrors P12).
- Composites in already-written TSV rows can be backfilled deterministically from each run's `metrics.json` without re-running.

**Recurrence prevention.** Any time the metrics-response schema is renamed, grep all references to the old key in the harness. Adding a `freshness_sweep.py` check that the composite-formula site references `optimization_summary` would catch this at lane closeout.

---

## P16 — Composite formula compounds correlated noise (CV >50%, 2σ-floor negative)

- **First seen:** 2026-05-23, fixture-A N=5 first end-to-end baseline
- **Wallclock to repro:** appears once σ-floor is computed from any non-tiny baseline
- **Status:** Fixed

**Symptom.** Even with composites correctly computed, `baseline_runs_summary.json` shows σ comparable to or larger than μ (CV >50%). `2σ-floor` is negative (μ − 2σ < 0), meaning any candidate beats the noise band — the σ-gate is useless. `iterations.html` fixture card displays the CV pill in red.

**Evidence query.**

1. `baseline_runs_summary.json` → for any fixture, `stdev` ≥ `mean / 2`.
2. `noise_floor_2sigma` is negative.
3. Examine raw TSV: the 3+ stable runs span an order of magnitude on `composite` despite all hitting `gates_passed="6/6"`.
4. `grep 'composite = ' scripts/autoresearch/run.py` shows a multiplicative form like `tokens × turns × wallclock`.

**Why it happens.** The three factors are correlated — a longer fixture run produces more tokens AND more operator turns AND more wallclock. Multiplying them compounds variance instead of averaging it. `operator_turns` and `wallclock_seconds` are not billed and measure "how long the conversation was," not "how efficient the agent was." With the fixture held constant across baseline + iteration runs, the only dimension that matters for cost comparison is tokens — exactly `noncached_plus_output_tokens`.

**Fix pointer.** `scripts/autoresearch/run.py:main`: `composite = int(opt.get("noncached_plus_output_tokens") or 0)`. Drop the `× turns × wallclock` factors. Also update the 6 doc sites: `OPTIMIZE.md`, `METRICS.md`, `README.md val_bpb` row, `iterations.html` methodology paragraph, `baseline.py` docstring.

**Recurrence prevention.** Future composite changes need to (a) declare independence of factors before multiplying; (b) measure post-change CV before declaring the formula sound. If σ/μ stays >30% after N=5, the formula is too noisy regardless of what it claims to measure.

---

## P17 — Fixture `feature_correct=False` on all runs while agent's own pytest passes (seed dep gap)

- **First seen:** 2026-05-23, fixture B N=4 baseline (sha=171cd69 + sha=dcd3fd3, all 4 runs)
- **Wallclock to repro:** appears on every run of a fixture whose code-gen produces tests with a runtime dep not in `requirements.txt`
- **Status:** Fixed (for pytest-asyncio specifically; general matcher recommended)

**Symptom.** A specific fixture (here B) has `feature_correct=False` on every baseline run across multiple shas. Other fixtures (A) pass `feature_correct=True` cleanly. Pre-build Builder side: `builder_stdout_stderr.log` shows the agent's own pytest invocation passing all dots (e.g., `python3 -m pytest -x -q ... [100%]`). Post-build harness side: `run_feature_check` returns False.

**Evidence query.**

1. `baseline_runs.tsv` fixture-X rows have `feature_correct=False` across ≥3 distinct run_ids and ≥2 distinct shas.
2. Other fixtures pass `feature_correct=True` on the same shas.
3. `grep '\[100%\]\|passed' /tmp/autoresearch/baseline-*/X/run-*/builder_stdout_stderr.log` shows the agent's own pytest passing.
4. Diff `pyproject.toml [project.optional-dependencies] dev` against `requirements.txt`. Look for anything required by `[tool.pytest.ini_options]` (e.g., `asyncio_mode = "auto"` ⇒ pytest-asyncio).
5. Sanity test: in a clean venv, `pip install -r <seed>/requirements.txt` then `cd <seed> && pytest tests -q --ignore-glob='*playwright*' --ignore-glob='*test_github*'`. Compare the passing-count before vs after adding the suspected dep. A jump (e.g., 107 → 139) confirms missing-plugin diagnosis.

**Why it happens.** Builder's code-gen agent runs tests in its own `/tmp/aab-workspaces/<task_id>` workspace with whatever deps it pip-installs ad-hoc — its pytest succeeds. After sprint fast-forward, Builder shuts down and the harness runs `run_feature_check` against the project workspace's clean `.venv`, which it rebuilds from `requirements.txt` only. Any test-suite dep declared in `pyproject.toml [optional-dependencies] dev` but missing from `requirements.txt` is absent in the harness's check. Tests that need it (async tests need pytest-asyncio when `asyncio_mode = "auto"`; tests with markers like `@pytest.mark.timeout` need pytest-timeout) silently fail collection → exit code ≠ 0 → `feature_correct=False`.

The fixture pattern matters: fixture A "button shows current time" generates sync tests, no plugin needed. Fixture B "notes feature with persistence" generates `httpx.AsyncClient + async def test_*` (the natural FastAPI persistence test pattern), which needs pytest-asyncio.

**Fix pointer.** Add the missing dep to the seed's upstream `requirements.txt` (e.g., `pytest-asyncio>=0.23.0`), re-capture seed via `scripts/autoresearch/setup_seed.sh`, truncate poisoned baseline rows, document drift in `docs/autoresearch/baseline_variance.md § Seed drift`. Do NOT patch the harness to install dev-deps — that hides future seed defects.

**Recurrence prevention.** Whenever the seed's `pyproject.toml` lists a pytest plugin or runtime dep in `[project.optional-dependencies] dev`, audit `requirements.txt` for the same line. If a `[tool.pytest.ini_options]` directive (asyncio_mode, timeout, etc.) requires a plugin, that plugin belongs in `requirements.txt` not `dev`. A `freshness_sweep.py` check that lists declared-but-missing pytest plugins would catch this at lane closeout.

---

## Pattern entry template

```markdown
## PN — <short name>

- **First seen:** YYYY-MM-DD, cycle N
- **Wallclock to repro:** ~N min
- **Status:** Fixed | Open | Partial

**Symptom.** <what the operator notices first>

**Evidence query.**

1. <specific, narrow predicate that only this pattern matches>
2. <ideally derivable from a STUCK dump without re-running>
...

**Why it happens.** <root cause, one paragraph>

**Fix pointer.** <file:function and one-line summary of the change>

**Recurrence prevention.** <CI test / lint rule / "none" if behavioral>
```
