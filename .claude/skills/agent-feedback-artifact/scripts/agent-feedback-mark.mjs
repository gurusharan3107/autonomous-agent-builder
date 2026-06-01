#!/usr/bin/env node
// Update a marker's status + agent reply via the feedback server (the single
// authoritative queue writer). The server applies the terminal-state guard,
// lease bookkeeping, and reload signalling.
import { serverBase, apiJson } from "./feedback-client.mjs";

const args = process.argv.slice(2);

// Split positionals from flags. Value-taking flags CONSUME their next arg, so a
// flag value (e.g. the --port number) never leaks into the agent message.
const VALUE_FLAGS = new Set(["--summary", "--port", "--url", "--root"]);
const positionals = [];
const flags = {};
for (let i = 0; i < args.length; i++) {
  const a = args[i];
  if (VALUE_FLAGS.has(a)) flags[a] = args[++i];
  else if (a.startsWith("--")) flags[a] = true;
  else positionals.push(a);
}
const [id, status, ...messageWords] = positionals;
if (!id || !status) {
  console.error("Usage: scripts/agent-feedback-mark.mjs <work-id> <status> [agent-message] [--summary <thread-summary>] [--reload | --reload-full] [--port <port> | --url <base>]");
  process.exit(2);
}

// Two-tier reload: --reload → CSS hot-swap; --reload-full → full page reload.
const reloadFlag = "--reload" in flags || "--reload-full" in flags;
const reloadMode = "--reload-full" in flags ? "full" : (reloadFlag ? "css" : null);

const base = serverBase(args);
const body = { status, agentMessage: messageWords.join(" ") };
if (flags["--summary"]) body.threadSummary = flags["--summary"];
if (reloadFlag) { body.reload = true; body.reloadMode = reloadMode; }

const data = await apiJson("POST", base, `/api/agent/status/${encodeURIComponent(id)}`, body);
console.log(JSON.stringify({
  id: data.id ?? id,
  markerId: data.markerId ?? null,
  status: data.status ?? status,
  workerStatus: data.workerStatus ?? status,
  reload: Boolean(data.reload),
  reloadMode: data.reloadMode ?? null
}, null, 2));
