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

## P10 — `/api/agent/chat/respond` returns 400; iteration crashes

- **First seen:** 2026-05-23, cycle 10
- **Status:** Fixed (defensive break)

**Symptom.** `crash.log` contains `400 Client Error: Bad Request for url: .../api/agent/chat/respond`. TSV row `status=crash`.

**Evidence.** `crash.log` 400 + builder_stdout_stderr.log shows `POST /api/agent/chat/respond HTTP/1.1" 400` near the end.

**Why.** Respond handler (`src/.../embedded/server/routes/agent.py:1196-1227`) raises 400 when `selected_options` + `custom_text` both strip to empty, or payload doesn't match the event's contract (e.g., `selected_options` sent for a `tool_approval_request`).

**Fix.** `run.py:send_chat_respond` — branch by `pending_item["type"]` (see P11). 400 fallback `break`s cleanly instead of `send_chat`-ing (which causes P11).

**Prevention.** New pending-interaction types must branch inside `send_chat_respond`. The 400 catch is last-resort, not active recovery.

---

## P11 — `send_chat` fallback on 400-respond causes 409 Conflict

- **First seen:** 2026-05-23, cycle 12
- **Status:** Fixed

**Symptom.** `crash.log` 409 + builder_stdout shows `POST .../respond" 400` immediately followed by `POST .../chat" 409`. Wallclock < 60s.

**Why.** `chat/respond` 400 left session with a live reserved run; P10's old `send_chat()` fallback tried to start a NEW turn → 409 from `hub.reserve_run()`.

**Fix.** `run.py:send_chat_respond` — branch by `pending_item["type"]`: `tool_approval_request` → `decision=allow`+`reason=...`; `ask_user_question` → `selected_options` or non-empty `custom_text` fallback. P10's 400 handler now `break`s (incomplete, not crash).

**Prevention.** Never `send_chat()` as a fallback when `chat/respond` fails — session has a live reservation. Resolve via `chat/respond` or break cleanly.

---

## P12 — `feature_correct` always False: wrong metrics key + missing deps + wrong cwd

- **First seen:** 2026-05-23, post-P11
- **Status:** Fixed (3 compounding bugs)

**Symptom.** `feature_correct=False` + `chunk_pressure_risk` empty on every shipped row despite Builder's own pytest passing.

**Why.** Three compounding:
1. `evaluate_hard_gates` + `write_session_row` read `metrics["optimization"]` but schema is `"optimization_summary"` → `chunk_pressure={}` → `gate_chunk=False` always.
2. `run_feature_check` ran pytest without `pip install -r requirements.txt` first — seed `.venv` is minimal (no jinja2/httpx) → collection `ModuleNotFoundError`.
3. pytest cwd was repo, not workspace — `app.main` mounts `StaticFiles(directory="app/static")` relative to cwd → `RuntimeError` at import.
4. `test_github.py` uses `@pytest.mark.asyncio` but `pytest-asyncio` not in `requirements.txt`.

**Fix.** `run.py`:
- `evaluate_hard_gates` / `write_session_row`: `metrics.get("optimization_summary") or metrics.get("optimization")`.
- `run_feature_check`: pip-install `requirements.txt` before pytest; `cwd=workspace`; `--ignore-glob=*test_github*`.

**Prevention.** Verify metrics-key paths against live `builder metrics show --json`. `run_feature_check` must use `cwd=workspace` for any repo mounting static files relative to cwd.

---

## P13 — `feature_correct` False: sprint fast-forward deletes `.venv` from workspace

- **First seen:** 2026-05-23, post-P12
- **Status:** Fixed

**Symptom.** Post-P12, `feature_correct=False` persists on shipped runs (`gate_pass_rate=0.8333`, 5/6). Baseline stderr shows `PEP 668` / `break-system-packages`.

**Why.** Task workspace `/tmp/aab-workspaces/<task_id>` commits `.venv` deletions on the task branch (code-gen creates its own venv there; seed `.venv` shows deleted). `workspace_integrated_fast_forward` merges those into the sprint branch; project workspace `git checkout` then deletes `/tmp/devpulse-<uuid>/.venv`. By `run_feature_check` time, `venv_py` missing → fell back to `sys.executable` (system python3) → PEP 668 → `CalledProcessError` → `False`.

**Fix.** `run.py:run_feature_check` — if `venv_py.exists()` is False, `python3 -m venv .venv` first. Always use `str(venv_py)` (no `sys.executable` fallback).

**Prevention.** Never rely on the seed `.venv` surviving the Builder run.

---

## P14 — Direct 409 on `chat/respond`: pending item already auto-handled

- **First seen:** 2026-05-23, baseline A/run-4
- **Status:** Fixed

**Symptom.** `crash.log` 409 on `/api/agent/chat/respond` (no prior 400). `feature_correct=True` (P13 held). Wallclock short-to-medium.

**Why.** Between `get_pending_question` poll and `send_chat_respond` POST, Builder auto-handles the pending event (auto-approve tool, concurrent turn resolves it). Session no longer has a pending question → 409. Existing `except` only caught 400 → 409 re-raised → `decision_status=crash`.

**Fix.** `run.py:825-839` `except requests.HTTPError` — add `elif status_code == 409: continue`. NOT `break` (session still running; would prematurely call `ship_or_timeout`).

**Prevention.** 409 = "wrong moment to respond, poll again" (continue). 400 = "payload rejected" (break). Never raise either.

---

## P15 — Composite formula reads wrong metrics key (composite=0 for every run)

- **First seen:** 2026-05-23, post-P12
- **Status:** Fixed

**Symptom.** TSV `composite=0` despite non-zero `noncached_plus_output_tokens` on 6/6 rows. `baseline_runs_summary.json` stays `unstable/stable_runs=0`; `iterations.html` headline `mean=null`.

**Evidence.** TSV col 17 = 0 where col 9 > 0; `grep 'composite = int' run.py` shows `metrics.get("optimization")`.

**Why.** P12 patched `evaluate_hard_gates` to `optimization_summary` but missed the parallel composite site at `run.py:870`. `baseline.py:compute_summary` filters via `if r.get("composite")` → falsy for 0 → empty stable_runs.

**Fix.** `run.py:870` — `metrics.get("optimization_summary") or metrics.get("optimization")` (mirrors P12). Backfill existing rows from each `metrics.json` (no re-run).

**Prevention.** Grep all metrics-key references when the schema is renamed. A `freshness_sweep` link between composite site and canonical key would auto-catch this.

---

## P16 — Composite formula compounds correlated noise (CV >50%, 2σ-floor negative)

- **First seen:** 2026-05-23, fixture-A N=5
- **Status:** Fixed

**Symptom.** Composites correctly computed but `stdev ≥ mean/2`, `noise_floor_2sigma < 0` → any candidate beats the band, σ-gate useless. iterations.html fixture CV pill red.

**Evidence.** Stable runs span an order of magnitude on `composite` while all 6/6. `grep 'composite = ' run.py` shows multiplicative form `tokens × turns × wallclock`.

**Why.** Three factors are correlated — a longer fixture run produces more of each. Multiplying compounds variance instead of averaging it. `operator_turns` + `wallclock_seconds` aren't billed; they measure conversation length, not efficiency. Fixture held constant ⇒ only `noncached_plus_output_tokens` matters for cost comparison.

**Fix.** `run.py:870` — `composite = int(opt.get("noncached_plus_output_tokens") or 0)`. Drop the `× turns × wallclock`. Update 6 doc sites: `OPTIMIZE.md`, `METRICS.md`, `README.md val_bpb`, `iterations.html` methodology, `baseline.py` docstring.

**Prevention.** New composite formulas: declare factor independence before multiplying; measure CV post-change. σ/μ > 30% after N=5 ⇒ formula too noisy.

---

## P17 — Fixture `feature_correct=False` on all runs while agent's pytest passes (seed dep gap)

- **First seen:** 2026-05-23, fixture B N=4 across 2 shas
- **Status:** Fixed (pytest-asyncio specifically; general matcher recommended)

**Symptom.** One fixture's runs all show `feature_correct=False` across multiple shas; other fixtures pass. `builder_stdout_stderr.log` shows the agent's own pytest passing inside its `/tmp/aab-workspaces/<task_id>` venv.

**Evidence.**
1. ≥3 fixture-X rows `feature_correct=False`, other fixtures `True` on same shas.
2. `grep '\[100%\]' /tmp/.../X/run-*/builder_stdout_stderr.log` — agent's pytest passed.
3. Diff seed `pyproject.toml [optional-dependencies] dev` vs `requirements.txt`. Anything required by `[tool.pytest.ini_options]` (e.g., `asyncio_mode="auto"` ⇒ pytest-asyncio) MUST be in `requirements.txt`.
4. Sanity: clean venv + `pip install -r <seed>/requirements.txt` + harness pytest invocation. Passing-count jump after adding the suspected dep confirms (107 → 139 was the pytest-asyncio signal).

**Why.** Builder's code-gen agent installs deps ad-hoc in its task workspace. After sprint FF, harness runs `run_feature_check` against project workspace's clean `.venv` rebuilt from `requirements.txt` only. Test-suite deps in `dev` but not `requirements.txt` → tests fail collection silently → exit ≠ 0. Fixture B's "notes with persistence" naturally generates `httpx.AsyncClient + async def test_*` which needs pytest-asyncio; fixture A's sync tests don't.

**Fix.** Add missing dep to upstream `~/Builder-Workspace/devpulse/requirements.txt`, re-capture seed via `setup_seed.sh`, truncate poisoned baseline rows, document drift in `baseline_variance.md § Seed drift`. Do NOT patch the harness to install dev-deps — hides future seed defects.

**Prevention.** When seed's `pyproject.toml [tool.pytest.ini_options]` declares a directive (asyncio_mode, timeout, etc), its plugin belongs in `requirements.txt`, not `[optional-dependencies] dev`. A `freshness_sweep` check listing declared-but-missing pytest plugins would auto-catch this.

---

## P22 — code-gen Sonnet API latency exceeds watchdog idle threshold (api_latency)

- **First seen:** 2026-05-24, fixture A iter 1/5, second full baseline attempt
- **Wallclock to repro:** Fires whenever Sonnet's first or inter-turn response time exceeds `--idle-seconds` (was 180s; fixed to 600s)
- **Status:** Catalogued + matcher added + harness fix applied (2026-05-24)

**Symptom.** Watchdog fires at ~190s (`idle_seconds ≈ 180–300`). Builder log has `agent_phase_start agent=code-gen` (Sonnet model, `effort=high`) but no `agent_phase_complete agent=code-gen`. Optionally: some `mcp__workspace__list_directory` / `mcp__workspace__run_command` calls appear (code-gen made a partial turn) and then stop — the agent was mid-turn waiting for Sonnet's second response. `STUCK_DETECTED.json.idle_seconds ≈ 190`. Not a Builder bug; the watchdog threshold was shorter than Sonnet's observed API latency.

**Evidence query.**

1. `STUCK_DETECTED.json.idle_seconds` in range 120–360.
2. `STUCK_DETECTED.json.reason != "wall_clock_budget_exceeded"` (real watchdog dump, not synthetic).
3. `agent=code-gen` in `builder_stdout_stderr.log`.
4. No `agent_phase_complete agent=code-gen` in builder log.
5. Optional: `mcp__workspace__list_directory` or `mcp__workspace__run_command` in log (code-gen made ≥1 tool call before second LLM response timed out).

**Why it happens.** `baseline.py` spawns `hang_watchdog.py --idle-seconds 180`. Sonnet's first-turn response to a large implementation prompt (12k+ token context) takes ~120s; the second-turn response after 5 workspace reads takes >180s. The watchdog sees 190s of no WAL writes and fires, triggering SIGTERM to the builder. The iter aborts as `watchdog_dump_detected`. The builder and code-gen agent were healthy; only the harness threshold was wrong.

**Fix pointer.** Harness calibration only: `baseline.py:_spawn_hang_watchdog` — increase `--idle-seconds` from `180` to `600`. This gives Sonnet up to 10 min to respond while still catching true infinite hangs (DB lock loops, port deadlocks, etc.) well within the 1500s per-iter timeout. Landed 2026-05-24.

**Prevention.** If P22 fires again after the 600s fix, check for concurrent builder instances on ports 9876–9877 consuming API quota or bandwidth. Consider reducing the code-gen agent's initial context (e.g., fewer KB articles in the system prompt) to reduce Sonnet's processing time.

---

## P21 — Builder graceful-shutdown hook flood after wall-clock SIGTERM (budget_exhausted)

- **First seen:** 2026-05-24, fixture A iter 1/5 first full baseline
- **Wallclock to repro:** Fires whenever an iter exceeds `DEFAULT_ITER_WALL_CLOCK_SECONDS=1800`
- **Status:** Catalogued + matcher added (2026-05-24). Underlying cause may be P18b DB lock in `dispatch_background_error`.

**Symptom.** Iter aborts via `wall_clock_budget_exceeded`. Builder log ends with 100+ `Error in hook callback hook_N: ... error: Stream closed` or `error: Tool permission stream closed before response received`. Immediately preceded by `INFO: Shutting down` / `INFO: Waiting for background tasks to complete`. No watchdog dump (Builder was actively writing, watchdog never fired). Earlier in the same log: `dispatch_background_error database is locked` for multiple tasks.

**Evidence query.**

1. `STUCK_DETECTED.reason == "wall_clock_budget_exceeded"` (or synthesized by baseline.py).
2. `INFO:     Shutting down` in `builder_stdout_stderr.log`.
3. ≥5 `Error in hook callback hook_` + `error: Stream closed` (or `Tool permission stream closed`) in builder log — always come **after** the shutdown line.
4. Optional P18b precursor: `dispatch_background_error` + `database is locked` earlier in the same log.

**Why it happens.** `baseline.py` sends `SIGTERM` to the Builder server when the 1800s iter budget expires. Uvicorn begins graceful shutdown and awaits in-flight background tasks (Claude Code CLI agent subprocesses). Those subprocesses have pending hook permission requests; the hook server's stdin/stdout pipe closes on shutdown, so every pending `sendRequest` call throws `Error("Stream closed")`. Each `Error in hook callback` is logged but not fatal — it's normal graceful-shutdown behavior. The builder log floods with these errors while uvicorn waits. The iter ran long because tasks failed and restarted (P18b DB lock), or the fixture task is genuinely complex for a 30-minute budget.

**Fix pointer.** Not a Builder source bug. Two contributing factors: (1) **P18b** — `dispatch_background_error` DB lock at `src/autonomous_agent_builder/api/routes/dispatch.py:_run_dispatch_step` line ~197 (`await db.commit()`). The outermost dispatch commit is not retry-wrapped like P18's `persist_realtime_run_update`. Fix: add `OperationalError("database is locked")` retry loop in `_run_dispatch_step`, same exponential-backoff pattern as P18. (2) If P18b fixed and iter still times out, increase `DEFAULT_ITER_WALL_CLOCK_SECONDS` in `scripts/autoresearch/baseline.py` (e.g., to 2700s for fixtures with multi-task sprints).

**Prevention.** The matcher now fires reliably on this pattern (baseline.py writes synthetic STUCK_DETECTED.json, matcher checks for shutdown + hook flood). P18b DB lock retry would eliminate the task-failure restart cascade that inflates iter time.

---

## P20 — Orchestrator infinite recovery loop / agent livelock (persistent)

- **First seen:** 2026-05-24, A1 sanity baseline after P18+P19 source fixes landed
- **Status:** Catalogued; source fix needed in `orchestrator.py` recovery-loop budget
- **Category:** `persistent` — auto-retry won't help; needs follow-up dispatch cap

**Symptom.** Distinct from P18/P19 silent-hang class — Builder is *actively writing* the DB (watchdog correctly does NOT fire). Iter aborts via `wall_clock_budget_exceeded` after ~30 min. Builder log shows 5+ short `agent_phase_complete agent=chat` events back-to-back with `stop_reason=end_turn`, interspersed with `hook_blocked_bash` warnings. Multiple `embedded_dispatch_followup_selected followup_task_id=<X>` for the same X. Phase transitions bounce (planning → implementation → quality_gates → back to planning → …) without converging to `done`. ~$0.5–2 burned per iter on recovery-chat churn.

**Evidence.**
1. `STUCK_DETECTED.reason == "wall_clock_budget_exceeded"` (key — distinguishes from P18/P19).
2. `grep -c "agent_phase_complete\s\+agent=chat" <evidence>/builder_stdout_stderr.log` ≥ 5.
3. Counter of `embedded_dispatch_followup_selected followup_task_id=X` shows ≥ 2 for the same X.
4. ≥1 `hook_blocked_bash` warning (chat agent kept trying blocked operations).
5. Often: `Control request timeout: initialize` OR `agent_unexpected_error` somewhere in the log (the failure that triggered the recovery cascade).

**Why.** When a Builder agent fails (SDK timeout, hook block, unrecoverable error), the orchestrator's recovery dispatches another chat agent to figure out what to do — but that agent has no way to actually unblock the underlying issue. It ends with `stop_reason=end_turn` (no useful action) and the orchestrator dispatches yet another chat. Infinite chat→chat recovery loop bounded only by wall-clock budget. Same root-cause family as P18 (no fail-fast in Builder's state machine) but on the recovery path instead of the lifecycle event path.

**Fix (HARNESS — autonomy classification).** `diagnose_hang.py:match_p20_orchestrator_livelock` matches with confidence 0.9 when all 5 evidence predicates fire (0.7 with subset). Reads `evidence_dir/builder_stdout_stderr.log` directly because wall-clock-aborted iters don't have a watchdog dump.

**Fix (BUILDER SOURCE — persistent prevention).** `src/autonomous_agent_builder/orchestrator/orchestrator.py` — bound follow-up chat dispatch per task. Recommended: track `recovery_attempts` on Task model; cap at 3; transition task to `BLOCKED` after cap with operator-required decision. Mirrors P18's fail-fast principle.

Investigate the root cause of each recovery cascade too — the SDK `Control request timeout: initialize` deserves its own typed-retry policy (ROADMAP M2.6).

**Prevention.** Once the source fix lands, autoresearch iters that hit recovery-loop scenarios will fail fast at ~10s × 3 attempts = 30s instead of grinding for 30 min. Catalog matcher remains as defense-in-depth.

---

## P19 — Builder hangs after `tool_not_found_in_registry` (persistent contract drift)

- **First seen:** 2026-05-24, A1 sanity baseline after P18 source fix
- **Status:** Catalogued + source-fixed; 3 missing schemas (`AskUserQuestion`, `mcp__builder__task_recover`, `mcp__builder__workspace_scaffold`) added to `_SDK_BUILTINS`
- **Category:** `persistent` — auto-retry won't help; needs schema fix or prompt-list cleanup

**Symptom.** Builder's chat agent's allowed_tools list references tools that don't exist in `_SDK_BUILTINS` or `custom_tools`. At registry build time, `tool_registry.py` logs `tool_not_found_in_registry` warning and **drops the tool silently**, building with fewer tools than declared. But the agent's prompt template *instructs the model* to call those exact tools by name (e.g., "use `AskUserQuestion` for bounded decisions"). The model either emits text instead of tool_use (lifecycle waits for a tool result that never arrives) OR a chat→chat transition triggers a fresh registry build that drops the same tools again, and Builder polls `/api/dashboard/board` forever.

**Evidence.**
1. `grep "tool_not_found_in_registry" <evidence>/builder_stdout_stderr.log` returns one or more lines.
2. Last `agent_phase_complete` had `stop_reason=tool_use` (model wanted to invoke a tool).
3. `tool_registry_built tool_count=N` shows a count less than the agent's declared `allowed_tools` length.
4. WAL mtime stale ≥180s after the warnings (watchdog fires).

**Why.** Contract drift. Three sources need to agree:
- `agents/definitions.py` agent `allowed_tools` list
- `agents/tool_registry.py` `_SDK_BUILTINS` dict
- The agent's prompt template (which names tools the model should call)

When any one drifts, the others silently degrade. `tool_registry.py:79` logs but doesn't fail-build, and there's no test that asserts every declared `allowed_tool` has a matching schema.

**Fix (SOURCE — persistent prevention).** Add the missing schemas to `_SDK_BUILTINS` so the registry can include them. Implementation locations for the tool functions themselves typically exist already (`routes/agent.py`, `routes/tasks.py`); the schema is the contract that must match.

**Fix (HARNESS — autonomy classification).** `diagnose_hang.py:match_p19_tool_not_found_hang` extracts the dropped tool names from the warning and surfaces them in the `fix_pointer`. Category `persistent` means baseline.py emits `SELF_HEAL_ESCALATION` rather than retrying (no point retrying — same registry build, same drop).

**Prevention.** Add a unit test that walks every agent in `definitions.py`, builds its registry, and asserts `len(registry.tools) == len(agent.allowed_tools)` — i.e., zero drops. That test would catch contract drift before any baseline iter runs.

---

## P18 — Builder hangs on `database is locked` during agent_run lifecycle flush (transient)

- **First seen:** 2026-05-24, A1 sanity baseline after substrate-identity contract landed
- **Status:** Catalogued + auto-retry; persistent Builder source fix tracked under ROADMAP M2.6 (IMP-010 class)
- **Category:** `transient` — auto-retry is the autonomous remediation

**Symptom.** Builder's agent completes its work successfully (tests pass, code shipped) but the lifecycle hangs in the active phase. `lane_status` reports the iter as 0/N complete with no progress for ≥3 minutes. `builder_stdout_stderr.log` shows the agent's `agent_phase_complete` event landed, then the next event-flush errored with `sqlite3.OperationalError: database is locked`, then Builder polls `/api/dashboard/board` forever without transitioning.

**Evidence.**
1. `grep -c "database is locked" <evidence_dir>/builder_stdout_stderr.log` ≥ 2.
2. `agent_run_lifecycle_flush_error` event in the log immediately after the lock error.
3. Offending SQL is `INSERT INTO agent_run_events`.
4. Process threads idle on `do_epoll_wait` or `futex_wait` (Builder waiting, not retrying).
5. WAL mtime stale ≥ 180s after the lock (hang_watchdog fires).

**Why.** SQLAlchemy session autoflush during `agent_run_events` INSERT races with another writer on the same SQLite WAL. The first writer holds the write lock; the second writer's autoflush raises `OperationalError`; the lifecycle's exception handler logs the flush error but doesn't unwind the phase. Builder's state machine waits for a transition event that can't be written. Same root-cause family as IMP-010 (session rollback during long agent runs) but on a different write path. Builder doesn't fail-fast; it polls forever.

**Fix (HARNESS — transient retry).** `diagnose_hang.py:match_p18_db_lock_transient` matches the signature with confidence 0.95. `baseline.py`'s stuck-iter handler routes `category=transient` to `kill + retry on fresh /tmp/devpulse-<uuid>/` (one retry beyond `MAX_HEAL_ATTEMPTS`). Most runs succeed on retry because the lock contention is non-deterministic. No operator intervention.

**Fix (BUILDER SOURCE — persistent prevention).** Wrap `agent_run_events` INSERT in `session.no_autoflush:` block at `src/autonomous_agent_builder/orchestrator/agent_run_lifecycle.py` (or wherever `agent_run_events` is populated). Alternative: queue events to a single-writer background thread so concurrent agents never contend on the same SQLite connection. Track under ROADMAP M2.6 typed-retry refinement.

**Prevention.** (1) Source patch above eliminates the race. (2) Watchdog + auto-retry catches it in the wild even if the source bug recurs in a future code path. (3) Builder should fail-fast on unhandled flush errors instead of polling — add a phase-level deadline so any phase that doesn't transition within N seconds aborts the task with explicit `STUCK` status visible to harness.

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
