#!/usr/bin/env node
// `close` lane (distinct from `closeout`): tear down the running feedback
// server. Closeout stays report-only by design; close actually stops things.
//
// Split of responsibility — close stops what a script CAN stop:
//   • Feedback server  → scriptable here: SIGTERM the listener on <port>
//                         (the server traps SIGTERM and calls server.close()),
//                         SIGKILL any straggler.
//   • Monitor (wake)   → NOT scriptable. A harness Task can only be ended by
//                         the agent that owns its handle via TaskStop. This
//                         script reports the reminder; the SKILL.md `close`
//                         lane has the agent make that call.
import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
const args = process.argv.slice(2);
const port = Number(valueFor("--port") || process.env.AGENT_FEEDBACK_PORT || 4177);
const force = args.includes("--force"); // skip the graceful SIGTERM wait

const pids = await listenerPids(port);

if (pids.length === 0) {
  console.log(JSON.stringify({
    ok: true,
    port,
    serverWasRunning: false,
    killed: [],
    note: "No listener on this port — server already stopped.",
    monitorReminder: monitorReminder()
  }, null, 2));
  process.exit(0);
}

const killed = [];
for (const pid of pids) {
  signal(pid, force ? "SIGKILL" : "SIGTERM");
  killed.push({ pid, signal: force ? "SIGKILL" : "SIGTERM" });
}

// Graceful path: give the trapped SIGTERM a moment to close the socket, then
// SIGKILL anything still bound to the port.
if (!force) {
  await sleep(1200);
  const survivors = await listenerPids(port);
  for (const pid of survivors) {
    signal(pid, "SIGKILL");
    killed.push({ pid, signal: "SIGKILL" });
  }
}

const stillListening = (await listenerPids(port)).length > 0;

console.log(JSON.stringify({
  ok: !stillListening,
  port,
  serverWasRunning: true,
  killed,
  stillListening,
  note: stillListening
    ? `Port ${port} still has a listener after SIGKILL — inspect 'lsof -nP -iTCP:${port} -sTCP:LISTEN' manually.`
    : "Feedback server stopped.",
  monitorReminder: monitorReminder()
}, null, 2));

process.exit(stillListening ? 1 : 0);

function monitorReminder() {
  return "Server only. If you armed a Monitor on agent-feedback-watch.mjs, call TaskStop on that handle now — a script cannot end a harness Task; only the owning agent can.";
}

function valueFor(name) {
  const i = args.indexOf(name);
  return i >= 0 ? args[i + 1] : null;
}

function signal(pid, sig) {
  try { process.kill(pid, sig); } catch { /* already gone */ }
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

// PIDs holding a LISTEN socket on the port. lsof -t prints one PID per line.
async function listenerPids(portNumber) {
  try {
    const { stdout } = await execFileAsync("lsof", ["-t", "-nP", `-iTCP:${portNumber}`, "-sTCP:LISTEN"]);
    return [...new Set(stdout.trim().split("\n").filter(Boolean).map(Number))];
  } catch {
    return []; // lsof exits non-zero when nothing matches
  }
}
