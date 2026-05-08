export type StatusTone = "active" | "review" | "pending" | "done" | "blocked" | "muted";

export const STATUS_LABEL: Record<string, string> = {
  active: "Active",
  running: "Running",
  implementation: "Implementing",
  planning: "Planning",
  design: "Designing",
  design_review: "Design review",
  quality_gates: "Quality gates",
  pr_creation: "PR creation",
  review_pending: "Needs review",
  build_verify: "Build verify",
  pending: "Queued",
  done: "Shipped",
  success: "Success",
  completed: "Completed",
  blocked: "Blocked",
  failed: "Failed",
  capability_limit: "Capability limit",
  warn: "Warn",
  pass: "Pass",
  passed: "Passed",
  fail: "Fail",
  timeout: "Timeout",
  error: "Error",
};

export const STATUS_TONE_MAP: Record<string, StatusTone> = {
  active: "active",
  running: "active",
  implementation: "active",
  planning: "active",
  design: "active",
  design_review: "review",
  quality_gates: "review",
  pr_creation: "review",
  review_pending: "review",
  build_verify: "review",
  warn: "review",
  pending: "pending",
  done: "done",
  completed: "done",
  success: "done",
  pass: "done",
  passed: "done",
  blocked: "blocked",
  failed: "blocked",
  fail: "blocked",
  capability_limit: "blocked",
  timeout: "blocked",
  error: "blocked",
};

export const ACTIVE_STATUSES = new Set([
  "active",
  "running",
  "implementation",
  "planning",
  "design",
]);

export function toStatusTone(status: string): StatusTone {
  return STATUS_TONE_MAP[status] ?? "pending";
}
