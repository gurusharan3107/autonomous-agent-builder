#!/usr/bin/env node
import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { summarizeThread } from "./agent-feedback-routing.mjs";

const args = process.argv.slice(2);
const [id, status] = args.filter((a) => !a.startsWith("--"));
if (!id || !status) {
  console.error("Usage: scripts/agent-feedback-mark.mjs <work-id> <status> [agent-message] [--summary <thread-summary>] [--reload | --reload-full] [--root <data-root>]");
  process.exit(2);
}

const summaryIndex = args.indexOf("--summary");
const positional = args.slice(2).filter((a) => !a.startsWith("--"));
const messageParts = summaryIndex >= 0
  ? positional.slice(0, positional.length - (args.slice(summaryIndex + 1).filter((a) => !a.startsWith("--")).length))
  : positional;
const explicitSummary = summaryIndex >= 0 ? args.slice(summaryIndex + 1).filter((a) => !a.startsWith("--")).join(" ") : "";
const root = resolve(valueFor("--root") || process.cwd());
// Two-tier reload semantics:
//   --reload         → CSS hot-swap (instant, no state loss). Default for style fixes.
//   --reload-full    → full page reload (location.replace). Use for HTML/template edits.
// reload-full implies reload (the more specific wins).
const reloadFlag = args.includes("--reload") || args.includes("--reload-full");
const reloadMode = args.includes("--reload-full") ? "full" : (reloadFlag ? "css" : null);
const queuePath = resolve(root, "data", "feedback-queue.json");
const queue = JSON.parse(await readFile(queuePath, "utf8"));
const item = queue.find((entry) => entry.id === id);

if (!item) {
  console.error(`Feedback batch not found: ${id}`);
  process.exit(1);
}

item.status = status;
item.workerStatus = status;
item.agentMessage = messageParts.join(" ");
if (explicitSummary) item.threadSummary = explicitSummary;
if (["done", "blocked", "canceled"].includes(status)) {
  item.lastProcessedAt = new Date().toISOString();
  if (!item.threadSummary) item.threadSummary = summarizeThread(item, item.agentMessage);
}
if (reloadFlag) {
  item.reload = true;
  item.reloadMode = reloadMode;  // "css" | "full"
}
item.updatedAt = new Date().toISOString();
await writeFile(queuePath, `${JSON.stringify(queue, null, 2)}\n`);
console.log(JSON.stringify({
  id: item.id,
  markerId: item.markerId || item.marker?.id || item.payload?.comments?.[0]?.id,
  status: item.status,
  workerStatus: item.workerStatus,
  reload: Boolean(item.reload),
  reloadMode: item.reloadMode || null
}, null, 2));

function valueFor(name) {
  const index = args.indexOf(name);
  return index >= 0 ? args[index + 1] : null;
}
