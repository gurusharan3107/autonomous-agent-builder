# Agent Handbook — modifying & troubleshooting agent-feedback-artifact

Read this before editing the skill or debugging a regression. Failures listed
here were real this session — each cost minutes (or hours) to find without
the lesson.

---

## Architecture map (find the right file fast)

```
operator types comment in browser
  │
  └─ widget (overlay.html / runtime.js) ──── POST ────►  artifact-feedback-server.mjs
                                                          │
                                                          ├─ writeJson(queue.json)   ← atomic tmp+rename
                                                          ├─ broadcast(artifactPath) ← SSE to widget
                                                          └─ fs.watch fires ─────────►  same broadcast (covers direct writes)
                                                          
agent-feedback-watch.mjs (fs.watch on queue.json) ────►  stdout JSON line  ────►  Monitor (Claude Code) / pipe (other harness)

agent ─ acts on marker ─ writes file ─ mark.mjs ──── writes queue.json ────►  server fs.watch ────►  SSE ────►  widget pollStatus ────►  reload (css-hotswap | full)
```

| Concern | File | Notes |
|---|---|---|
| Widget markup + styles + IIFE (canonical) | `references/overlay.html` | Single source of truth; mirrored to extension on sync |
| Wake source (push, no polling) | `scripts/agent-feedback-watch.mjs` | fs.watch on queue.json, one line per new queued marker |
| Queue + API + SSE | `scripts/artifact-feedback-server.mjs` | POST `/api/feedback`, DELETE `/api/feedback/message`, GET `/api/feedback/status`, GET `/api/feedback/events` (SSE), agent endpoints `/api/agent/*` |
| Routing classifier | `scripts/agent-feedback-routing.mjs` | Returns `route`, `contextTier`, `workerLifecycle`, `model`, `reasoningEffort` |
| Mark + reload flags | `scripts/agent-feedback-mark.mjs` | `--reload` (css) / `--reload-full` (page) writes `reloadMode` into the item |
| Closeout | `scripts/agent-feedback-closeout.mjs` | Emits `agentReminders` block (TaskStop reminder, stopServer hint) |
| Browser delivery (running-app mode) | `.claude/plugin/hermes_chrome/extension/` | popup toggle, content-script injection, MV3 CSP-safe runtime load |

---

## Hard-won lessons — read these before you change anything

### MV3 isolated-world CSP blocks inline `<script>` injected by content scripts

**Symptom:** Widget HTML mounts and is visible, but click handlers don't fire. DevTools console shows `Executing inline script violates the following Content Security Policy directive 'script-src 'self' 'wasm-unsafe-eval' 'inline-speculation-rules' chrome-extension://...'`.

**Why:** When a content script inserts an inline `<script>` into the page DOM, Chrome evaluates that script under the **extension's** isolated-world CSP, which forbids `unsafe-inline`. The page's own CSP is unrelated.

**Fix:** Serve the script body from the extension's URL (`chrome.runtime.getURL('content-scripts/feedback-widget-runtime.js')`) via `<script src>`. The extension URL is in the CSP's `script-src 'self'` for content-script-injected content. Inline is blocked; `src` is allowed.

**Where this is implemented:** `feedback-widget.js` strips `<script>` blocks from `overlay.html` after innerHTML, then appends a separate `<script src=…>` for the runtime.

### WSL2: Chrome on Windows can't reach Node bound to IPv6 wildcard via `127.0.0.1`

**Symptom:** Widget POST to `http://127.0.0.1:4177/api/feedback` fails with "Failed to fetch" in browser console, but `curl http://127.0.0.1:4177/...` from inside WSL works fine.

**Why:** Node's default `server.listen(port)` binds to `::` (IPv6 wildcard). WSL2's port-forwarding bridges Windows `localhost` → WSL `[::1]`, but the IPv4 `127.0.0.1` → IPv6 `::` bridge does not work for Chrome's connection.

**Fix:** Use `localhost`, not `127.0.0.1`, when the widget runs in a Windows-side Chrome talking to a WSL-side Node server. The widget's `QUEUE_ORIGIN` default is `http://localhost:4177`. Don't change it back to 127.0.0.1.

### Some installed Chrome extensions inject extra CSP into target pages

**Symptom:** CSP error in DevTools attributes the violation to your content script, with a CSP that references some unfamiliar extension ID (e.g. `chrome-extension://e0b888a0-…`). devpulse itself sends no CSP.

**Why:** Other extensions installed in the operator's Chrome can rewrite the page's CSP via declarativeNetRequest or by injecting `<meta http-equiv="Content-Security-Policy">`. Don't assume the CSP you see in errors comes from the page server.

**Fix:** Don't try to placate page-side CSP from within the extension. Serve scripts from the extension URL (see MV3 lesson above) — that URL is typically allowed by these extensions' default CSPs.

### `fs.watch` on the file vs the directory

**Symptom:** Server's broadcast-on-write doesn't fire for atomic writes done by `mark.mjs` or external scripts.

**Why:** `artifact-feedback-server.mjs`'s `writeJson` uses tmp file + rename. Watching the file directly misses rename events on some platforms. Watching the parent directory catches the rename consistently.

**Fix:** Both the server's broadcast watcher AND `agent-feedback-watch.mjs` watch the parent `data/` directory and filter for `filename === "feedback-queue.json"`. Don't switch to watching the file path itself.

### TCP Nagle + Node's small SSE writes = seconds of latency

**Symptom:** SSE event delivery to widget takes 4–9 seconds.

**Why:** SSE record is a small `data: …\n\n` chunk. TCP Nagle on the response socket buffers it waiting for more data to fill a packet. Combined with `keep-alive` overhead, delivery can be seconds late.

**Fix in server:** On the SSE response, set `req.socket.setNoDelay(true)`, call `res.flushHeaders()`, and add `x-accel-buffering: no` header (defensive against proxies). After these, SSE delivery is ~1 ms.

### `broadcast("*")` vs `broadcast("/specific")` — easy to invert

**Symptom:** SSE broadcast fires (server logs show it), but widget receives no event.

**Why:** The original `broadcast()` had: `if (key !== "*" && key !== artifactPath) continue;`. For `broadcast("*")` from fs.watch, this skipped every client subscribed to a specific artifact (the common case).

**Fix:** Read the semantics carefully. `broadcast("*")` from the server side means "deliver to everyone" (used when fs.watch doesn't know which artifact changed). `broadcast("/page")` means "deliver to clients subscribed to /page OR to the wildcard". The current implementation distinguishes the two via `const deliverToAll = artifactPath === "*"`.

### `location.replace` reloads HTML but Chrome serves `/static/styles.css` from cache

**Symptom:** Auto-reload (`--reload`) fires, page URL gains `_fb_reload=…`, but the CSS change isn't visible.

**Why:** `location.replace` triggers HTML re-fetch. The new HTML still references `/static/styles.css` (no cache-buster). Chrome's HTTP cache returns the old CSS. The new page renders with stale styles.

**Fix:** Don't rely on `location.replace` for CSS changes. Use **CSS hot-swap**: replace every `<link rel="stylesheet">` with a cloned `<link>` whose href carries a fresh `?_fb_cb=<ts>` param. The new URL is a cache miss → fresh fetch → new rules applied → no page reload, no JS state loss.

`--reload` (default) does CSS hot-swap; `--reload-full` does the full `location.replace` path (use only for HTML/template edits).

### `setInterval(pollStatus, …)` captures the original function by reference

**Symptom:** After wrapping `pollStatus` with reload-check logic, the wrap fires from SSE but not from the safety-net interval.

**Why:** `setInterval(pollStatus, 30_000)` resolves `pollStatus` to a function reference at the time of the `setInterval` call. Reassigning `pollStatus = wrapped` later doesn't change the captured reference.

**Fix:** Either declare the wrap BEFORE the `setInterval(pollStatus, …)` binding, OR pass an arrow function `setInterval(() => pollStatus(), …)` that resolves the name lazily on each tick. The current code does both: declares the wrap first AND uses arrow-fn passes.

### Multi-marker reload race

**Symptom:** Two markers each marked `--reload` within milliseconds. Page reloads once → on the next page, the second marker still has `reload: true` in its server state → another reload triggers. Loop.

**Why:** Earlier wrap added the matched marker to `alreadyReloaded` then scheduled `setTimeout`. The second marker in the same `pending` list wasn't added until its own setTimeout, but the first reload happened before that.

**Fix:** Collect ALL matching markers into a `pending` array, mark all as in-flight, then commit to `alreadyReloaded` only after the swap actually applies.

### Reload commit race — persist on `load`, not on schedule

**Symptom:** Agent marks `--reload`, operator's page shows `localStorage['…:reloaded']` containing the marker ID but the `<link>` has no cache-bust query and the visible style didn't change. Operator sees no effect; agent thinks the swap fired.

**Why:** Earlier code wrote `alreadyReloaded` + persisted localStorage *before* the `setTimeout(400ms)` hot-swap. If the operator refreshed (or the SPA navigated) inside that window, the new page found the ID already in `reloaded` → `pending=0` → never applied.

**Fix:** Split state. In-memory `__afInflight` Set dedupes concurrent pollStatus calls (per-page, dies with the page). Persisted `alreadyReloaded` is committed only inside the link `load`-event settle callback. A page refresh inside the swap window leaves the item still pending so the next page handles it.

### Hot-swap on pages with no external stylesheet — auto-escalate

**Symptom:** `--reload` toast says "refreshing styles" but the visible color/font/spacing didn't change. Operator F5's manually and the change appears.

**Why:** CSS hot-swap iterates `link[rel="stylesheet"]` — pages using inline `<style>` blocks only have nothing to clone. Earlier code silently no-op'd and committed.

**Fix:** Before scheduling the swap, check `document.querySelectorAll('link[rel="stylesheet"]').some(l => l.href)`. If none, escalate to the full-reload path. Toast becomes "reloading page (no external stylesheet)".

### Double-fetch in `pollStatusWrapped`

**Symptom:** Every SSE message triggers two `/api/feedback/status` GETs. Doubles server load; doubles latency.

**Why:** The reload-check wrapper used to call `origPollStatus()` (which fetched) and then make its own fetch to the same endpoint to read the items list.

**Fix:** `pollStatus` returns the fetched `result`; the wrapper reuses it. One fetch per SSE message.

### `fs.watch` fan-out — server-side debounce

**Symptom:** Single queue write produces 2–7 SSE broadcasts. Each one wakes every connected client to re-fetch. With double-fetch this was 14× per write.

**Why:** Node's `fs.watch` is chatty — atomic rename can fire multiple `change` events per logical write.

**Fix:** `artifact-feedback-server.mjs` debounces via `watchBroadcastTimer` (30 ms trailing-edge coalesce). One broadcast per logical change.

### SSE silent-but-connected stall

**Symptom:** EventSource stays open, no `error` fires, but messages stop arriving (proxy stripped keepalives / server wedged / connection half-open). 30s safety-net poll is too slow.

**Fix:** Track `window.__afLastSseMessage` (updated on every received message). Safety-net interval checks freshness — if > 80s (~3× the server's 25s keepalive) without a message, engage 2s fast-poll. Auto-cancels when SSE catches up.

### Trash + refresh = resurrection (two distinct cases)

**Case A — queued message deletion:** operator hits trash on a queued (not yet processed) marker. Server's DELETE endpoint removes the message; if all messages gone, sets `item.status = "canceled"`. On refresh, widget's `pollStatus` calls `ensureThreadFromServerItem` for every item — without a filter, the canceled item still creates a thread. Fix: skip items where `status === "canceled"`.

**Case B — done marker deletion:** operator hits trash on a marker the agent already replied to. Server keeps the item as `status: "done"` (intentional audit trail). The widget locally removes the thread, but on refresh, the server still has it. The "canceled" filter from case A doesn't apply.

Fix: **local tombstone set** in `localStorage` under `<storageKey>:tombstones`. Every delete path (`deleteMessage`, `deleteThread`, `clearAllThreads`) records `thread.id`, `thread.markerId`, and every known `batchId`. `ensureThreadFromServerItem` skips any item whose `id` or `markerId` is tombstoned.

Don't try to "fix" this by making the server forget done items. That breaks the audit trail and the agent-reply-visible-after-refresh contract.

### Auto-reinject after page reload

**Symptom:** Operator toggles Feedback Mode on, widget appears, page auto-reloads (e.g. devpulse's 60-second refresh) — widget is gone, toggle still shows on.

**Why:** Content scripts are wiped on tab reload. Without re-injection logic, the toggle's persistent state has no effect on the new page load.

**Fix:** Service worker listens on `chrome.tabs.onUpdated` for `status: "complete"`, checks `chrome.storage.local` for the per-tab feedback flag, re-injects `feedback-widget.js`. Lives in `service_worker.js`'s onUpdated handler.

---

> **Diagnostic recipes + operator regression checklist** live in [`optimize.md`](optimize.md). This handbook stays focused on architectural lessons + editing conventions.

---

## Conventions

- **Read the canonical overlay.html in the skill**, never the mirror in the extension. The extension's `content-scripts/overlay.html` is regenerated by `sync.sh` from the skill's copy.
- **Edit overlay.html in the skill only.** Then run `bash .claude/plugin/hermes_chrome/scripts/sync.sh` to mirror + extract runtime.js.
- **Always run `bash ./scripts/validate.sh` after editing this skill.** If it exits non-zero, the SKILL.md is broken (frontmatter, sentence-length, etc.).
- **Routing keyword list grows organically.** When a marker mis-routes, add the missing keyword(s) to `agent-feedback-routing.mjs` and re-test. Style words go into `styleIntent`, calc/data words into `dataIntent`.
- **Token efficiency rule.** The wake event payload is ~250 chars by design. Don't expand it without a reason. Use `agent-feedback-details.mjs` for full marker pull when the route or summary is insufficient.
- **Reload-tier rule of thumb.** Most markers are CSS — use `--reload`. Switch to `--reload-full` only when the agent edited a template/HTML file. When in doubt, prefer `--reload` (worst case is the operator needs a manual hard-reload).
