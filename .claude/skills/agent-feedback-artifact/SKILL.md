---
name: agent-feedback-artifact
description: "Use when the user wants in-page annotation widget on HTML artifacts,
  marker-local chat, or comment-triggered agent work. Add, serve, queue, and
  process marker feedback. Triggers: annotation, feedback, marker, artifact."
---

# Agent Feedback Artifact

Injects a managed annotation widget into an HTML artifact (static file or running web app), serves it through a local feedback server, and queues marker-scoped user comments as push-delivered agent work items.

> Self-validate after edits: `./scripts/validate.sh` from the skill directory.

## Delivery modes

The one thing that decides whether markers arrive: **where the widget POSTs `/api/feedback`, and whether a queue server is listening there.** The two modes differ only in that.

| | **Static artifact** | **Running app** |
|---|---|---|
| When | Single HTML file | Live web app (devpulse, dashboards) |
| Widget injected by | `add-agent-feedback.mjs` (baked into the file) | `hermes-chrome` extension popup toggle (no app code change) |
| Processes | **1** — `artifact-feedback-server.mjs` both serves the file AND hosts the queue | **2** — the app (its own server) + a queue-only `artifact-feedback-server.mjs` sidecar |
| Widget posts to | **same-origin** (`__FB_BASE=""`) — the server that served the page | the **queue sidecar**: popup "Queue origin" override, else default **`http://localhost:4177`** |
| Operator opens | the **served** URL `http://localhost:<port>/<file>.html` | the **app's own** URL |
| Queue-origin config | none | none if the sidecar runs on `4177`; else set the popup override |

**Two rules that prevent silent "Send failed" / markers-never-arrive:**
1. **Static: open the SERVED URL, never `file://…`.** A `file://` page posts to a `file://` base → no server → marker dropped.
2. **App: the queue sidecar must be reachable at the widget's queue origin.** Default is `4177`; if you run the sidecar on another port, set the popup "Queue origin" to match. The server's default port is also `4177` (`artifact-feedback-server.mjs`), so leaving both at the default just works.

> Diagnosing a no-show marker: a `curl -X POST :<port>/api/feedback` that returns 202 + fires the Monitor proves server+watcher are fine → the break is browser→server (wrong port/origin or `file://`). In extension mode, **read the live tab with the hermes bridge** (`page_context`, read-only `evaluate` of `__FB_BASE`) rather than guessing.

## Operating sequence

```
preflight → add widget → serve → arm/heal wake → process markers → disarm Monitor → closeout (+ optimize self-introspect)
```

Full step-by-step + script invocations → [`references/operate.md`](references/operate.md).

**`close` lane** (`/agent-feedback-artifact close`) — tear down the live session. **Distinct from `closeout`** (which stays report-only + optimize self-introspection; `close` does not run it). `close` stops *both* running pieces:
1. **Server** — `node scripts/agent-feedback-close.mjs [--port 4177]` SIGTERMs the listener (the server traps it and closes gracefully; SIGKILLs a straggler). `serverWasRunning:false` = already stopped, fine.
2. **Monitor** — the script can't end a harness Task. **You** call `TaskStop` on the `agent-feedback-watch.mjs` Monitor handle you armed in step 4 of the operating sequence. Skip if you never armed one.

Key invariants (detail in [`operate.md`](references/operate.md)):
- **Wake isn't durable; the queue is.** The Monitor can die silently mid-session → markers sit `queued`, unwoken. At session entry / each `/agent-feedback-artifact` (re)invocation run `agent-feedback-wake-status.mjs --root <root>`; on `rearm_required` (exit 1), `pkill -f agent-feedback-watch.mjs` + re-arm the Monitor (backfills the backlog).
- **Closeout `optimize`** = model-judged self-introspection, not a ritual. Clean session → change nothing; only when warranted, load [`optimize.md`](references/optimize.md) → "Optimize step".
- **Args:** read-only/file scripts take `--root`; mutating CLIs (`dispatch`, `mark`) take `--port` (default 4177).

## Per-marker action (every wake notification)

Wake payload: `{id, markerId, route, status, url, origin, artifactTitle, artifactPath, summary, visibleText, sentAt, createdAt, emittedAt}` (~400–460 chars). `origin` ∈ `localhost | external | github | file | blocked | unknown` — derived from `url`. `visibleText` is the marked element's text (≤60 chars), dedup'd to `null` when identical to `summary` — disambiguates deictic comments ("change this", "make the number red"). Pre-decide the action from these fields before paying any round-trip.

Decision is `origin` × `route` × `summary clarity`:

| `origin` | `route` + summary | What to do |
|---|---|---|
| `localhost` | direct + clear ("make X red") | Act on the local app — file follows from URL/artifactPath. **Skip details.** |
| `localhost` | direct + vague, or any `cheap_marker_worker` | Pull details once for selector/rect/ui |
| `external` | direct/cheap + clear question | **Answer from summary + URL.** Skip details. |
| `external` | direct/cheap + vague | Pull details (selectedText, visibleText) |
| `github` | any | URL is the work target — fetch/inspect the linked repo, then answer or act |
| `file` | any | Static artifact mode — file path is in the URL |
| `blocked` | any | Surface as warning (`chrome://`, `about:`, `view-source:`) |
| any | `deep_marker_worker` | Pull details. Dispatch a background Task subagent for data/calc work |

### Where to run it — inline vs background subagent

The `dispatch` field on the dispatched item (`"inline"` | `"background_task"`) says where to run the work:

| Route / `dispatch` | Run it | Why |
|---|---|---|
| `no_worker_main_agent_direct` → `inline` | **Main thread, directly** | Single-element style/text tweak; spawning a subagent is pure overhead |
| `deep_marker_worker` / work-requests → `background_task` | **Background Task subagent** (`Agent`, `run_in_background:true`); prompt = the item's `workerPrompt`; `Explore` (read-only diagnosis/scoping), `general-purpose`/`Plan` when you assign a write scope | Real investigation/implementation — keeps the main thread free and isolates context |
| `cheap_marker_worker` | Inline by default; **background if ≥2 markers are concurrent** | One scoped diagnosis is cheap inline; a burst crosses the parallelism threshold |
| **Multiple worker markers queued together** | **Dispatch concurrently** (one message, N `Agent` calls); **cap concurrency**; **serialize write-scope markers per file** (read-only parallelize freely) | Wall-clock |

`spawn.model` / `reasoningEffort` / `fork_context` are **advisory** — the harness Task tool owns model/isolation; you can't set them per-subagent from a skill.

### Durability rules (the operator may have walked away)

- **Terminal-state guarantee:** every claimed marker MUST end `done` or `blocked` — even on subagent error (catch → `mark <id> blocked "<error>"`). Never leave a marker in `processing`. The server's reclaim sweep is the backstop (a dead worker's lease expires → requeued, or `blocked` after `AGENT_FEEDBACK_MAX_ATTEMPTS`), but don't rely on it for normal completion.
- **Ambiguity → `blocked`, never `AskUserQuestion`:** there may be no one to answer. `mark <id> blocked "<what you need>"` — the reason surfaces on the marker for the returning operator.
- **Long subagent (> lease TTL, default 10 min):** send a heartbeat `mark <id> processing "still working: <phase>"` once per window so the sweep doesn't reclaim live work.

After applying the fix (the CLIs are now HTTP clients of the server — pass `--port`, default `4177`, not `--root`):
```
node scripts/agent-feedback-mark.mjs <id> done "reply" [--reload | --reload-full] [--port <port>]
```
- `--reload` — CSS hot-swap (use for every CSS change; ~700 ms to visible)
- `--reload-full` — full page reload (use for HTML/template edits)
- *(no flag)* — reply only, no auto-refresh (question-only replies)

**Batch concurrent wakes into one turn** — dispatch worker-routed ones as parallel background subagents (~2× wall-clock on 3 markers).

Rationale + reply conventions → [`references/best-practices.md`](references/best-practices.md).

## Load references on need

| When | Load |
|---|---|
| Step-by-step operating procedure | [`references/operate.md`](references/operate.md) |
| Optimize step (closeout self-introspection) or diagnosing a runtime issue | [`references/optimize.md`](references/optimize.md) |
| Skill-specific defaults + conventions | [`references/best-practices.md`](references/best-practices.md) |
| Modifying or extending the skill itself | [`references/agent-handbook.md`](references/agent-handbook.md) |
| Wake adapter (Monitor / file-watch / Hermes) | [`references/wake-bridge.md`](references/wake-bridge.md) |
| CORS issues | [`references/cors-setup.md`](references/cors-setup.md) |
| Browser acceptance checklist | [`references/browser-acceptance.md`](references/browser-acceptance.md) |
| Widget HTML/CSS/JS internals | [`references/overlay.html`](references/overlay.html) (canonical source) |
| Headed browser testing for running-app mode | `hermes-chrome` skill (separate top-level skill) |
