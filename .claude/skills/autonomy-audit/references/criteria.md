# Autonomy criteria — 13 narrow predicates

Source of truth for `scripts/audit.py`. The script consults this catalog; **the two must stay in sync** — if you add C14, you must add a matcher to `audit.py:CHECKS` in the same commit.

Each criterion below is one section. Sections follow a fixed structure:

- **What it is** — one sentence operator-facing
- **Why** — the autoresearch failure mode this prevents (P-pattern from `.claude/skills/autoresearch/KNOWN_PATTERNS.md`)
- **Static predicate** — what the auditor greps / reads / AST-parses
- **Dynamic predicate** *(optional)* — what the auditor observes after `--dynamic` launches the target briefly
- **Verdict scale** — what counts as `pass` / `partial` / `fail` / `unknown`
- **fix_pointer template** — emitted by the audit when the criterion fails

If any of these fields would be vibes-only ("yes if it looks like X"), the criterion is not yet ready to be a predicate — open an Optimize-lane ticket against this skill instead of papering over.

---

## C1 — Observability-first watchdog

- **What it is.** Target has a process or external monitor that detects when its main loop has gone idle (no progress signal for N seconds) AND fires a callback / SIGTERM / notification on detection.
- **Why.** Autoresearch P-original: cycle 1 sat 47 minutes on a silent hang because nothing watched for progress. Detection within minutes is the precondition for every other autonomy property — without it, cycle time degenerates to operator polling.
- **Static predicate.**
  - File matching `*watchdog*`, `*monitor*`, `*supervisor*`, OR `*heartbeat*` in target source tree, OR
  - Target's main loop contains a `signal.alarm`, `asyncio.wait_for(...)`, `subprocess.TimeoutExpired` handling, or equivalent timeout with idle detection.
  - Bonus pass: the threshold is *configurable* via flag / env / config file (grep for `--idle`, `IDLE_SECONDS`, `timeout` parameters).
- **Dynamic predicate.** Launch the target with a deliberately stuck input (or external SIGSTOP for 30s if launching isn't safe); confirm the watchdog fires a log line or process termination within configured threshold ± 10%.
- **Verdict scale.**
  - `pass`: file + configurable threshold + dynamic check confirms detection
  - `partial`: file present but threshold hardcoded OR dynamic check skipped/inconclusive
  - `fail`: no watchdog file AND no in-loop timeout handling
  - `unknown`: source unreadable
- **fix_pointer template.** "Add a `<target-path>/scripts/watchdog.<ext>` that watches the main loop's progress signal (e.g., DB mtime, log mtime, output file growth) and fires on idle > configurable threshold. See `.claude/skills/autoresearch/scripts/hang_watchdog.py` for a worked example."

## C2 — Preserved forensics on failure

- **What it is.** When the target fails (crash, timeout, watchdog fire), state is *copied* to a persisted directory — not just logged. Re-running is not the diagnostic path.
- **Why.** Autoresearch P4 cycle 4: workspace was `rm -rf`'d before grabbing the DB → lost the deadlock evidence and had to repro from scratch. Subsequent cycles copied `agent_builder.db` + threads + sockets + py-spy.
- **Static predicate.**
  - Watchdog / failure path copies (`shutil.copy`, `cp -a`, `tar`, `git stash`, `pg_dump`, etc.) target state to a directory outside the workspace, OR
  - Failure handler writes structured dump (JSON / SQLite / proc snapshot) to a configurable `--dump-root`.
- **Verdict scale.**
  - `pass`: file copy path present + `--dump-root` (or equivalent) configurable + at least 3 distinct artifact types captured (logs / DB / process state / network state)
  - `partial`: only 1–2 artifact types OR hardcoded dump location
  - `fail`: failure path emits only stdout / a single log file
  - `unknown`: failure path not identifiable in source
- **fix_pointer template.** "Extend the watchdog / failure handler to copy DB/state files + process introspection (threads, open FDs, sockets) + structured metadata JSON to `<dump-root>/<UTC>-<run-id>/`. Pattern: `.claude/skills/autoresearch/scripts/hang_watchdog.py:dump_diagnostics`."

## C3 — Pattern catalog as data structure (not prose)

- **What it is.** Known failure patterns live in a machine-readable file (or rows in a table) that an automated matcher consults — not a human-only doc.
- **Why.** Autoresearch lesson: prose docs ("known issues to watch for") never transfer between sessions. Only machine-readable catalogs compound. `KNOWN_PATTERNS.md` works *only* because `diagnose_hang.py` matches against it programmatically.
- **Static predicate.**
  - Target has a `KNOWN_PATTERNS.md` / `patterns.json` / `signatures.yaml` / `issues.toml` (or similar) AND
  - A script in target source consumes that catalog (grep for filename references inside `*.py`, `*.ts`, `*.sh`, etc.).
- **Verdict scale.**
  - `pass`: catalog file + script that reads it + matchers are predicates not vibes (heuristic: each entry has at least one regex / SQL / FD check, not just description)
  - `partial`: catalog file exists but no script reads it (it's just docs)
  - `fail`: no catalog file, OR file exists but is pure prose
  - `unknown`: target is too small for a catalog to be meaningful (single-file scripts, <100 LOC)
- **fix_pointer template.** "Create `<target>/KNOWN_PATTERNS.md` with one section per known failure mode, each containing a narrow predicate (regex / SQL / file check). Add a matcher script that consults it (pattern: `.claude/skills/autoresearch/scripts/diagnose_hang.py`). Sync catalog ↔ matcher in the same commit."

## C4 — `unknown` is a valid verdict (learning trigger)

- **What it is.** The target's matchers / classifiers / decisions explicitly distinguish "confidently matched X" from "I have no idea." The "no idea" case triggers human-level diagnosis AND a catalog update.
- **Why.** Without an explicit `unknown` signal, the system either silently misclassifies (calcifies wrong fixes) or repeats known fixes blindly. Autoresearch P5 hit this when the first fix was incomplete — only the cycle 6 `unknown` verdict forced re-reading the source.
- **Static predicate.**
  - Matcher script returns a verdict enum that includes `unknown` (or `None`, `null`, `inconclusive`, `low_confidence` — any explicit "I don't know") AND
  - The `unknown` path has documented operator action (escalate, log, add to catalog).
- **Verdict scale.**
  - `pass`: matcher returns `unknown` AND there's documentation pointing to what to do on unknown
  - `partial`: matcher returns `unknown` but no documented next step
  - `fail`: matcher returns only pass/fail or always returns something even when uncertain (no abstention)
  - `unknown`: no matcher exists (target hasn't built C3 yet)
- **fix_pointer template.** "Add explicit `unknown` verdict to the matcher when no pattern fires above confidence threshold (0.5 typical). Document operator action: 'add a new entry to KNOWN_PATTERNS + new matcher to the script before closing the Fix lane.'"

## C5 — Narrow detection predicates (discrimination)

- **What it is.** Two different failure modes never match the same predicate. Catalog entries are narrow enough to discriminate.
- **Why.** Autoresearch P5 / P6 / P9 all manifested as "sprint blocked" but each had a different root cause + different fix. Generic "sprint failed" predicate would mislabel them.
- **Static predicate.** For each pair of catalog entries `(Pi, Pj)`, simulate matching them against the test fixtures of the OTHER entry — if predicate is satisfied by the other entry's evidence, the predicate is too coarse. Audit script may approximate this by checking that predicates use *multiple* AND-conjoined conditions, not single broad strings.
- **Verdict scale.**
  - `pass`: every matcher uses ≥2 AND-joined conditions OR a specific regex/substring (not a generic keyword); no two matchers in the catalog have identical evidence queries
  - `partial`: some matchers are narrow, some are too broad (single-keyword)
  - `fail`: catalog matchers are mostly single-keyword OR none of them discriminate
  - `unknown`: catalog is too small to evaluate discrimination
- **fix_pointer template.** "Audit each catalog matcher: would entry Pj's evidence also trigger entry Pi's matcher? If yes, tighten the regex (add AND-joined conditions, narrower substring, structural check). See P5 vs P6 vs P9 in `.claude/skills/autoresearch/KNOWN_PATTERNS.md` for the canonical 'narrow enough' bar."

## C6 — Cost-bounded cycles (explicit budgets)

- **What it is.** The target has explicit budgets on time, cost (USD if applicable), and iteration count. No "let it run until done" loops.
- **Why.** Without ceilings, even a working autonomous loop can burn unbounded resources. Autoresearch's `--max-iterations` + `--cost-budget-usd` + watchdog idle threshold + SIGINT are non-negotiable.
- **Static predicate.**
  - Target's main entrypoint exposes (CLI flag, config, or constructor arg) at least 2 of: `max-iterations`, `cost-budget`, `timeout`, `max-tokens`, `max-cycles` AND
  - The loop body checks these on each iteration (not just at start).
- **Verdict scale.**
  - `pass`: ≥2 of (iteration cap, time cap, cost cap) checked each cycle, each configurable
  - `partial`: only 1 budget OR caps exist but not checked each cycle
  - `fail`: loop has no budget enforcement, OR runs to "completion" without ceilings
  - `unknown`: target isn't a loop (single-shot script)
- **fix_pointer template.** "Add `--max-iterations`, `--cost-budget-usd` (or equivalent), and a per-cycle wallclock budget to the loop entrypoint. Check them at the top of each iteration; raise / break when exceeded. Pattern: `scripts/autoresearch/loop.py`'s stop conditions."

## C7 — Fixes propagate to surfaces future agents read

- **What it is.** When the target's loop discovers a bug + fix, the fix is recorded in a place the *next* invocation of the loop (or a different agent) will read — not just patched locally.
- **Why.** Loops whose learnings stay in chat context have zero compounding value. Autoresearch's Fix lane closeout (ROADMAP + STATUS + CHANGELOG + KNOWN_PATTERNS + matcher) is what makes each cycle's fix permanent.
- **Static predicate.**
  - Target's docs / repo includes structured surfaces an agent reads (ROADMAP.md, CHANGELOG.md, KNOWN_PATTERNS.md, STATUS.md, decision log) AND
  - The fix workflow has a documented step that writes to those surfaces (look for "closeout", "post-fix", "update CHANGELOG" in target docs / runbooks).
- **Verdict scale.**
  - `pass`: ≥3 durable surfaces present + documented closeout step that writes to them
  - `partial`: surfaces exist but no documented write-on-fix step OR vice versa
  - `fail`: no durable post-fix surfaces (only chat context, only code comments)
  - `unknown`: target is single-script and propagation isn't applicable
- **fix_pointer template.** "Create or extend post-fix closeout: ROADMAP tick + STATUS Recent Decisions entry + CHANGELOG row + catalog entry (if C3 satisfied) — all in the same commit. See `docs/goal/FIX-STANDARD.md` § Closeout for the worked checklist."

## C8 — State, not conversation (durable persistence)

- **What it is.** All durable state (config, history, catalog, intermediate results) lives in files / DB / external store — not in conversation context, in-memory caches, or session variables.
- **Why.** Conversation-state autonomy is a contradiction. If `diagnose_hang.py` needed to remember the last 10 sessions to work, it wouldn't work in a fresh shell. Files are the durability boundary.
- **Static predicate.**
  - Target persists configuration to files (not just env vars or CLI flags) AND
  - Catalog / decisions / learnings (if any from C3 / C4) live in files, not in code constants AND
  - The target can be invoked cold (no prior session context) and behave identically.
- **Verdict scale.**
  - `pass`: all of the above + a "cold start" smoke test exists OR is trivially demonstrable
  - `partial`: persists most state but some critical config is hardcoded or env-only
  - `fail`: state lives in chat history, code constants, or runtime-only caches
  - `unknown`: target is stateless (no durable state needed) — typically `pass` by triviality
- **fix_pointer template.** "Move ephemeral state to files: catalog → `<target>/KNOWN_PATTERNS.md`, decisions → `<target>/decisions.json`, config → `<target>/config.toml`. Smoke-test cold start by running the target from a fresh shell with no environment context."

## C9 — Honest failure (no optimistic guessing)

- **What it is.** When the target encounters something it doesn't understand, it logs / reports the uncertainty *honestly* — not with a confident wrong answer.
- **Why.** Tightly related to C4. Autoresearch P5's first fix was incomplete; the matcher correctly returned P5 again in cycle 6 because the predicate matched the symptom — but the *suggested fix* was the cycle-5 one, which was wrong. Honest matchers say "P5 symptom present but if cycle-5 fix is in source, look at P6 too."
- **Static predicate.**
  - Catalog matchers (from C3) include a confidence score (or any numeric uncertainty signal) AND
  - Fix pointers reference downstream/alternative patterns when the same symptom could indicate >1 root cause (cascading pointer pattern).
- **Verdict scale.**
  - `pass`: matchers emit confidence + fix pointers cascade to alternatives when applicable
  - `partial`: confidence present but no cascading pointers, OR vice versa
  - `fail`: matchers report binary verdict without uncertainty; fix pointers are always single
  - `unknown`: target has no matchers (C3 unsatisfied)
- **fix_pointer template.** "Add confidence scores [0.0, 1.0] to each matcher. For matchers whose symptom could indicate >1 root cause, cascade the fix_pointer to alternatives (see `.claude/skills/autoresearch/scripts/diagnose_hang.py:match_p2_free_text_scoping`'s P2→P7→P8 cascade)."

## C10 — Safe-to-fail at every layer

- **What it is.** Failures are bounded, reversible, and don't accumulate cruft that pollutes the next cycle.
- **Why.** Autoresearch ran 11 cycles in one session because each failure was cheap: watchdog SIGTERMs, baseline.py marks `status=crash`, workspace gets cleaned, next cycle starts fresh. Without this, the loop's failure modes compound instead of bound.
- **Static predicate.**
  - Target uses git (or similar versioning) to bound edits to a branch / worktree AND
  - Cleanup logic in failure paths (`finally:` blocks, `trap` handlers, `defer`-equivalent) removes ephemeral state (`/tmp/...`, processes, temp DBs) AND
  - The cleanup is idempotent (running it twice doesn't crash).
- **Verdict scale.**
  - `pass`: versioned edits + cleanup in finally/trap + idempotent
  - `partial`: 2 of 3 conditions
  - `fail`: failures leave processes alive, temp dirs unremoved, or modify protected paths
  - `unknown`: failure paths not identifiable
- **fix_pointer template.** "Wrap mutating operations in transactions (DB) or branches (git). Add `finally:` / `trap` cleanup of every resource the loop creates (processes, temp dirs, port allocations). Test idempotency: run cleanup twice in a row — should succeed both times."

## C11 — LLM-as-diagnoser fallback (Gap-1)

- **What it is.** When the deterministic matcher (C3) returns `unknown`, the target can fall through to an LLM call that diagnoses against the same dump artifacts — and the result is *appended to the catalog*, not just used once.
- **Why.** Without this, every `unknown` requires a human. Static matchers cover known patterns; LLM fallback covers novel ones.
- **Static predicate.**
  - Target has a code path that, on matcher `unknown`, invokes an LLM (subprocess to `claude` / `codex` / API call) with the dump as context AND
  - The LLM's response is parsed back into the same `{id, verdict, evidence, fix_pointer}` shape AND
  - The result is persisted (e.g., suggested catalog entry written to a staging file for operator review).
- **Verdict scale.**
  - `pass`: full path exists + result persisted for review
  - `partial`: LLM fallback exists but result isn't persisted
  - `fail`: no LLM fallback; `unknown` requires manual handling every time
  - `unknown`: target is small enough that LLM fallback isn't needed (rare)
- **fix_pointer template.** "Add an `unknown` → LLM-fallback path. On matcher abstention, build a prompt from the dump artifacts, call the LLM with bounded context + cost cap (criterion C6), parse the response into the catalog schema, write to `<target>/proposed_patterns/<UTC>.json` for operator review."

## C12 — Auto-apply governance for high-confidence pattern fixes (Gap-2)

- **What it is.** When the matcher returns a known pattern with confidence ≥ threshold AND the fix is a mechanical edit (regex substitution, constant rename, flag flip), the target *applies it* without prompting. Lower-confidence or larger-scope fixes escalate to operator.
- **Why.** Without auto-apply, every cycle requires operator intervention even on patterns we've fixed 50 times. Today's autoresearch session didn't reach this level — I applied each fix by hand. C12 is the next leverage point.
- **Static predicate.**
  - Catalog entries (C3) tag fixes with an `auto_apply_safe` boolean or risk class AND
  - Target has a code path that, on high-confidence pattern + safe fix, applies the edit + commits + re-runs the cycle without prompting AND
  - Threshold + safe-class allowlist are configurable (criterion C6).
- **Verdict scale.**
  - `pass`: all of the above
  - `partial`: tags + threshold exist but no auto-apply code path
  - `fail`: every fix requires manual operator action
  - `unknown`: target has no catalog (C3 unsatisfied) or only one pattern (too few to govern)
- **fix_pointer template.** "Add `auto_apply_safe: bool` to each catalog entry. Add a code path that, on `confidence >= 0.9 AND auto_apply_safe`, applies the fix (e.g., a known regex substitution), commits with `auto-fix(<pattern-id>):` message, and re-runs the cycle. Bound by a `--max-auto-fixes` budget (C6)."

## C13 — Meta-orchestrator with escalation policy (Gap-3)

- **What it is.** A top-level loop owns `while cycle_fails: detect → diagnose → fix → rerun → if same-pattern-twice: escalate`. The operator isn't in the per-cycle critical path.
- **Why.** Without this, the autonomous loop is "autonomous-per-cycle but operator-driven across cycles." Same-pattern-twice escalation prevents applying the same wrong fix repeatedly.
- **Static predicate.**
  - Target has a meta-loop entrypoint (e.g., `meta_loop.py`, `auto_runner.sh`) that calls into the per-cycle entrypoint repeatedly AND
  - Meta-loop tracks `failure_attempts.json` (or equivalent) keyed by pattern_id AND
  - Meta-loop has an explicit escalation policy (e.g., `if attempts[pattern_id] >= 2: alert_operator()`) AND
  - All of C6 (budgets) applied at the meta-loop level.
- **Verdict scale.**
  - `pass`: all of the above
  - `partial`: meta-loop exists but no escalation OR no failure ledger
  - `fail`: no meta-loop; operator drives each cycle
  - `unknown`: target is single-shot by design (not a loop)
- **fix_pointer template.** "Build `<target>/meta_loop.py` that drives the per-cycle loop with: per-cycle budget enforcement (C6), failure-attempt ledger keyed by pattern_id, escalation on same-pattern-twice (alert operator, halt loop), cost cap across all cycles. See the 'Gap to full autonomy' section in commit `6fa9f90`'s CHANGELOG for the design sketch."

---

## Adding a new criterion (C14+)

When auditing a new target surfaces a real autonomy failure mode that doesn't fit C1–C13:

1. Open `create-skill` Optimize lane against `autonomy-audit`.
2. Add a new section to this file using the template structure above. Each predicate must be machine-checkable.
3. Add the matching function to `scripts/audit.py:CHECKS` in the same commit.
4. Run `scripts/validate.sh` — must exit 0.
5. Update `SKILL.md` description if the new criterion changes the skill's scope.

Hard Rule 1 binds: criteria are predicates. If the new failure mode can't be reduced to a checkable predicate, it's vibes — encode the failure as a `KNOWN_PATTERNS` entry in the target's own catalog (criterion C3 of the target) instead of expanding this skill.
