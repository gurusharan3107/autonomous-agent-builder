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
import { readFile } from "node:fs/promises";
import { watch } from "node:fs";
import { resolve } from "node:path";

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

function summarize(item) {
  const marker = item.marker || item.payload?.comments?.[0] || {};
  return {
    id: item.id,
    markerId: item.markerId || marker.markerId || marker.id || null,
    route: item.workerRoute || null,
    status: item.status || null,
    artifactPath: item.artifactPath || item.payload?.artifactPath || null,
    summary: (item.latestUserMessage || marker.text || item.visibleText || "").slice(0, 140),
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
      const isNew = !seen.has(item.id);
      // Only actionable (queued) items fire — done/canceled/processing markers
      // are noise after a restart. Record them as seen so we don't re-emit if
      // their status later flaps, but never push them to stdout.
      seen.add(item.id);
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

// Backfill on startup so restarts don't drop *queued* markers.
await scan();

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

process.on("SIGTERM", () => { watcher.close(); process.exit(0); });
process.on("SIGINT",  () => { watcher.close(); process.exit(0); });
