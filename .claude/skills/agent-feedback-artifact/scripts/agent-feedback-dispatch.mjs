#!/usr/bin/env node
// Claim/route the next queued marker via the feedback server (the single
// authoritative queue writer). With --claim the item is leased + moved to
// "processing"; without --claim it is routed (preview). The server returns the
// item merged with its full route summary (workerPrompt, spawn, dispatch).
import { serverBase, apiJson } from "./feedback-client.mjs";

const args = process.argv.slice(2);
const claim = args.includes("--claim");
const base = serverBase(args);

const data = await apiJson("POST", base, `/api/agent/dispatch?claim=${claim ? "1" : "0"}`);
console.log(JSON.stringify({ item: data.item ?? null }, null, 2));
