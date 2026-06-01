# agent-feedback-artifact — Operate

Full step-by-step procedure for setting up and running the feedback loop.
Loaded on demand from SKILL.md.

---

## Operating sequence

```
preflight → add widget (mode-specific) → serve → arm Monitor → process markers → disarm Monitor → closeout
```

**Critical args for queue/watch scripts:** always pass `--root <serve-root>`. Without it, scripts default to `process.cwd()/data/` and fail silently or read the wrong queue. Use the same path you passed to `artifact-feedback-server.mjs`.

### 1. Preflight

```bash
node scripts/agent-feedback-preflight.mjs <artifact.html> --port <port>
```

Reports readiness: widget-injection state, server port availability, queue path, webhook config.

### 2. Add widget (delivery-mode-specific)

**Static artifact mode:**
```bash
node scripts/add-agent-feedback.mjs <artifact.html>
```
Injects an `AGENT_FEEDBACK_WIDGET_START..END` block before `</body>`. Idempotent.

**Running-app mode (hermes-chrome):**
No file edit. The operator toggles `Feedback Mode` in the hermes-chrome extension popup. The extension's service worker injects the widget content script into the target tab. See the `hermes-chrome` skill for popup setup.

### 3. Serve

```bash
node scripts/artifact-feedback-server.mjs <serve-root> <port>   # <port> defaults to 4177
```

Serves static files from `<serve-root>` (static-artifact mode) AND exposes the queue API (`/api/feedback/*`) + SSE endpoint (`/api/feedback/events`). Running-app mode uses this server **only as the queue sidecar** — the running app stays on its own port, and the widget posts cross-origin to this sidecar (CORS is built in).

- **Default port is `4177`** — the extension widget also defaults to `http://localhost:4177`, so leaving both at the default makes running-app mode work with no config. If you choose another port here, set the popup "Queue origin" to match, or markers post to a dead origin.
- The queue file lives under `<serve-root>/data/`, keyed by serve-root, **not** by port — so changing the port keeps the same queue + Monitor.

### 4. Arm Monitor (wake)

Push-only event source — kernel `fs.watch` on `queue.json`. Zero polling.

**Claude Code (default):**
```
Monitor({
  description: "agent-feedback markers from <slug>",
  persistent: true,
  command: "node ~/.claude/skills/agent-feedback-artifact/scripts/agent-feedback-watch.mjs --root <serve-root>"
})
```
Each new marker prints one JSON line — `{id, markerId, route, status, url, origin, artifactTitle, artifactPath, summary, visibleText, sentAt, createdAt, emittedAt}` (~400–460 chars). Surfaces as a chat notification. `origin` and `visibleText` let you decide directly: `origin=localhost` + clear summary → act; `origin=external` + clear question → answer from URL alone; `visibleText` disambiguates deictic phrases.

**Any harness:** `node agent-feedback-watch.mjs --root <serve-root> | <your wake adapter>`. Same line stream, pipe to whatever your harness consumes.

**Self-healing wake check (the push path can die silently).** The harness may auto-stop a Monitor that emitted too many events; the watcher can be orphaned (process alive, Monitor dead). The marker stays durably `queued` but never wakes you — and an absent operator won't tell you. So **at session entry, on `/agent-feedback-artifact` (re)invocation, and whenever you suspect staleness, run:**
```
node scripts/agent-feedback-wake-status.mjs --root <serve-root>
```
It reports `verdict` from two signals: undelivered-backlog age (a `queued` marker older than `--backlog-stale-sec`, default 90s, means the wake did NOT deliver — the strongest signal, catches the orphaned-watcher case) and watcher-heartbeat freshness (`data/.wake-heartbeat`). On `verdict: rearm_required` (exit 1), **heal it**: `pkill -f agent-feedback-watch.mjs`, then arm a fresh persistent Monitor on the watch command above — the new watcher backfills every `queued` marker so the backlog is delivered. The watcher writes its heartbeat every `AGENT_FEEDBACK_HEARTBEAT_MS` (default 30s). Residual limit: a fully-idle queue with a silently-dead Monitor isn't detectable until a new marker ages into the backlog signal — so the session-entry re-check is the backstop.

**Hermes alt:** keep the existing webhook path (`AGENT_FEEDBACK_WEBHOOK_URL`) — orthogonal to the watcher; both can coexist. See [`wake-bridge.md`](wake-bridge.md).

### 5. Annotate (browser, operator side)

For static-artifact: open the **served** URL `http://localhost:<port>/<file>` (use the explicit filename like `index.html`, NOT just `/` — processing scripts resolve artifact path from `location.pathname` and bare `/` causes `EISDIR` errors). **Never open the `file://` path** — a `file://` page posts to a `file://` base, no server is listening, and every marker is silently dropped ("Send failed").

For running-app: open the running app's own URL in Chrome with the hermes-chrome extension; toggle Feedback Mode. The widget posts to the queue sidecar at its queue origin (default `http://localhost:4177`, or the popup "Queue origin" override). Confirm the sidecar from step 3 is reachable at that origin.

**Marker placement loop (operator):**
1. Click `.af-launcher` (top-right toggle) → reveals toolbar
2. Click `[data-af-toggle]` (Annotate button) → `aria-pressed=true`, layer becomes `pointer-events: auto`
3. Click target element on the page → marker created at click point via `elementAtPoint` (which masks widget nodes during hit-test)
4. Type into `[data-af-popover-input]`
5. Click `.af-popover-send`

After send: popover closes, **Annotate auto-disarms** (`setArmed(false)`). To place another marker, click Annotate again. This is intentional — prevents accidental double-placement.

**Inspecting an existing marker (operator):**
1. Click the marker badge (`.af-marker`) on the page → popover opens collapsed, Agent tab active
2. Click the gear (`[data-af-config]`) → popover expands, Agent + UI tabs visible
3. Click UI tab → shows live-resampled element style; if the marker is on a container whose own color is inherited, a **Primary text** row surfaces the most prominent text-bearing child's color + font

Popover re-anchors automatically on expand/collapse so it stays attached to the marker even near viewport edges.

### 5b. Agent-driven verification (bridge mode)

When an agent drives this flow through hermes-chrome (for self-test or regression check), these rules avoid wasting turns on bridge-automation quirks and keep the cursor presence operator-visible:

1. **Re-check toolbar + Annotate state at the start of every flow.** `.af-launcher` is a *toggle* — clicking it when the toolbar is already open HIDES it; never blind-double-click it. `[data-af-toggle]` `aria-pressed` resets to `false` after each Send and on Feedback Mode re-toggle. `evaluate` `{toolbarOpen, pressed}` first; open the toolbar only if closed, and click Annotate only if `pressed === "false"`. DOM state (toolbar/armed/pending popover) persists between bridge calls — tests are NOT isolated; assume leftover state.
2. **Batch related actions in ONE `bridge({type:"run", actions:[...]})` call** to avoid the cross-call idle gap where the popover collapses back to compact (call-1 place, call-2 read → `width: 0`). BUT within that batch the popover opens **asynchronously** after the placement click — see rule 6.
3. **Use `click_selector` over `cursor_move + cursor_click` for small targets.** The high-level click auto-handles cursor activation and re-tries hit-test against the resolved element rather than the topmost (which can be an SVG icon inside a button — the click still works via bubbling, but the high-level helper is more reliable).
4. **Verify visible change via computed style on the actual styled element**, not the marker selector. The marker may be placed on a container whose color is inherited; the change is on a child. Read `getComputedStyle(child).color`, not `getComputedStyle(container).color`.
5. **Cursor presence is operator feedback — never park the cursor at an edge or off-screen.** The cursor sits at the last action coordinate, so end batched sequences at meaningful targets (the marker, the value just changed, the popover gear). Never call `cursor_hide`. Don't move to viewport corners. The operator infers "agent is working / agent finished here" from where the cursor stopped — make that location informative.
6. **Wait for the popover before filling — a tight place+fill+send batch silently drops the marker.** After the target click the popover renders async; if `fill`/send run immediately, the send finds no unsent message → **no marker is created, yet the batch returns `success:true`**. Insert `{"type":"wait_for_selector","selector":"[data-af-popover-input]"}` between the placement click and the `fill`. (Observed: the 5-action launcher→toggle→click→fill→send batch produced zero markers with `success:true`; splitting placement from fill+send fixed it.)
7. **`success:true` ≠ marker created. ALWAYS assert the queue actually grew** after a send (`agent-feedback-next.mjs` / read `data/feedback-queue.json` count before vs after, or wait for the Monitor wake). The bridge reports click success, not marker creation — never declare a send verified from `success` alone.
8. **`success:false` on the send click is ambiguous** — it can mean the widget rejected the input (e.g. empty comment: `.af-popover-send` is NOT disabled on empty input, the send just no-ops) OR the bridge click failed on a collapsed popover. Disambiguate by probing the DOM (`popoverInput` present? `markerCount`?) and the queue — do not infer the cause from the result code.

Marker is created with `pendingComment`, committed to queue on send.

### 6. Process queue

When a Monitor wake notification arrives, the wake payload (`{id, route, summary, …}`) is usually enough to act on. Best-practice rules (skip-details, batching, reload flag choice) are in [`best-practices.md`](best-practices.md).

**Claim → run → terminal.** Claim the marker (`dispatch --claim`), which leases it to `processing`. Then run per its `dispatch` field — **inline** for `no_worker_main_agent_direct`, a **background Task subagent** (`Agent`, `run_in_background:true`, prompt = the item's `workerPrompt`) for worker routes; dispatch multiple queued worker markers concurrently (cap concurrency; serialize write-scope per file). **Every claimed marker must end `done`/`blocked`** — on subagent error, `mark blocked` with the error; on ambiguity, `mark blocked` with what you need (never `AskUserQuestion` — the operator may be away). For subagent work exceeding the lease TTL, heartbeat with `mark <id> processing "still working: …"`. If a worker dies, the server's reclaim sweep requeues the marker (or blocks it after `AGENT_FEEDBACK_MAX_ATTEMPTS`), so nothing is silently orphaned. Full rules: SKILL.md "Per-marker action".

The processing scripts (mutating CLIs are HTTP clients of the server — pass `--port`, default `4177`; read-only `next`/`details` stay file-based and accept `--root`):
- `node scripts/agent-feedback-dispatch.mjs --claim [--port <port>]` — claim + lease the next queued item; returns it merged with `workerPrompt` + `dispatch`
- `node scripts/agent-feedback-next.mjs --root <serve-root>` — peek at the next queued item (read-only)
- `node scripts/agent-feedback-details.mjs <id> --root <serve-root>` — full marker payload (selector, rect, ui, etc.) — pull only when needed (read-only)
- `node scripts/agent-feedback-mark.mjs <id> done "reply" [--reload | --reload-full] [--port <port>]` — close the marker with an agent reply

### 7. Disarm Monitor

At closeout: `TaskStop` the Monitor handle. The agent owns the task ID.

### 8. Closeout

```bash
node scripts/agent-feedback-closeout.mjs <artifact.html> --port <port>
```

Report includes: widget state, server listening state, queue counts, webhook config, plus an `agentReminders` block (TaskStop reminder, stop-server hint).

---

## Script inventory

| Script | Purpose |
|---|---|
| `add-agent-feedback.mjs <artifact.html>` | Inject widget before `</body>` |
| `remove-agent-feedback.mjs <artifact.html>` | Remove managed block (roundtrip-safe) |
| `artifact-feedback-server.mjs <serve-root> <port>` | Static serving + `/api/feedback/*` + SSE + queue |
| `agent-feedback-preflight.mjs <artifact.html> --port <port>` | Readiness checks |
| `agent-feedback-closeout.mjs <artifact.html> --port <port>` | Read-only state report + agentReminders |
| `agent-feedback-next.mjs --root <root>` | Next queued item |
| `agent-feedback-details.mjs <id> --root <root>` | Full marker payload |
| `agent-feedback-mark.mjs <id> <status> [reply] [--reload\|--reload-full] [--port <port>]` | Update status + agent reply (HTTP client; server applies terminal guard + lease). `--reload` → CSS hot-swap; `--reload-full` → full page reload |
| `agent-feedback-dispatch.mjs --claim [--port <port>]` | Claim + lease the next queued item (HTTP client); returns it merged with `workerPrompt` + `dispatch` |
| `agent-feedback-routing.mjs` | Route classifier + `reclaimExpired` supervisor logic (library; see `best-practices.md`) |
| `feedback-client.mjs` | Shared HTTP helper for the mutating CLIs (library) |
| `agent-feedback-watch.mjs --root <root>` | Push-only wake source. fs.watch on queue.json, one JSON line per new queued marker |

---

## Closeout report shape

`agent-feedback-closeout.mjs` returns JSON with:
- `widgetInstalled`: whether `AGENT_FEEDBACK_WIDGET_START..END` block is in the artifact
- `server.listening`: TCP listen check on the port
- `webhook.configured` / `webhook.url` / `webhook.signingConfigured`
- `queue.path` / `queue.totalForArtifact` / `queue.counts` (queued/processing/done/blocked/canceled)
- `cleanupCommands`: copy-paste hints for `removeCapability` and `clearLocalQueue`
- `agentReminders.taskStopMonitor`: always present — reminds the agent to stop the Monitor it armed in step 4
- `agentReminders.stopServer`: present only when the server is still listening — instructions to kill it
