#!/usr/bin/env node
// Unit tests for the durability supervisor's pure reclaim logic.
// Run: node scripts/test-agent-feedback-supervisor.mjs
import { reclaimExpired } from "./agent-feedback-routing.mjs";

let failures = 0;
function check(name, cond) {
  if (cond) { console.log(`  ok   ${name}`); }
  else { console.error(`  FAIL ${name}`); failures++; }
}

const NOW = Date.parse("2026-06-01T12:00:00.000Z");
const past = new Date(NOW - 60_000).toISOString();   // 1 min ago (expired)
const future = new Date(NOW + 60_000).toISOString(); // 1 min ahead (valid)

// 1. Expired processing under maxAttempts → requeued.
{
  const q = [{ id: "a", status: "processing", attempts: 1, leaseUntil: past }];
  const changed = reclaimExpired(q, NOW, { maxAttempts: 3 });
  check("expired+attempts<N → changed", changed === true);
  check("expired+attempts<N → queued", q[0].status === "queued");
  check("expired+attempts<N → lease cleared", q[0].leaseUntil === null);
  check("expired+attempts<N → reclaimReason set", /requeued/.test(q[0].reclaimReason || ""));
}

// 2. Expired processing at/over maxAttempts → blocked (terminal).
{
  const q = [{ id: "b", status: "processing", attempts: 3, leaseUntil: past, marker: { id: "b", messages: [] } }];
  const changed = reclaimExpired(q, NOW, { maxAttempts: 3 });
  check("poison → changed", changed === true);
  check("poison → blocked", q[0].status === "blocked");
  check("poison → lastProcessedAt set (terminal)", typeof q[0].lastProcessedAt === "string");
  check("poison → reclaimReason mentions attempts", /attempts/.test(q[0].reclaimReason || ""));
  check("poison → agentMessage surfaced", Boolean(q[0].agentMessage));
}

// 3. Valid (future) lease → untouched.
{
  const q = [{ id: "c", status: "processing", attempts: 1, leaseUntil: future }];
  const changed = reclaimExpired(q, NOW, { maxAttempts: 3 });
  check("valid lease → unchanged", changed === false && q[0].status === "processing");
}

// 4. Legacy item (no leaseUntil) → never reclaimed.
{
  const q = [{ id: "d", status: "processing", attempts: 0, leaseUntil: null }];
  const changed = reclaimExpired(q, NOW, { maxAttempts: 3 });
  check("legacy (null lease) → unchanged", changed === false && q[0].status === "processing");
}

// 5. Non-processing items ignored.
{
  const q = [
    { id: "e", status: "queued", leaseUntil: past },
    { id: "f", status: "done", leaseUntil: past }
  ];
  const changed = reclaimExpired(q, NOW, { maxAttempts: 3 });
  check("non-processing → unchanged", changed === false && q[0].status === "queued" && q[1].status === "done");
}

if (failures) { console.error(`\n${failures} assertion(s) failed`); process.exit(1); }
console.log("\nall supervisor assertions passed");
