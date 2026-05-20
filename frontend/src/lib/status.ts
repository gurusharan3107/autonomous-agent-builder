export type StatusTone = "active" | "review" | "pending" | "done" | "blocked" | "muted";

export type DesignStatusKey =
  | "ready"
  | "running"
  | "active"
  | "implementation"
  | "planning"
  | "design"
  | "review"
  | "review_pending"
  | "answered"
  | "approved"
  | "denied"
  | "design_review"
  | "pending"
  | "done"
  | "success"
  | "pass"
  | "blocked"
  | "failed"
  | "fail"
  | "warn";

export const STATUS_LABEL: Record<DesignStatusKey, string> = {
  ready: "Ready",
  active: "Active",
  running: "Running",
  implementation: "Implementation",
  planning: "Planning",
  design: "Designing",
  review: "In review",
  design_review: "Design review",
  review_pending: "Needs review",
  answered: "Answered",
  approved: "Approved",
  denied: "Denied",
  pending: "Queued",
  done: "Shipped",
  success: "Success",
  blocked: "Blocked",
  failed: "Failed",
  warn: "Warn",
  pass: "Pass",
  fail: "Fail",
};

export const STATUS_TONE_MAP: Record<DesignStatusKey, StatusTone> = {
  ready: "muted",
  active: "active",
  running: "active",
  implementation: "active",
  planning: "active",
  design: "active",
  review: "review",
  design_review: "review",
  review_pending: "review",
  answered: "done",
  approved: "done",
  denied: "blocked",
  warn: "review",
  pending: "pending",
  done: "done",
  success: "done",
  pass: "done",
  blocked: "blocked",
  failed: "blocked",
  fail: "blocked",
};

export const ACTIVE_STATUSES = new Set([
  "active",
  "running",
  "implementation",
  "planning",
  "design",
]);

export function normalizeStatusForDisplay(status: string, active = false): DesignStatusKey {
  switch (status) {
    case "queued":
    case "pending":
      return "pending";
    case "running":
    case "ready":
    case "planning":
    case "design":
    case "design_review":
    case "implementation":
    case "review_pending":
    case "answered":
    case "approved":
    case "done":
    case "success":
    case "pass":
    case "blocked":
    case "failed":
    case "fail":
    case "warn":
    case "active":
      return status;
    case "quality_gates":
    case "pr_creation":
    case "build_verify":
      return active ? "running" : "review";
    case "completed":
      return "done";
    case "allow":
    case "allowed":
      return "approved";
    case "deny":
    case "denied":
    case "rejected":
      return "denied";
    case "passed":
      return "pass";
    case "capability_limit":
      return "blocked";
    case "timeout":
    case "error":
      return "failed";
    default:
      return "pending";
  }
}

export function toStatusTone(status: string, active = false): StatusTone {
  return STATUS_TONE_MAP[normalizeStatusForDisplay(status, active)] ?? "pending";
}
