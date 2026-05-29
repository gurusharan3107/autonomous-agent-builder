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
node scripts/artifact-feedback-server.mjs <serve-root> <port>
```

Serves static files from `<serve-root>` (static-artifact mode) AND exposes the queue API (`/api/feedback/*`) + SSE endpoint (`/api/feedback/events`). Running-app mode uses this server for queue + API; the running app stays on its own port.

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
Each new marker prints one JSON line `{id, route, summary, sentAt, createdAt, emittedAt}` (~250 chars). Surfaces as a chat notification.

**Any harness:** `node agent-feedback-watch.mjs --root <serve-root> | <your wake adapter>`. Same line stream, pipe to whatever your harness consumes.

**Hermes alt:** keep the existing webhook path (`AGENT_FEEDBACK_WEBHOOK_URL`) — orthogonal to the watcher; both can coexist. See [`wake-bridge.md`](wake-bridge.md).

### 5. Annotate (browser, operator side)

For static-artifact: open `http://localhost:<port>/<file>` (use the explicit filename like `index.html`, NOT just `/` — processing scripts resolve artifact path from `location.pathname` and bare `/` causes `EISDIR` errors).

For running-app: open the running app's URL in Chrome with the hermes-chrome extension; toggle Feedback Mode.

Then:
1. Click `.af-launcher` (top-right toggle) → reveals toolbar
2. Click `[data-af-toggle]` (Annotate button) → arms overlay
3. Click target element on the page → marker created at click point with `elementAtPoint` resolution
4. Type into `[data-af-popover-input]`
5. Click `.af-popover-send`

Marker is created with `pendingComment`, committed to queue on send.

### 6. Process queue

When a Monitor wake notification arrives, the wake payload (`{id, route, summary, …}`) is usually enough to act on. Best-practice rules (skip-details, batching, reload flag choice) are in [`best-practices.md`](best-practices.md).

The processing scripts:
- `node scripts/agent-feedback-next.mjs --root <serve-root>` — peek at the next queued item
- `node scripts/agent-feedback-details.mjs <id> --root <serve-root>` — full marker payload (selector, rect, ui, etc.) — pull only when needed
- `node scripts/agent-feedback-mark.mjs <id> done "reply" [--reload | --reload-full] --root <serve-root>` — close the marker with an agent reply

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
| `agent-feedback-mark.mjs <id> <status> [reply] [--reload\|--reload-full] --root <root>` | Update status + agent reply. `--reload` → CSS hot-swap; `--reload-full` → full page reload |
| `agent-feedback-routing.mjs` | Route classifier (library; see `best-practices.md`) |
| `agent-feedback-dispatch.mjs` | Direct/worker decision (library) |
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
