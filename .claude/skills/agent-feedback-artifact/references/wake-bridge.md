# Wake Bridge — push the agent on new markers

Two layers, decoupled. The wire format is harness-agnostic; the wake adapter is per-harness.

```
operator comments
    → widget POST /api/feedback
        → server writes queue.json (DURABLE)
            ├─ (a) fs.watch fires → agent-feedback-watch.mjs prints one JSON line
            │       └─ harness adapter consumes the line (Monitor / tail / exec)
            └─ (b) server POSTs AGENT_FEEDBACK_WEBHOOK_URL  (if configured)
                    └─ webhook receiver dispatches per harness
```

Pick (a) for Claude Code and most other harnesses. Pick (b) for Hermes. They can coexist — both observe the same queue.

---

## (a) File-watch + Monitor — Claude Code default

Push end-to-end. Kernel-level inotify (Linux) / FSEvents (macOS). Zero polling.

**Arm during skill operating sequence step 4:**

```
Monitor({
  description: "agent-feedback markers from <slug>",
  persistent: true,
  command: "node ~/.claude/skills/agent-feedback-artifact/scripts/agent-feedback-watch.mjs --root <serve-root>"
})
```

Each new marker prints one line:
```json
{"id":"afw-...","markerId":"af-...","route":"deep_marker_worker","status":"queued","artifactPath":"/","summary":"make brand text larger"}
```
That line surfaces as an in-conversation notification. The agent decides whether to fetch full marker context via `agent-feedback-details.mjs <id>` or act on the summary alone (style-class routes typically don't need full context).

**Disarm at closeout:** `TaskStop` the Monitor handle, then `agent-feedback-closeout.mjs`.

### Auto-refresh tiers (mark.mjs → widget)

When marking a marker `done`, pick the right refresh signal so the operator sees the change without a manual reload:

| Flag | What the widget does | Use when |
|---|---|---|
| `--reload` | **CSS hot-swap.** Replaces every `<link rel="stylesheet">` with a cache-busted clone. ~400–700 ms to visible change. No page reload, no runtime state loss. | CSS / styling edits (color, font, spacing, layout) — the dominant case |
| `--reload-full` | **Full page reload.** `location.replace` with a cache-bust query param. ~700 ms + Chrome HTML parse/render. Runtime JS state is reset. | HTML / template / JSX / Jinja2 edits — anything that changes the DOM structure |
| *(no flag)* | Reply only. No auto-refresh. | Question-only replies, or when the operator should decide whether to reload |

The widget reads `reloadMode` from `/api/feedback/status` (`"css"` or `"full"`). When multiple pending markers exist in one batch, `full` wins (escalates).

**Backfill:** on script start, every `status: "queued"` item already in `queue.json` is emitted once. Agent restarts don't drop work.

**Token/context cost:** one ~140-char line per marker. Pull details only on demand. Nothing recurring.

---

## (a') File-watch + any harness adapter

Same watch script, different consumer:

```bash
node ~/.claude/skills/agent-feedback-artifact/scripts/agent-feedback-watch.mjs --root <serve-root> | <your wake bridge>
```

Examples of `<your wake bridge>`:
- `while read line; do my-harness-cli notify "$line"; done`
- A small Node receiver that writes each line as a one-line sentinel file under `~/agent-feedback-inbox/`
- A Slack/email forwarder for human-on-call

---

## (b) Hermes webhook — Hermes harness

When `AGENT_FEEDBACK_WEBHOOK_URL` is set on the server, every new marker triggers an immediate POST to that URL with the full work-item summary. The server signs with HMAC-SHA256 if `AGENT_FEEDBACK_WEBHOOK_SECRET` is set.

### Setup

```bash
hermes gateway setup  # or add platforms.webhook to config.yaml

hermes webhook subscribe artifact-feedback-<slug> \
  --prompt "New artifact feedback comment on {artifactPath}. Work ID: {items[0].id}, Route: {items[0].route}, Marker: {items[0].visibleText}, Message: {items[0].latestUserMessage}. Use the agent-feedback-artifact skill to process this marker. Run dispatch to claim, then process per route." \
  --skills "agent-feedback-artifact" \
  --deliver origin \
  --events "artifact_feedback_new"
```

Then start the server with the returned URL:

```bash
AGENT_FEEDBACK_WEBHOOK_URL="http://localhost:8644/hooks/artifact-feedback-<slug>" \
AGENT_FEEDBACK_WEBHOOK_SECRET="$(hermes webhook list --json | jq -r '.[] | select(.name=="artifact-feedback-<slug>") | .secret')" \
  node scripts/artifact-feedback-server.mjs <serve-root> <port>
```

### Teardown

```bash
hermes webhook remove artifact-feedback-<slug>
node scripts/agent-feedback-closeout.mjs <artifact.html> --port <port>
```

### Webhook payload

```json
{
  "event": "artifact_feedback_new",
  "count": 1,
  "items": [
    {
      "id": "afw-...",
      "markerId": "af-...",
      "status": "queued",
      "artifactPath": "/page.html",
      "selector": "td:nth-child(2)",
      "visibleText": "Salary (Section 17)",
      "latestUserMessage": "Is this figure correct?",
      "route": "deep_marker_worker",
      "contextTier": "T2",
      "workerLifecycle": "fresh_once"
    }
  ],
  "artifact": "/page.html",
  "timestamp": "2026-05-27T12:00:00.000Z"
}
```

---

## Why two paths

| | File-watch (a) | Hermes webhook (b) |
|---|---|---|
| Harness-agnostic | ✅ | ❌ Hermes-bound |
| Reliability | fs durable; agent restart re-scans | depends on Hermes daemon + webhook receiver |
| Latency | ms (inotify / FSEvents) | ~1 s |
| External deps | none (Node `fs.watch`) | Hermes CLI + gateway |
| Coexist with the other | ✅ orthogonal, both observe the same queue | same |

If you have Hermes, you can run both — the watch script doesn't interfere with the webhook POST. If you don't, the file-watch path is the recommended default for every other harness.

---

## Fallback: No Wake

If neither path is armed, markers still queue durably in `feedback-queue.json`. Process them on demand with `node scripts/agent-feedback-next.mjs --root <serve-root>`. Acceptable for development; not for production operator use.

---

## Environment Variables (server-side, webhook path only)

| Variable | Required | Description |
|---|---|---|
| `AGENT_FEEDBACK_WEBHOOK_URL` | No | URL to POST new feedback events to |
| `AGENT_FEEDBACK_WEBHOOK_SECRET` | No | HMAC-SHA256 signing key |
| `AGENT_FEEDBACK_WEBHOOK_TIMEOUT_MS` | No | Request timeout (default: 2500ms) |
| `PORT` | No | Server port (default: 4177) |
