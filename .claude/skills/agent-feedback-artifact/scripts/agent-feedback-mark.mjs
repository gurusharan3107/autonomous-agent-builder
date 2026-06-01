#!/usr/bin/env node
// Update a marker's status + agent reply via the feedback server (the single
// authoritative queue writer). The server applies the terminal-state guard,
// lease bookkeeping, and reload signalling.
import { serverBase, apiJson } from "./feedback-client.mjs";

const args = process.argv.slice(2);
const [id, status] = args.filter((a) => !a.startsWith("--"));
if (!id || !status) {
  console.error("Usage: scripts/agent-feedback-mark.mjs <work-id> <status> [agent-message] [--summary <thread-summary>] [--reload | --reload-full] [--port <port> | --url <base>]");
  process.exit(2);
}

const summaryIndex = args.indexOf("--summary");
const positional = args.slice(2).filter((a) => !a.startsWith("--"));
const messageParts = summaryIndex >= 0
  ? positional.slice(0, positional.length - (args.slice(summaryIndex + 1).filter((a) => !a.startsWith("--")).length))
  : positional;
const explicitSummary = summaryIndex >= 0 ? args.slice(summaryIndex + 1).filter((a) => !a.startsWith("--")).join(" ") : "";
// Two-tier reload semantics:
//   --reload      → CSS hot-swap (instant, no state loss). Default for style fixes.
//   --reload-full → full page reload (location.replace). Use for HTML/template edits.
const reloadFlag = args.includes("--reload") || args.includes("--reload-full");
const reloadMode = args.includes("--reload-full") ? "full" : (reloadFlag ? "css" : null);

const base = serverBase(args);
const body = { status, agentMessage: messageParts.join(" ") };
if (explicitSummary) body.threadSummary = explicitSummary;
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
