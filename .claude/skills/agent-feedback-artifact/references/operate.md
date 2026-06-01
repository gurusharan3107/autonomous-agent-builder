# agent-feedback-artifact — Operate

Step-by-step run procedure. Loaded on demand from SKILL.md.

## Operating sequence
```
preflight → add widget → serve → arm/heal wake → process markers → disarm Monitor → closeout (+ optimize)
```
**Args:** file scripts take `--root <serve-root>` (else default to `cwd/data/` — wrong queue); mutating CLIs (`dispatch`, `mark`) take `--port` (default 4177). Same serve-root you passed to the server.

### 1. Preflight
`node scripts/agent-feedback-preflight.mjs <artifact.html> --port <port>` → widget state, port availability, queue path, webhook config.

### 2. Add widget
- **Static:** `node scripts/add-agent-feedback.mjs <artifact.html>` — injects `AGENT_FEEDBACK_WIDGET_START..END` before `</body>` (idempotent).
- **Running-app (hermes-chrome):** no file edit — operator toggles Feedback Mode in the extension popup; the service worker injects the widget. See the `hermes-chrome` skill.

### 3. Serve
`node scripts/artifact-feedback-server.mjs <serve-root> <port>` (port default 4177). Serves static files (static mode) + queue API (`/api/feedback/*`) + SSE (`/api/feedback/events`). Running-app mode uses it as a **queue-only sidecar** (app stays on its own port; widget posts cross-origin; CORS built in).
- Default `4177` matches the extension widget default → running-app works with no config. Non-default port → set the popup "Queue origin" to match or markers post to a dead origin.
- Queue file lives at `<serve-root>/data/`, keyed by serve-root **not** port — changing port keeps the same queue + Monitor.

### 4. Arm/heal wake
Push-only `fs.watch` on queue.json, zero polling. Arm (Claude Code):
```
Monitor({ description:"agent-feedback markers from <slug>", persistent:true,
  command:"node <skill-dir>/scripts/agent-feedback-watch.mjs --root <serve-root>" })
```
`<skill-dir>` = this skill's actual install path (absolute). **A project-local
`.claude/skills/agent-feedback-artifact` overrides the global
`~/.claude/skills/agent-feedback-artifact`** — use the one you were invoked from;
a hardcoded `~/.claude/...` fails with `MODULE_NOT_FOUND` when the skill is repo-local.
Each marker → one line `{id, markerId, route, status, url, origin, artifactTitle, artifactPath, summary, visibleText, sentAt, createdAt, emittedAt}`. `origin`+`visibleText` let you act directly (localhost+clear → act; external+clear question → answer from URL; `visibleText` disambiguates deictic phrases). Any harness: `agent-feedback-watch.mjs --root <root> | <adapter>`. Hermes: webhook path → [`wake-bridge.md`](wake-bridge.md).

**Self-heal — the push path can die silently** (Monitor auto-stop / orphaned watcher; marker stays `queued` but never wakes you, and an absent operator won't tell you). At session entry / each (re)invocation / on suspicion:
```
node scripts/agent-feedback-wake-status.mjs --root <serve-root>
```
Verdict from two signals: undelivered-backlog age (`queued` older than `--backlog-stale-sec`, default 90s = wake didn't deliver — strongest, catches the orphaned-watcher case) + heartbeat freshness (`data/.wake-heartbeat`, written every `AGENT_FEEDBACK_HEARTBEAT_MS`, default 30s). `rearm_required` (exit 1) → `pkill -f agent-feedback-watch.mjs`, then re-arm the Monitor (it backfills the queued backlog). Residual: a fully-idle queue with a dead Monitor isn't detectable until a new marker ages in — the entry re-check is the backstop.

### 5. Annotate (operator)
- **Static:** open the **served** URL `http://localhost:<port>/<file>` (explicit filename, not `/` → `EISDIR`). **Never `file://`** — posts to a dead `file://` base; marker dropped ("Send failed").
- **Running-app:** open the app's own URL with the extension; toggle Feedback Mode. Widget posts to the sidecar (default `http://localhost:4177` or popup override) — confirm it's reachable.

Placement: `.af-launcher` (reveal toolbar) → `[data-af-toggle]` (arm, `aria-pressed=true`) → click target (marker at click point via `elementAtPoint`, which masks widget nodes) → type `[data-af-popover-input]` → `.af-popover-send`. After send the popover closes and **Annotate auto-disarms** — re-click to place another.
Inspect a marker: click `.af-marker` → popover (Agent tab) → gear `[data-af-config]` → UI tab shows live element style (+ Primary-text row for inherited-color containers). Popover re-anchors on expand/collapse.

### 5b. Agent-driven verification (hermes-chrome bridge)
1. **Re-check state first.** `.af-launcher` is a toggle (re-click hides) — never blind-double-click. `[data-af-toggle]` `aria-pressed` resets after each Send/re-toggle. `evaluate {toolbarOpen, pressed}`; open/arm only as needed. DOM state persists across bridge calls — tests aren't isolated.
2. **Batch a task's actions in one `bridge({type:"run",...})`** (avoids cross-call popover collapse) — but the popover opens async after placement (see 6).
3. **`click_selector` over `cursor_move+click`** for small targets (hit-tests the resolved element, not the topmost SVG icon).
4. **Verify change on the actual styled element**, not the marker selector (color may be on an inherited child): `getComputedStyle(child).color`.
5. **Never `cursor_hide` or park the cursor off-screen** — end batches at meaningful targets; cursor position is operator feedback.
6. **Wait for the popover before fill:** `{"type":"wait_for_selector","selector":"[data-af-popover-input]"}` between the placement click and `fill`. A tight place+fill+send drops the marker silently (`success:true`, no marker).
7. **`success:true` ≠ marker created — assert the queue grew** (next.mjs / count before-vs-after / Monitor wake). The bridge reports click success, not marker creation.
8. **`success:false` is ambiguous** (widget-reject — `.af-popover-send` isn't disabled on empty input, just no-ops — vs collapsed-popover). Disambiguate via DOM (`popoverInput`/`markerCount`) + queue; don't infer from the code.

### 6. Process queue
Wake payload `{id, route, summary, …}` is usually enough (skip-details/batching/reload rules → [`best-practices.md`](best-practices.md)).

**Claim → run → terminal:** `dispatch --claim` (leases to `processing`) → run per `dispatch` field — **inline** for `no_worker_main_agent_direct`, **background Task subagent** (`run_in_background`, prompt = `workerPrompt`) for worker routes (concurrent for multiple; cap concurrency; serialize write-scope per file). **Every claimed marker ends `done`/`blocked`** — subagent error → `mark blocked <error>`; ambiguity → `mark blocked <what you need>` (never `AskUserQuestion` — operator may be away). Work > lease TTL → heartbeat `mark <id> processing "…"`. Dead worker → reclaim sweep requeues/blocks (`AGENT_FEEDBACK_MAX_ATTEMPTS`). Full rules: SKILL.md "Per-marker action".

Scripts (mutating = HTTP client `--port`; read-only = file `--root`):
- `dispatch.mjs --claim [--port]` — claim+lease next; returns item + `workerPrompt` + `dispatch`
- `next.mjs --root` — peek next queued (read-only)
- `details.mjs <id> --root` — full payload, on demand (read-only)
- `mark.mjs <id> done "reply" [--reload|--reload-full] [--port]` — close with reply

### 7. Disarm Monitor
`TaskStop` the Monitor handle (the agent owns the task id).

### 8. Closeout (+ optimize)
`node scripts/agent-feedback-closeout.mjs <artifact.html> --port <port>` → read-only report: widget state, server listening, queue counts, webhook, `agentReminders` (TaskStop + stop-server), `optimize` block. Act on the reminders — stop the server if still listening. **Optimize step:** read `verdict`/`signalNotes`, self-introspect on the session; if `verdict` is `signals_to_review` or introspection finds a real recurring issue, load [`optimize.md`](optimize.md) → "Optimize step". Obvious clean case → change nothing.

---

## Script inventory

| Script | Purpose |
|---|---|
| `add-agent-feedback.mjs <artifact.html>` | Inject widget before `</body>` |
| `remove-agent-feedback.mjs <artifact.html>` | Remove managed block (roundtrip-safe) |
| `artifact-feedback-server.mjs <serve-root> <port>` | Static serving + `/api/feedback/*` + SSE + queue + reclaim sweep |
| `agent-feedback-preflight.mjs <artifact.html> --port <port>` | Readiness checks |
| `agent-feedback-closeout.mjs <artifact.html> --port <port>` | Read-only state report + agentReminders + `optimize` triage block |
| `agent-feedback-next.mjs --root <root>` | Next queued item (read-only) |
| `agent-feedback-details.mjs <id> --root <root>` | Full marker payload (read-only) |
| `agent-feedback-mark.mjs <id> <status> [reply] [--reload\|--reload-full] [--port <port>]` | Update status + reply (HTTP client; server applies terminal guard + lease) |
| `agent-feedback-dispatch.mjs --claim [--port <port>]` | Claim + lease next queued (HTTP client); returns item + `workerPrompt` + `dispatch` |
| `agent-feedback-routing.mjs` | Route classifier + `reclaimExpired` supervisor logic (library) |
| `feedback-client.mjs` | Shared HTTP helper for the mutating CLIs (library) |
| `agent-feedback-watch.mjs --root <root>` | Push-only wake; fs.watch on queue.json, one line per new queued marker; writes `data/.wake-heartbeat` |
| `agent-feedback-wake-status.mjs --root <root>` | Self-healing wake check: `ok`/`backlog_fresh`/`rearm_required` from backlog age + heartbeat (exit 1 on rearm) |

---

## Closeout report shape

`agent-feedback-closeout.mjs` returns JSON with:
- `widgetInstalled` — `AGENT_FEEDBACK_WIDGET_START..END` present in the artifact
- `server.listening` — TCP listen check on the port
- `webhook.configured` / `.url` / `.signingConfigured`
- `queue.path` / `.totalForArtifact` / `.counts` (queued/processing/done/blocked/canceled)
- `cleanupCommands` — copy-paste hints for `removeCapability` + `clearLocalQueue`
- `agentReminders.taskStopMonitor` (always) / `.stopServer` (only when still listening)
- `optimize` — `verdict` (`state_clean_no_action_indicated` | `signals_to_review`), `selfIntrospect`, `signals`, `wake`, `signalNotes` (candidates to judge), `next` (load `optimize.md` → "Optimize step" when warranted). Triage steps/questions live in `optimize.md`, not the report.
