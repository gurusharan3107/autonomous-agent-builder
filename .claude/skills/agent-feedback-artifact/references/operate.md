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
Each new marker prints one JSON line — `{id, markerId, route, status, url, origin, artifactTitle, artifactPath, summary, visibleText, sentAt, createdAt, emittedAt}` (~400–460 chars). Surfaces as a chat notification. `origin` and `visibleText` let you decide directly: `origin=localhost` + clear summary → act; `origin=external` + clear question → answer from URL alone; `visibleText` disambiguates deictic phrases.

**Any harness:** `node agent-feedback-watch.mjs --root <serve-root> | <your wake adapter>`. Same line stream, pipe to whatever your harness consumes.

**Hermes alt:** keep the existing webhook path (`AGENT_FEEDBACK_WEBHOOK_URL`) — orthogonal to the watcher; both can coexist. See [`wake-bridge.md`](wake-bridge.md).

### 5. Annotate (browser, operator side)

For static-artifact: open `http://localhost:<port>/<file>` (use the explicit filename like `index.html`, NOT just `/` — processing scripts resolve artifact path from `location.pathname` and bare `/` causes `EISDIR` errors).

For running-app: open the running app's URL in Chrome with the hermes-chrome extension; toggle Feedback Mode.

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

1. **Re-check Annotate state at the start of every flow.** `aria-pressed` resets to `false` after each Send and on Feedback Mode re-toggle. Do `evaluate({pressed: ...})` first; only click Annotate if `pressed === "false"`.
2. **Batch related actions in ONE `bridge({type:"run", actions:[...]})` call.** Between bridge calls there is an idle window where popover state can settle (re-anchoring, re-renders). A multi-call test that places a marker in call 1 and reads popover-input rect in call 2 will sometimes see `width: 0` because the popover collapsed back to its compact form. Single batched call eliminates the gap.
3. **Use `click_selector` over `cursor_move + cursor_click` for small targets.** The high-level click auto-handles cursor activation and re-tries hit-test against the resolved element rather than the topmost (which can be an SVG icon inside a button — the click still works via bubbling, but the high-level helper is more reliable).
4. **Verify visible change via computed style on the actual styled element**, not the marker selector. The marker may be placed on a container whose color is inherited; the change is on a child. Read `getComputedStyle(child).color`, not `getComputedStyle(container).color`.
5. **Cursor presence is operator feedback — never park the cursor at an edge or off-screen.** The cursor sits at the last action coordinate, so end batched sequences at meaningful targets (the marker, the value just changed, the popover gear). Never call `cursor_hide`. Don't move to viewport corners. The operator infers "agent is working / agent finished here" from where the cursor stopped — make that location informative.

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
