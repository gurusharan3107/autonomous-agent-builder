---
name: agent-feedback-artifact
description: "Use when the user wants in-page annotation widget on HTML artifacts,
  marker-local chat, or comment-triggered agent work. Add, serve, queue, and
  process marker feedback. Triggers: annotation, feedback, marker, artifact."
---

# Agent Feedback Artifact

> **Self-validate after edits.** Run `./scripts/validate.sh` from the skill directory after any change.

Injects a managed annotation widget into an HTML artifact, serves it through a local feedback server, and queues marker-scoped user comments as agent work items.

## Delivery Modes

Two ways the widget reaches the page. Both share the same server, queue, routing, and wake.

| Mode | When | Delivery |
|---|---|---|
| **Static artifact** | Single HTML file (report, generated page) | `add-agent-feedback.mjs` injects the widget into the file; `artifact-feedback-server.mjs` serves it. |
| **Running app** | Any live web app (devpulse, todo, dashboards) | `hermes-chrome` extension toggles `Feedback Mode` in the popup → content script injects the widget into the live page. Same queue, same flow, no app code change. Reference: [`references/hermes-chrome-bridge-setup.md`](references/hermes-chrome-bridge-setup.md). |

## Operating Sequence

```
preflight → add widget (mode-specific) → serve → arm Monitor → annotate/process → disarm Monitor → closeout
```

**Critical args (always required for queue/watch scripts):** `--root <serve-root>`. Without it, scripts default to `process.cwd()/data/` and fail silently or read the wrong queue. Use the same path you passed to `artifact-feedback-server.mjs`.

**Non-Claude-Code harnesses:** the wake step uses the same `agent-feedback-watch.mjs` script — just pipe its stdout to whatever your harness consumes (e.g. `node agent-feedback-watch.mjs --root <dir> | <your wake adapter>`). See [`references/wake-bridge.md`](references/wake-bridge.md) for adapter patterns.

1. **Preflight:** `node scripts/agent-feedback-preflight.mjs <artifact.html> --port <port>`
2. **Add widget:**
   - Static-artifact mode: `node scripts/add-agent-feedback.mjs <artifact.html>` (injects `AGENT_FEEDBACK_WIDGET_START..END` block)
   - Running-app mode: ensure `hermes-chrome` extension is installed; user toggles `Feedback Mode` in its popup. No file edit needed.
3. **Serve:** `node scripts/artifact-feedback-server.mjs <serve-root> <port>` (queue + API only — running-app mode also uses this server)
4. **Arm Monitor (wake):** start the watch script as a push-only event source. The agent's harness consumes its stdout.
   - **Claude Code (default):**
     ```
     Monitor({
       description: "agent-feedback markers from <slug>",
       persistent: true,
       command: "node ~/.claude/skills/agent-feedback-artifact/scripts/agent-feedback-watch.mjs --root <serve-root>"
     })
     ```
     Each new marker prints one JSON line → surfaces as a chat notification. No polling.
   - **Any harness:** `node agent-feedback-watch.mjs --root <serve-root> | <your wake adapter>` — same line stream, pipe into whatever your harness consumes.
   - **Hermes (alt):** keep the existing webhook path (`AGENT_FEEDBACK_WEBHOOK_URL`) — orthogonal to the watcher, both can coexist. See [`references/wake-bridge.md`](references/wake-bridge.md).
5. **Annotate (browser):** Open `http://localhost:<port>/<file>` (use the explicit filename like `index.html`, NOT just `/` — processing scripts resolve artifact path from `location.pathname` and bare `/` causes `EISDIR` errors) → click `.af-launcher` (top-right toggle) → click `[data-af-toggle]` (Annotate button, arms overlay) → click target element (layer intercepts with `elementAtPoint`) → type in `[data-af-popover-input]` → click `.af-popover-send`. Selectors: launcher=`.af-launcher`, annotate=`[data-af-toggle]`, input=`[data-af-popover-input]` (NOT `.af-popover-input`). Marker created with `pendingComment`, committed on send.

   **CDP contract:** click_selector, fill_selector, evaluate need CDP (`chrome.debugger`). If the bridge returns `"Another debugger is already attached"`, Chrome DevTools is open on the tab. Follow the bridge skill's CDP recovery: `close_tab` then `goto` to create a fresh tab without DevTools.
6. **Process queue:** Monitor notification arrives → act directly on the wake summary in most cases. The payload (`{id, route, summary, sentAt, createdAt, emittedAt}`) is usually enough.
   - **Skip `agent-feedback-details.mjs` when** `route` is `no_worker_main_agent_direct` AND the `summary` is unambiguous (e.g. "make X red", "change font", "add subtitle"). Pulling details adds ~5 s per marker for no gain on style routes.
   - **Pull details when** `route` is `deep_marker_worker` (data/calc intent) OR the summary is too vague to act on without selector + rect + ui context.
   - **Batch concurrent markers in one turn.** If a new wake notification arrives while you're still processing a previous marker, fold it into the same turn — do not sequentially mark-done one-at-a-time. Measured ~2× wall-clock savings on 3 markers vs. one-per-turn.
   - **Apply the fix** → call `agent-feedback-mark.mjs <id> done "reply" [reload-flag] --root <serve-root>`. Choose the reload flag per change type:
     - `--reload` — **CSS hot-swap (default for style changes).** Widget replaces `<link rel="stylesheet">` with a cache-busted clone. No page reload, no runtime state loss, ~400–700 ms to visible change. Use for every CSS/styling edit.
     - `--reload-full` — **Full page reload.** Widget calls `location.replace` with a cache-bust query param. Use when the edit touched HTML/templates (e.g. `dashboard.html`, JSX, Jinja2). Slower (~700 ms + Chrome's HTML parse/render) and loses runtime JS state, but necessary for non-CSS structural changes.
     - *(no flag)* — Reply only, no auto-refresh. Use for question-only replies or when the operator should decide whether to reload.
7. **Disarm Monitor:** at closeout, `TaskStop` the Monitor handle (the agent owns the task ID).
8. **Closeout:** `node scripts/agent-feedback-closeout.mjs <artifact.html> --port <port>`

**--root is required** for queue scripts (including `agent-feedback-watch.mjs`). Points at the server's `data/` directory. Without it, scripts read `process.cwd()/data/` and fail.

## Script Inventory

| Script | Purpose |
|---|---|
| `add-agent-feedback.mjs` | Inject widget before `</body>` |
| `remove-agent-feedback.mjs` | Remove managed block (roundtrip-safe) |
| `artifact-feedback-server.mjs` | Static serving + `/api/feedback/*` + queue |
| `agent-feedback-preflight.mjs` | Readiness checks |
| `agent-feedback-closeout.mjs` | Read-only state report |
| `agent-feedback-next.mjs` | Next queued item |
| `agent-feedback-details.mjs <id>` | Full marker payload |
| `agent-feedback-mark.mjs <id> <status> [reply] [--reload\|--reload-full]` | Update status + agent reply. `--reload` → CSS hot-swap; `--reload-full` → full page reload. |
| `agent-feedback-routing.mjs` | Route selection (see refs) |
| `agent-feedback-dispatch.mjs` | Direct/worker decision |
| `agent-feedback-watch.mjs` | Push-only wake source — `fs.watch` on queue.json, one JSON line per new marker to stdout. Consumed by `Monitor` (Claude Code) or any harness adapter. |

## Routing Rules

`classifyWorkItem` decides route based on intent keywords:

| If intent matches | Route to |
|---|---|
| `styleIntent` words (bigger, font, color, spacing, padding, margin, ui, style, layout, button, icon, copy, text, etc.) | `no_worker_main_agent_direct` |
| `dataIntent` words (total, gross, tax, income, calculate, amount, number, incorrect, wrong, `₹`, `rs.`) | `deep_marker_worker` |
| Both match | Prefer style if style word count ≥ data word count |

selector is evidence, not intent — do not classify by `data-*` attributes.

## Closeout

Always run `closeout.mjs`. Report: widget state, server state, webhook config, queue counts, browser evidence, cleanup commands.

## Load References On Need

| When | Load |
|---|---|
| Wake adapter (Monitor / file-watch / Hermes webhook) | `references/wake-bridge.md` |
| CORS issues with widget fetch | `references/cors-setup.md` |
| River acceptance test checklist | `references/browser-acceptance.md` *(see below)* |
| Hermes Chrome Bridge for headed testing | `hermes-chrome-bridge` skill |
| Widget HTML/CSS/JS internals | `references/overlay.html` |

## Why This Exists

Artifact feedback is lossy via chat (operator describes, agent guesses). This skill makes the artifact the feedback surface, captures marker-scoped intent at source, and gives agents a small default packet with deeper context available on demand.
