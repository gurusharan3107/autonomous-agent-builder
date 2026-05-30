# agent-feedback-artifact — Optimize

Runtime diagnosis + per-failure-class recipes when the loop misbehaves.
Loaded on demand from SKILL.md when a failure is detected.

`operate.md` covers the happy path. This file is when something doesn't work.

---

## Operator-side regressions to look for

Before declaring a fix done, walk this checklist:

| Check | How to verify |
|---|---|
| Toggle survives long page auto-refresh | Many dashboards reload every 30–60 s. Wait it out — widget should reappear automatically via the service-worker auto-reinject. |
| Trash removes locally AND on refresh | Click trash on a marker. Hard-reload. Marker should stay gone (tombstone in localStorage prevents resurrection). |
| Clear-all removes everything AND on refresh | Click clear icon. Hard-reload. Zero markers. |
| Configure button opens to Agent tab | Click configure in the popover footer. "Agent" tab should be active, not "UI". |
| Send → reply visible in status bar without manual refresh | Send a comment, wait. Agent's reply should appear in the top-right status bar within ~1 s (SSE push) or 30 s (safety-net poll). |
| Auto-reload doesn't infinite-loop on multi-reload markers | Mark two markers `--reload` quickly. Exactly one CSS-hotswap / one page reload should occur. |

---

## Diagnostic recipes

### "Widget isn't injecting on the running app"

1. Open DevTools on the page. Console: any CSP errors mentioning the extension URL? → MV3 inline-script lesson in [`agent-handbook.md`](agent-handbook.md).
2. `chrome://extensions` → check the hermes-chrome extension is loaded, not errored.
3. From page console: `document.getElementById('hermes-feedback-mount')` — should be a node.
4. If mount exists but `window.__agentFeedbackLoaded === false` → script didn't run → CSP issue → verify runtime is served via `<script src>` not inline.

### "Markers POSTed but agent never wakes"

1. `curl http://localhost:4177/api/feedback/status?artifact=/` — does the marker exist server-side? If no → widget POST failed (likely CORS — see [`cors-setup.md`](cors-setup.md) — or WSL2 IPv6 issue from agent-handbook).
2. `ps -ef | grep agent-feedback-watch` — is the watch script running? If not → no wake source.
3. `ls /tmp/agent-feedback-<slug>/data/feedback-queue.json` — does the watched file exist?
4. `node scripts/agent-feedback-watch.mjs --root <serve-root>` directly — does it emit lines when you POST a marker?
5. If yes → the wake source works; check the agent harness adapter (Monitor in Claude Code, pipe/tail elsewhere).

### "Auto-reload didn't fire after `--reload`"

1. Check the queue: did `mark.mjs` actually write `reload: true` + `reloadMode`? `curl /api/feedback/status?artifact=/` and look for those fields.
2. DevTools → Network → filter `events` → is there an open EventSource connection? If not → widget isn't getting pushes; check SSE endpoint reachability.
3. Page console: `localStorage.getItem('agent-feedback:/:reloaded')` — does it contain the marker id?
   - **Yes + `<link>` has no `?_fb_cb=` query** → race: the page refreshed inside the 400ms setTimeout window before the swap committed. Should not happen after the load-event commit fix; if it does, re-check `overlay.html` `pollStatusWrapped` — `commit()` must be inside the `link.load` settle callback, not on schedule.
   - **Yes + cache-busted link present** → the swap fired; if no visible change, the disk file may not have your edit, or specificity is wrong.
4. **Page uses inline `<style>` only (no `<link rel="stylesheet">`)** → `--reload` auto-escalates to full reload now; if it didn't, you're running an old widget runtime. Refresh page to pick up new content script.
5. **SSE silent > 80s** → adaptive fast-poll engages (2s); check `window.__afFastPolling` is set. If SSE is permanently dead, server may be down or proxy stripping keepalives.
6. **`/api/feedback/status` fetched twice per SSE message** → old code; the wrapper now reuses `origPollStatus`'s returned `result`. Re-sync the extension.

### "Visible change applied but page state was lost"

You probably used `--reload-full` for a CSS-only change. Switch to `--reload` (CSS hot-swap preserves runtime state).

### "Comment never reaches queue"

Likely CORS / network. DevTools Network panel:
- Is the OPTIONS preflight returning 204 with `access-control-allow-origin`?
- Is the POST `/api/feedback` returning 202?
- Is the response body well-formed JSON?

If preflight fails → server isn't sending CORS headers (check `artifact-feedback-server.mjs` is current).
If POST returns 4xx → check payload shape (see `comments: []` requirement).
If both look fine but widget shows "Send failed" → the widget's `__FB_BASE` resolution; check `data-queue-origin` on the mount node matches a reachable URL.

### "Deleted markers reappear on refresh"

Tombstone is missing or being skipped. Page console:
- `localStorage.getItem('agent-feedback:/:tombstones')` — should contain JSON array of deleted IDs.
- If the array is empty after clicking trash → the delete handler isn't writing tombstones. Verify the `tombstone(...)` call in `deleteMessage`/`deleteThread`/`clearAllThreads` in `overlay.html`.
- If the array IS populated but markers reappear → `ensureThreadFromServerItem` isn't reading the set. Check the early-return guard near top of that function.

### "SSE delivery is seconds late"

TCP Nagle + small SSE writes. Server should call `req.socket.setNoDelay(true)` + `res.flushHeaders()` + set `x-accel-buffering: no` header. See the SSE-delivery lesson in [`agent-handbook.md`](agent-handbook.md).

### "One queue write triggers N fetches (N=2..14)"

Node's `fs.watch` is chatty — one logical write can fire 2–7 `change` events. Server now coalesces with a 30 ms debounce (`watchBroadcastTimer` in `artifact-feedback-server.mjs`). If you see > 1 fetch per write, you're running an old server — kill and restart it.

### "UI panel shows the wrong color after a change"

- **Same color as before the change** → the marker was placed on a *container* whose own color genuinely didn't change; the change was on a child. The "Primary text" row (when surfaced) shows the prominent child's color. If that row is missing, the child color matches the container's (i.e. no visible difference at that element).
- **Captured-at-creation stale snapshot** → fixed by live re-sample; the tag shows " (snapshot)" suffix only when the live selector failed to resolve.

### "UI panel hangs on a huge container"

`findPrimaryTextChild` walks descendants — bounded to depth 4 and 50 visited nodes. If you removed those caps locally, restore them.

### "Routing put a clearly-style marker on `cheap_marker_worker` or `deep_marker_worker`"

`agent-feedback-routing.mjs`'s `styleIntent` regex missed the keyword. Add the missing word to the alternation and re-test. The list is intentionally grown by experience — additions are cheap and low-risk.

---

## When to escalate to the agent handbook

For these classes, optimize.md isn't enough — read [`agent-handbook.md`](agent-handbook.md):

- MV3 isolated-world CSP behavior
- WSL2 IPv6 vs IPv4 routing
- Widget state model (localStorage + server queue + tombstones)
- pollStatus wrap ordering
- Multi-marker reload race
- fs.watch on directory vs file
