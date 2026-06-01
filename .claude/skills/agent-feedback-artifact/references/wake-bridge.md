# Wake Bridge — push the agent on new markers

Two decoupled layers: a harness-agnostic wire format + a per-harness wake adapter.

```
operator comments → widget POST /api/feedback → server writes queue.json (DURABLE)
  ├─ (a) fs.watch → agent-feedback-watch.mjs prints one JSON line → harness adapter (Monitor/tail/exec)
  └─ (b) server POSTs AGENT_FEEDBACK_WEBHOOK_URL (if set) → webhook receiver
```

(a) = Claude Code + most harnesses; (b) = Hermes. They coexist — both observe the same queue.

## (a) File-watch + Monitor (Claude Code default)

Push end-to-end via inotify/FSEvents, zero polling. Arm in operating-sequence step 4:
```
Monitor({ description:"agent-feedback markers from <slug>", persistent:true,
  command:"node ~/.claude/skills/agent-feedback-artifact/scripts/agent-feedback-watch.mjs --root <serve-root>" })
```
Each new marker → one ~140-char line: `{"id":"afw-...","markerId":"af-...","route":"...","status":"queued","artifactPath":"/","summary":"..."}`. Surfaces as a notification. Act on the summary, or pull `agent-feedback-details.mjs <id>` (style routes rarely need it).

- **Backfill:** on (re)start, every `status:"queued"` item is re-emitted once — restarts don't drop work.
- **Wake can die silently** (Monitor auto-stop / orphaned watcher) → run `agent-feedback-wake-status.mjs` at entry (SKILL.md / operate.md step 4); the watcher writes `data/.wake-heartbeat`.
- **Disarm at closeout:** `TaskStop` the handle, then `agent-feedback-closeout.mjs`.

### Auto-refresh tiers (mark.mjs → widget)
| Flag | Effect | Use when |
|---|---|---|
| `--reload` | CSS hot-swap (cache-bust `<link>`s, ~400–700 ms, no state loss) | CSS/style edits — dominant case |
| `--reload-full` | Full reload (`location.replace` + cache-bust); resets JS state | HTML/template/JSX/Jinja edits |
| *(none)* | Reply only | question replies / operator decides |

Widget reads `reloadMode` from `/api/feedback/status` (`css`|`full`); across a batch `full` wins.

## (a') File-watch + any harness
```bash
node ~/.claude/skills/agent-feedback-artifact/scripts/agent-feedback-watch.mjs --root <serve-root> | <your wake bridge>
```
e.g. `while read line; do my-cli notify "$line"; done`, a sentinel-file writer, or a Slack/email forwarder.

## (b) Hermes webhook

`AGENT_FEEDBACK_WEBHOOK_URL` set → server POSTs each new marker (HMAC-SHA256 signed when `AGENT_FEEDBACK_WEBHOOK_SECRET` set).
```bash
hermes gateway setup   # or add platforms.webhook to config.yaml
hermes webhook subscribe artifact-feedback-<slug> \
  --prompt "New feedback on {artifactPath}. Work {items[0].id}, Route {items[0].route}, Marker {items[0].visibleText}, Msg {items[0].latestUserMessage}. Use agent-feedback-artifact; dispatch to claim, then process per route." \
  --skills "agent-feedback-artifact" --deliver origin --events "artifact_feedback_new"
# start server with the returned URL + secret:
AGENT_FEEDBACK_WEBHOOK_URL=".../hooks/artifact-feedback-<slug>" \
AGENT_FEEDBACK_WEBHOOK_SECRET="$(hermes webhook list --json | jq -r '.[]|select(.name=="artifact-feedback-<slug>").secret')" \
  node scripts/artifact-feedback-server.mjs <serve-root> <port>
# teardown: hermes webhook remove artifact-feedback-<slug> ; then closeout
```
Payload: `{event:"artifact_feedback_new", count, items:[{id, markerId, status, artifactPath, selector, visibleText, latestUserMessage, route, contextTier, workerLifecycle}], artifact, timestamp}`.

## (a) vs (b)
| | File-watch (a) | Hermes webhook (b) |
|---|---|---|
| Harness-agnostic | ✅ | ❌ Hermes-bound |
| Reliability | fs durable; restart re-scans | needs Hermes daemon + receiver |
| Latency | ms | ~1 s |
| Deps | none | Hermes CLI + gateway |

Run both if you have Hermes (orthogonal); else (a) is the default.

## Fallback: no wake
Neither armed → markers still queue durably; process on demand with `agent-feedback-next.mjs --root <serve-root>`. Dev-only, not production.

## Env vars (server-side, webhook path)
| Var | Default | Purpose |
|---|---|---|
| `AGENT_FEEDBACK_WEBHOOK_URL` | — | POST target for new events |
| `AGENT_FEEDBACK_WEBHOOK_SECRET` | — | HMAC-SHA256 signing key |
| `AGENT_FEEDBACK_WEBHOOK_TIMEOUT_MS` | 2500 | request timeout |
| `PORT` | 4177 | server port |
