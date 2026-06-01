#!/usr/bin/env node
/**
 * agent-feedback-watch.mjs — push-only wake primitive.
 *
 * Watches the queue.json maintained by artifact-feedback-server.mjs.
 * Prints one compact JSON line per NEW marker to stdout. Designed to be the
 * source-of-events for whichever harness adapter the operator's agent runs in:
 *
 *   Claude Code:  Monitor({ command: "node agent-feedback-watch.mjs --root <dir>", persistent: true })
 *                 → each stdout line surfaces as an in-conversation notification.
 *
 *   Any shell:    node agent-feedback-watch.mjs --root <dir> | <your wake adapter>
 *
 *   Hermes:       (orthogonal — Hermes path is the server's webhook POST, this
 *                  script not required.)
 *
 * Wake is push end-to-end: fs.watch → kernel inotify (Linux) / FSEvents (macOS).
 * No polling, no interval, no cron.
 *
 * Backfill: on startup, the script emits any markers already in the queue with
 * status === "queued" that the agent hasn't seen — so restarts don't lose work.
 *
 * Output line shape:
 *   {"id":"afw-...","markerId":"af-...","route":"...","artifactPath":"/","summary":"..."}
 *
 * The agent uses `id` to call agent-feedback-details.mjs / mark.mjs for full
 * context only when it actually wants to act.
 */
import { readFile, writeFile } from "node:fs/promises";
import { watch } from "node:fs";
import { resolve } from "node:path";

// Heartbeat: prove this watcher's loop is alive so agent-feedback-wake-status.mjs
// can tell "watcher running" from "watcher dead". Written to a dotfile the
// fs.watch below ignores (it only reacts to feedback-queue.json), so it never
// self-triggers a scan.
const HEARTBEAT_MS = Number(process.env.AGENT_FEEDBACK_HEARTBEAT_MS || 30_000);

const args = process.argv.slice(2);
let root = "";
for (let i = 0; i < args.length; i++) {
  const a = args[i];
  if (a === "--root") root = args[++i] || "";
  else if (a.startsWith("--root=")) root = a.slice("--root=".length);
}
if (!root) {
  console.error("Usage: agent-feedback-watch.mjs --root <serve-root>");
  process.exit(2);
}

const rootAbs = resolve(root);
const queuePath = resolve(rootAbs, "data", "feedback-queue.json");

const seen = new Set();
let inflight = false;
let pendingTick = false;

async function readQueueSafe() {
  try {
    const txt = await readFile(queuePath, "utf8");
    const parsed = JSON.parse(txt);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

// Origin categorization: lets the agent decide local-app vs external vs github
// vs file in O(1) without parsing the URL each time. Universal capability —
// the widget works on any page, so WHERE the comment came from is decision-
// critical context that belongs in the wake, not behind a details round-trip.
function categorizeOrigin(url) {
  if (!url) return "unknown";
  try {
    const u = new URL(url);
    if (u.protocol === "file:") return "file";
    if (u.protocol === "chrome:" || u.protocol === "about:" || u.protocol === "view-source:") return "blocked";
    const h = u.hostname;
    if (h === "localhost" || h === "127.0.0.1" || h === "0.0.0.0" || h.endsWith(".localhost")) return "localhost";
    if (h === "github.com" || h.endsWith(".github.com") || h === "raw.githubusercontent.com") return "github";
    return "external";
  } catch {
    return "unknown";
  }
}

function summarize(item) {
  const marker = item.marker || item.payload?.comments?.[0] || {};
  const url = marker.url || item.payload?.comments?.[0]?.url || null;
  return {
    id: item.id,
    markerId: item.markerId || marker.markerId || marker.id || null,
    route: item.workerRoute || null,
    status: item.status || null,
    // WHERE — decision-critical for "act directly vs answer vs inspect external"
    url,
    origin: categorizeOrigin(url),
    artifactTitle: item.artifactTitle || marker.title || null,
    artifactPath: item.artifactPath || item.payload?.artifactPath || null,
    // WHAT — operator's words
    summary: (item.latestUserMessage || marker.text || item.visibleText || "").slice(0, 140),
    // The element's own text content — disambiguates deictic summaries like
    // "change this" / "make the number red" without paying a details round-trip.
    // Only included when distinct from `summary` (avoids duplicating the same
    // string when operator's comment IS the visible text).
    visibleText: (() => {
      const v = (item.visibleText || marker.selectedText || marker.elementText || "").trim().slice(0, 60);
      const s = (item.latestUserMessage || "").trim();
      return v && v !== s ? v : null;
    })(),
    // Timing instrumentation — let the agent measure each segment.
    sentAt: item.sentAt || item.payload?.sentAt || null,           // T0 — widget Send click
    createdAt: item.createdAt || null,                              // T1 — server persisted queue.json
    emittedAt: new Date().toISOString()                             // T2 — watch script emitted this line
  };
}

async function scan() {
  if (inflight) { pendingTick = true; return; }
  inflight = true;
  try {
    const items = await readQueueSafe();
    for (const item of items) {
      if (!item || !item.id) continue;
      // Key `seen` on id+status so a marker REQUEUED by the durability sweep
      // (processing → queued) fires a fresh wake. When an item leaves "queued"
      // (claimed/terminal), drop its queued key so a later reclaim re-emits
      // exactly once. Only "queued" items are ever pushed to stdout.
      if (item.status !== "queued") seen.delete(`${item.id}:queued`);
      const key = `${item.id}:${item.status}`;
      const isNew = !seen.has(key);
      seen.add(key);
      if (isNew && item.status === "queued") {
        process.stdout.write(JSON.stringify(summarize(item)) + "\n");
      }
    }
  } finally {
    inflight = false;
    if (pendingTick) {
      pendingTick = false;
      // micro-debounce — coalesce rapid writes into one scan
      setTimeout(() => scan(), 25);
    }
  }
}

const heartbeatPath = resolve(rootAbs, "data", ".wake-heartbeat");
async function beat() {
  try { await writeFile(heartbeatPath, new Date().toISOString()); } catch { /* non-fatal */ }
}

// Backfill on startup so restarts don't drop *queued* markers.
await scan();
await beat();
const heartbeatTimer = setInterval(beat, HEARTBEAT_MS);
heartbeatTimer.unref?.();

// fs.watch on the parent dir — watching the file directly is unreliable across
// atomic-rename writes (which is exactly how artifact-feedback-server.mjs writes
// the queue, via writeJson tmp → rename). Watching the dir catches the rename.
const watcher = watch(resolve(rootAbs, "data"), { persistent: true }, (_event, filename) => {
  if (filename === "feedback-queue.json") scan();
});

watcher.on("error", (err) => {
  console.error("[agent-feedback-watch] fs.watch error:", err.message);
  process.exit(1);
});

process.on("SIGTERM", () => { clearInterval(heartbeatTimer); watcher.close(); process.exit(0); });
process.on("SIGINT",  () => { clearInterval(heartbeatTimer); watcher.close(); process.exit(0); });
