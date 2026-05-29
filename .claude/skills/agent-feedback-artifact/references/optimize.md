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

1. Check the queue file: did `mark.mjs` actually write `reload: true` + `reloadMode`? `curl /api/feedback/status?artifact=/` and look for those fields.
2. DevTools → Network → filter `events` → is there an open EventSource connection? If not → widget isn't getting pushes; check SSE endpoint reachability.
3. Page console: `localStorage.getItem('agent-feedback:/:reloaded')` — does it contain the marker id? If yes → the wrap already saw and processed it; the page may have already refreshed and you missed the visible change. If no → wrap isn't being called.
4. If wrap isn't being called → check SSE delivery via `curl -N http://localhost:4177/api/feedback/events?artifact=/` in a separate terminal while POSTing.
5. If SSE delivers but wrap isn't called → check the pollStatus wrap-ordering bug in [`agent-handbook.md`](agent-handbook.md).

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
