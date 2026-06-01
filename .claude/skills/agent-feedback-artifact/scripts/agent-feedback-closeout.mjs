#!/usr/bin/env node
import { readFile, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { basename, dirname, resolve } from "node:path";
import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

const args = process.argv.slice(2);
const targetArg = args.find((arg) => !arg.startsWith("--"));
const port = Number(valueFor("--port") || 4177);
const clearLocalQueue = args.includes("--clear-local-queue");

if (!targetArg) {
  console.error("Usage: scripts/agent-feedback-closeout.mjs <artifact.html> [--port 4177] [--clear-local-queue]");
  process.exit(2);
}

const target = resolve(process.cwd(), targetArg);
const root = dirname(target);
const artifactPath = `/${basename(target)}`;
const queuePath = resolve(root, "data", "feedback-queue.json");
const html = await readFile(target, "utf8").catch((error) => fail(`target_read_failed: ${error.message}`));
const widgetInstalled = html.includes("AGENT_FEEDBACK_WIDGET_START") && html.includes("AGENT_FEEDBACK_WIDGET_END");
const serverListening = await isListening(port);
const webhookUrl = process.env.AGENT_FEEDBACK_WEBHOOK_URL || "";
let queue = [];
let queueReadable = false;

if (existsSync(queuePath)) {
  queue = JSON.parse(await readFile(queuePath, "utf8"));
  queueReadable = true;
}

const matching = queue.filter((item) => artifactPathFor(item) === artifactPath);
const counts = countByStatus(matching);
let cleared = false;

if (clearLocalQueue) {
  if (!isTestDuplicate(target)) {
    fail("--clear-local-queue is allowed only for test/verify/smoke/roundtrip duplicate artifacts");
  }
  const remaining = queue.filter((item) => artifactPathFor(item) !== artifactPath);
  await writeFile(queuePath, `${JSON.stringify(remaining, null, 2)}\n`);
  cleared = true;
}

// ── Optimize step ──────────────────────────────────────────────────────────
// Surface evidence + a disconfirming triage so the agent reviews the session
// before tearing down. The script computes deterministic signals; the agent
// answers the judgment (code fix vs skill how-to-operate vs both).
const nowMs = Date.now();
const processingItems = matching.filter((i) => i.status === "processing");
const staleProcessing = processingItems.filter((i) => i.leaseUntil && Date.parse(i.leaseUntil) < nowMs).length;
const unleasedProcessing = processingItems.filter((i) => !i.leaseUntil).length;
const blockedItems = matching.filter((i) => i.status === "blocked");
const reclaimedItems = matching.filter((i) => i.reclaimReason);

// Reuse the wake-status verdict (it exits 1 on rearm_required but still prints JSON).
let wake = null;
try {
  const { stdout } = await execFileAsync("node", [resolve(import.meta.dirname, "agent-feedback-wake-status.mjs"), "--root", root]);
  wake = JSON.parse(stdout);
} catch (error) {
  if (error.stdout) { try { wake = JSON.parse(error.stdout); } catch { /* leave null */ } }
}

// Auto-derived signals worth a LOOK — candidates to judge, not mandates to act on.
const signalNotes = [];
if (wake?.rearm) signalNotes.push(`WAKE ${wake.verdict}: ${wake.reason} — the push path failed to deliver (observed).`);
if (staleProcessing) signalNotes.push(`${staleProcessing} marker(s) past their lease still 'processing' — orphan risk if the sweep isn't running.`);
if (unleasedProcessing) signalNotes.push(`${unleasedProcessing} 'processing' marker(s) have no lease (pre-supervisor) — won't auto-reclaim. May be intentional (parked work) — judge.`);
if (blockedItems.length) signalNotes.push(`${blockedItems.length} 'blocked' marker(s) await an operator decision — confirm each surfaced a reason visibly.`);
if (reclaimedItems.length) signalNotes.push(`${reclaimedItems.length} marker(s) were reclaimed (a worker died mid-flight) — worth asking why.`);

// State alone never PROVES optimization is needed — it only flags what to look
// at. The model must self-introspect on the SESSION (operator corrections,
// surprises, repeated mistakes — none of which this script can see) and decide.
// Default for an obviously-clean session: change nothing. Do not manufacture work.
const stateClean = signalNotes.length === 0;
const optimize = {
  verdict: stateClean ? "state_clean_no_action_indicated" : "signals_to_review",
  selfIntrospect: "Reflect on THIS session, not just the state below: did the operator correct you, did anything surprise you, did a mistake recur? That judgment — not this script — decides whether to optimize and what step to take.",
  signals: { statusCounts: counts, staleProcessing, unleasedProcessing, blocked: blockedItems.length, reclaimed: reclaimedItems.length, oldestQueuedAgeSec: wake?.oldestQueuedAgeSec ?? null },
  wake,
  signalNotes,
  // Progressive disclosure: the triage steps + questions live in optimize.md;
  // load them only when there's actually something to review.
  next: stateClean
    ? "No state signals. If your session introspection also finds nothing real, close out and change nothing. Otherwise load references/optimize.md -> 'Optimize step' and triage."
    : "Load references/optimize.md -> 'Optimize step' and judge each signal/finding there (Q2 routes code-vs-skill). Some signals may be intentional — skip non-issues."
};

const report = {
  ok: true,
  target,
  artifactPath,
  widgetInstalled,
  server: {
    port,
    listening: serverListening
  },
  webhook: {
    configured: Boolean(webhookUrl),
    url: webhookUrl || null,
    timeoutMs: Number(process.env.AGENT_FEEDBACK_WEBHOOK_TIMEOUT_MS || 2500),
    signingConfigured: Boolean(process.env.AGENT_FEEDBACK_WEBHOOK_SECRET)
  },
  queue: {
    path: queuePath,
    readable: queueReadable,
    totalForArtifact: matching.length,
    counts,
    cleared
  },
  cleanupCommands: {
    removeCapability: `node ${resolve(import.meta.dirname, "remove-agent-feedback.mjs")} ${target}`,
    clearLocalQueue: `node ${resolve(import.meta.dirname, "agent-feedback-closeout.mjs")} ${target} --port ${port} --clear-local-queue`
  },
  agentReminders: {
    taskStopMonitor: "If you armed a Monitor on agent-feedback-watch.mjs during step 4 of the operating sequence, call TaskStop on that handle now. The closeout report cannot end the Monitor itself — only the agent that owns the task ID can.",
    stopServer: serverListening
      ? `Server still listening on port ${port}. Identify the PID with 'lsof -nP -iTCP:${port} -sTCP:LISTEN' and stop it (or kill the background task that started it). Closeout does not auto-kill processes it didn't start.`
      : null
  },
  optimize
};

console.log(JSON.stringify(report, null, 2));

function valueFor(name) {
  const index = args.indexOf(name);
  return index >= 0 ? args[index + 1] : null;
}

function fail(message) {
  console.error(message);
  process.exit(1);
}

function artifactPathFor(item) {
  return item.artifactPath || item.payload?.artifactPath;
}

function countByStatus(items) {
  return items.reduce((acc, item) => {
    const status = item.status || "unknown";
    acc[status] = (acc[status] || 0) + 1;
    return acc;
  }, { queued: 0, processing: 0, done: 0, blocked: 0, canceled: 0 });
}

function isTestDuplicate(path) {
  return /(test|smoke|verify|roundtrip|duplicate|clear)/i.test(basename(path));
}

function isListening(portNumber) {
  return execFileAsync("lsof", ["-nP", `-iTCP:${portNumber}`, "-sTCP:LISTEN"])
    .then(({ stdout }) => stdout.trim().split("\n").length > 1)
    .catch(() => false);
}
