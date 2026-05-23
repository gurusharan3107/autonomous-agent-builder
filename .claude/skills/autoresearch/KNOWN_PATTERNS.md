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

**Fix pointer.** `scripts/autoresearch/run.py` main loop — wrap
`send_chat_respond` in a try/except that catches `requests.HTTPError` with
status 400 and falls back to `send_chat("Continue with reasonable
defaults.", session_id=session_id)`. The iteration progresses to shipped
even if a specific structured question can't be answered, and we capture
the verdict cleanly. Iterations affected by this path may still fail
feature gates (gate_pass_rate < 1.0), but the run isn't lost.

**Recurrence prevention.** Better long-term fix: extend
`send_chat_respond` to handle `tool_approval_request` properly (the
`decision: allow|deny` payload) and add option-list validation before
sending. Catalog the actual 400-producing payloads as they accumulate.

---

## P11 — Reserved

Next pattern slot. When a new hang class is diagnosed, add it here and update
the diagnoser. Keep `unknown` matches rare.

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
