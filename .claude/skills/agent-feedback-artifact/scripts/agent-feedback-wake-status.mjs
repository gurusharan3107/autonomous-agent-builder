#!/usr/bin/env node
// Self-healing wake check. The push path (watcher → Monitor → agent) can die
// silently mid-session (e.g. the harness auto-stops a Monitor that emitted too
// many events), leaving markers durably queued but undelivered. The agent runs
// this at session entry and whenever it suspects staleness; on a `rearm`
// verdict it re-arms the Monitor (which backfills the queued backlog).
//
// Two signals, because neither alone is sufficient:
//   - undelivered-backlog age: a marker sitting `queued` past --backlog-stale-sec
//     means the wake FAILED to deliver (the strongest, symptom-level signal; it
//     catches the orphaned-watcher case where the process is alive but its
//     Monitor is dead).
//   - watcher heartbeat: data/.wake-heartbeat freshness proves the watcher loop
//     is running at all (catches "no watcher / watcher crashed").
//
// Usage: agent-feedback-wake-status.mjs --root <serve-root>
//        [--backlog-stale-sec 90] [--heartbeat-stale-sec 75]
import { readFile, stat } from "node:fs/promises";
import { resolve } from "node:path";

const args = process.argv.slice(2);
const val = (name, def) => { const i = args.indexOf(name); return i >= 0 ? args[i + 1] : def; };
const root = resolve(val("--root", process.cwd()));
const backlogStaleSec = Number(val("--backlog-stale-sec", 90));
const heartbeatStaleSec = Number(val("--heartbeat-stale-sec", 75));

const dataDir = resolve(root, "data");
const queuePath = resolve(dataDir, "feedback-queue.json");
const heartbeatPath = resolve(dataDir, ".wake-heartbeat");
const now = Date.now();

let queue = [];
try { const t = await readFile(queuePath, "utf8"); const p = JSON.parse(t); queue = Array.isArray(p) ? p : []; } catch { queue = []; }

const queued = queue.filter((it) => it && it.status === "queued");
const ageSec = (iso) => { const t = Date.parse(iso || ""); return Number.isFinite(t) ? Math.round((now - t) / 1000) : null; };
const oldestQueuedAgeSec = queued.reduce((max, it) => {
  const a = ageSec(it.createdAt);
  return a != null && a > max ? a : max;
}, 0);
const processingCount = queue.filter((it) => it && it.status === "processing").length;

let watcherHeartbeatAgeSec = null;
try { const s = await stat(heartbeatPath); watcherHeartbeatAgeSec = Math.round((now - s.mtimeMs) / 1000); } catch { watcherHeartbeatAgeSec = null; }

const watcherStale = watcherHeartbeatAgeSec == null || watcherHeartbeatAgeSec > heartbeatStaleSec;
const backlogStalled = queued.length > 0 && oldestQueuedAgeSec > backlogStaleSec;

let verdict, reason;
if (backlogStalled) {
  verdict = "rearm_required";
  reason = `${queued.length} marker(s) queued, oldest ${oldestQueuedAgeSec}s old (> ${backlogStaleSec}s) — the wake did not deliver`;
} else if (watcherStale) {
  verdict = "rearm_required";
  reason = watcherHeartbeatAgeSec == null
    ? "no watcher heartbeat — watcher not running"
    : `watcher heartbeat ${watcherHeartbeatAgeSec}s stale (> ${heartbeatStaleSec}s) — watcher loop not alive`;
} else if (queued.length > 0) {
  verdict = "backlog_fresh";
  reason = `${queued.length} marker(s) queued (fresh); a live wake should deliver imminently — process them`;
} else {
  verdict = "ok";
  reason = "no backlog; watcher heartbeat fresh";
}

const rearm = verdict === "rearm_required";
const rearmHint = rearm
  ? "pkill -f agent-feedback-watch.mjs ; then arm a fresh persistent Monitor on: node scripts/agent-feedback-watch.mjs --root <serve-root> ; the new watcher backfills all queued markers"
  : null;

console.log(JSON.stringify({
  verdict, rearm, reason,
  queuedCount: queued.length,
  oldestQueuedAgeSec,
  processingCount,
  watcherHeartbeatAgeSec,
  rearmHint
}, null, 2));
process.exit(rearm ? 1 : 0);
