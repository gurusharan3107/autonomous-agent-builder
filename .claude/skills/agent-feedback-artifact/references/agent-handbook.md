# Agent Handbook — modifying & troubleshooting agent-feedback-artifact

Read before editing the skill or debugging a regression. Every lesson below was a real failure that cost real time.

## Architecture map

```
operator types comment → widget (overlay.html/runtime.js) ──POST──► artifact-feedback-server.mjs
                                                                       ├─ writeJson(queue.json)  ← atomic tmp+rename
                                                                       ├─ broadcast(artifactPath) ← SSE to widget
                                                                       └─ fs.watch ──► same broadcast (covers direct writes)
agent-feedback-watch.mjs (fs.watch on queue.json) ──► stdout JSON line ──► Monitor / pipe
agent acts → mark.mjs writes queue.json → server fs.watch → SSE → widget pollStatus → reload (css-hotswap | full)
```

| Concern | File |
|---|---|
| Widget markup+styles+IIFE (canonical) | `references/overlay.html` (mirrored to extension on sync) |
| Wake source (push) | `scripts/agent-feedback-watch.mjs` |
| Queue + API + SSE + reclaim sweep | `scripts/artifact-feedback-server.mjs` (`/api/feedback/*`, `/api/agent/*`) |
| Routing + reclaim logic | `scripts/agent-feedback-routing.mjs` |
| Mark + reload flags | `scripts/agent-feedback-mark.mjs` |
| Closeout + optimize | `scripts/agent-feedback-closeout.mjs` |
| Browser delivery (running-app) | `.claude/plugin/hermes_chrome/extension/` |

## Hard-won lessons

**MV3 isolated-world CSP blocks inline `<script>`.** Widget mounts but handlers dead; console shows `script-src 'self'…` violation. Inline `<script>` injected by a content script runs under the *extension's* isolated-world CSP (no `unsafe-inline`). Fix: serve the runtime via `<script src=chrome.runtime.getURL('content-scripts/feedback-widget-runtime.js')>` — `feedback-widget.js` strips inline `<script>` from overlay.html then appends the `src` tag.

**WSL2: `127.0.0.1` unreachable from Windows Chrome.** Widget POST to `127.0.0.1:4177` "Failed to fetch" but `curl` from WSL works. Node binds `::`; WSL2 forwards Windows `localhost`→`[::1]`, not `127.0.0.1`→`::`. Fix: use `localhost`. Widget `QUEUE_ORIGIN` default is `http://localhost:4177` — keep it.

**Queue origin resolution — this skill's capability, not hermes-chrome's.** The hermes extension only provides the popup UI + injection plumbing; this contract is owned here (a delivery-behavior change is an agent-feedback change). Chain:
```
popup "Queue origin" → chrome.storage.local.feedbackQueueOrigin
  → service_worker.injectFeedbackWidget() sets window.__HERMES_FEEDBACK_QUEUE_ORIGIN
    → feedback-widget.js: QUEUE_ORIGIN = override || "http://localhost:4177"
      → mount data-queue-origin → runtime __FB_BASE → fetch(`${__FB_BASE}/api/feedback`)
```
- Static mode: no mount wrapper → `__FB_BASE=""` → same-origin. Override doesn't apply.
- Default `4177` is correct for running-app (queue sidecar on 4177). **Do NOT default to `location.origin`** — that points at the app, not the queue server.
- Override only for a non-default/remote sidecar. Most no-shows: non-default port without matching override, or operator on `file://`. Confirm with `curl -X POST :<port>/api/feedback` (202 = server fine), then read the live tab's `__FB_BASE` via the hermes bridge.

**Other installed extensions inject CSP.** CSP error names an unfamiliar extension ID though the page server sends none. They rewrite page CSP (declarativeNetRequest / `<meta>`). Fix: don't placate page CSP; serve scripts from the extension URL (above).

**`fs.watch`: watch the dir, not the file.** Broadcast-on-write misses atomic writes. `writeJson` is tmp+rename; watching the file misses rename on some platforms. Fix: both server + watch.mjs watch parent `data/` and filter `filename==="feedback-queue.json"`.

**TCP Nagle stalls SSE 4–9 s.** Small `data:` chunk buffered by Nagle + keep-alive. Fix: on the SSE response `req.socket.setNoDelay(true)`, `res.flushHeaders()`, `x-accel-buffering: no` → ~1 ms.

**`broadcast("*")` vs `("/page")` — easy to invert.** Broadcast logged but widget gets nothing: filter `key!=="*" && key!==artifactPath` skipped specific-artifact clients on `broadcast("*")`. Fix: `deliverToAll = artifactPath === "*"` — `"*"` = everyone, `"/page"` = that page + wildcard.

**`location.replace` serves cached CSS.** `--reload` fires, URL gains `_fb_reload`, CSS unchanged: HTML re-fetched but `/static/styles.css` has no cache-buster → cached. Fix: CSS hot-swap — clone each `<link rel=stylesheet>` with `?_fb_cb=<ts>`. `--reload` = hot-swap; `--reload-full` = `location.replace` (HTML/template edits only).

**`setInterval(pollStatus,…)` captures by reference.** Wrapped pollStatus fires from SSE but not the safety interval — the interval captured the original ref. Fix: declare the wrap *before* the setInterval AND pass `() => pollStatus()`. Code does both.

**Multi-marker reload race.** Two `--reload` markers ms apart → reload loop (2nd not committed before 1st reload). Fix: collect all matching into `pending`, mark in-flight, commit to `alreadyReloaded` only after the swap applies.

**Reload commit race — persist on `load`, not on schedule.** `:reloaded` has the ID but `<link>` not cache-busted: state written before the 400 ms swap; a refresh in that window makes the new page think it's done. Fix: in-memory `__afInflight` dedupes; persist `alreadyReloaded` only in the link `load` settle callback.

**Hot-swap with no external stylesheet → escalate.** "refreshing styles" but no change (inline-`<style>` page has no `<link>` to clone). Fix: if no `link[rel=stylesheet][href]`, escalate to full reload.

**Double-fetch in `pollStatusWrapped`.** Each SSE msg → 2 status GETs (wrapper fetched after `origPollStatus()` already fetched). Fix: pollStatus returns the result; wrapper reuses it.

**`fs.watch` fan-out → debounce.** One write → 2–7 broadcasts (atomic rename fires multiple `change` events). Fix: `watchBroadcastTimer` 30 ms trailing-edge coalesce.

**SSE silent-but-connected stall.** EventSource open, no `error`, messages stop (proxy stripped keepalives / wedged). Fix: track `window.__afLastSseMessage`; if >80 s stale (~3× the 25 s keepalive) engage 2 s fast-poll, auto-cancel when caught up.

**Trash + refresh = resurrection (two cases).** (A) queued-message delete → server sets `status:"canceled"`; skip canceled items in `ensureThreadFromServerItem`. (B) done-marker delete → server keeps it `done` (audit trail); a local **tombstone set** in `localStorage` (`<storageKey>:tombstones`, recording id/markerId/batchIds on every delete path) makes `ensureThreadFromServerItem` skip it. Don't make the server forget done items — breaks the audit trail + reply-after-refresh contract.

**Auto-reinject after page reload.** Feedback Mode on, page auto-reloads, widget gone but toggle still on (content scripts wiped on reload). Fix: SW `chrome.tabs.onUpdated` (`status:"complete"`) checks the per-tab flag and re-injects `feedback-widget.js`.

> Diagnostic recipes + operator regression checklist live in [`optimize.md`](optimize.md). This handbook is architectural lessons + conventions only.

## Conventions

- **Edit the canonical `overlay.html` in the skill**, never the extension mirror — then `bash .claude/plugin/hermes_chrome/scripts/sync.sh` to mirror + extract `runtime.js`.
- **Run `./scripts/validate.sh` after editing.** Non-zero = SKILL.md broken (frontmatter, sentence-length).
- **Routing keywords grow organically** — mis-route → add keyword(s) to `agent-feedback-routing.mjs` (`styleIntent` / `dataIntent` / `actionIntent`) and re-test.
- **Keep the wake payload compact** (~250 chars by design); pull `agent-feedback-details.mjs` only when route/summary is insufficient.
- **Reload tier:** most markers are CSS → `--reload`; `--reload-full` only for template/HTML edits. When in doubt, `--reload`.
