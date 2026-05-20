import type { TimelineEntry } from "@/components/agent-native";
import type { TaskActivityEvent, TaskAgentRunSummary, TaskBoardItem } from "@/lib/types";

export interface AgentStatus {
  running: boolean;
  model?: string;
  effort?: string;
  runtime_sdk?: string;
  provider?: string;
  current_turn?: number;
  max_turns?: number;
  tokens_used?: number;
  cost_usd?: number;
  observability?: Record<string, unknown>;
  error?: string;
  stop_reason?: string;
}

export interface TimelineItem {
  id: string;
  type: string;
  status: string;
  timestamp: string;
  payload: Record<string, unknown>;
}

export interface DiagnosticSummary {
  kind?: string;
  outcome?: string;
  tool_name?: string;
  input_focus?: string;
  summary?: string;
  detail?: string;
  error_message?: string;
  next_action?: string;
  raw_response?: string;
}

export interface HistoryResponse {
  session_id?: string;
  model?: string;
  effort?: string;
  runtime_sdk?: string;
  provider?: string;
  repo_identity: string;
  workspace_cwd: string;
  items: TimelineItem[];
  status?: AgentStatus | null;
}

export interface ChatResponse {
  response: string;
  session_id?: string;
  model?: string;
  effort?: string;
  runtime_sdk?: string;
  provider?: string;
  status?: AgentStatus;
}

export interface ChatRespondResponse {
  ok: boolean;
  session_id: string;
  event_id: string;
}

export interface SessionListItem {
  id: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  preview: string;
  workspace_cwd?: string | null;
  is_resume_candidate: boolean;
}

export interface SessionListResponse {
  repo_identity: string;
  workspace_cwd: string;
  latest_resume_session_id?: string | null;
  sessions: SessionListItem[];
}

export interface ChatMetaResponse {
  model: string;
  effort?: string;
  runtime_sdk?: string;
  provider?: string;
  repo_identity: string;
  workspace_cwd: string;
}

export interface QuestionDraft {
  selected: string[];
  customText: string;
}

export interface QuestionOption {
  label: string;
  description?: string;
}

export interface ApprovalDraft {
  reason: string;
}

export type TranscriptFilter = "thread" | "full" | "logs";
export type AgentMode = "chat" | "voice" | "trace";

export const APPROVAL_EVENT_TYPES = new Set(["tool_approval_request", "voice_action_prepared"]);
export const THREAD_EVENT_TYPES = new Set([
  "user_message",
  "assistant_message",
  "voice_final_summary",
  "run_error",
  "ask_user_question",
  "tool_approval_request",
  "voice_action_prepared",
]);
export const LOG_EVENT_TYPES = new Set(["specialist_status", "tool_result", "tool_error", "todo_snapshot"]);
export const TOOL_ACTIVITY_EVENT_TYPES = new Set(["tool_use", "tool_result", "tool_error", "todo_snapshot"]);
export const AGENT_RESPONSE_EVENT_TYPES = new Set([
  "assistant_message",
  "ask_user_question",
  "tool_approval_request",
  "voice_action_prepared",
  "run_error",
]);

export function findPendingBlockingItem(items: TimelineItem[]) {
  return (
    [...items]
      .reverse()
      .find(
        (item) =>
          (item.type === "ask_user_question" || APPROVAL_EVENT_TYPES.has(item.type)) &&
          !item.payload.answered,
      ) ?? null
  );
}

export function historyStillLoading(data: HistoryResponse) {
  return Boolean(data.status?.running) && findPendingBlockingItem(data.items ?? []) === null;
}

export function formatTime(timestamp: string) {
  return new Date(timestamp).toLocaleTimeString();
}

export function formatDuration(durationMs: number) {
  if (!durationMs) return "not recorded";
  const seconds = Math.max(1, Math.round(durationMs / 1000));
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return remainder ? `${minutes}m ${remainder}s` : `${minutes}m`;
}

export function normalizeQuestionOptions(rawOptions: unknown): QuestionOption[] {
  if (!Array.isArray(rawOptions)) {
    return [];
  }
  return rawOptions
    .map((option): QuestionOption | null => {
      if (typeof option === "string") {
        const label = option.trim();
        return label ? { label } : null;
      }
      if (option && typeof option === "object") {
        const record = option as Record<string, unknown>;
        const label = String(record.label ?? "").trim();
        const description = String(record.description ?? "").trim();
        return label ? { label, description: description || undefined } : null;
      }
      return null;
    })
    .filter((option): option is QuestionOption => option !== null);
}

export function readablePayloadText(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) {
    return value.map(readablePayloadText).filter(Boolean).join(", ");
  }
  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    for (const key of ["summary", "question", "title", "description", "label", "content", "action", "tool_name"]) {
      const nested = readablePayloadText(record[key]);
      if (nested) return nested;
    }
    try {
      return JSON.stringify(record);
    } catch {
      return "";
    }
  }
  return "";
}

export function questionAnswerText(item: TimelineItem): string {
  return readablePayloadText(item.payload.answer_value ?? item.payload.selected_options ?? "");
}

export function operatorChoiceLabel(label: string): string {
  const normalized = label.trim().toLowerCase();
  if (normalized === "start shipping") return "Start now";
  if (normalized === "hold delivery") return "Hold";
  return label;
}

export function decisionItemWasAnswered(item: TimelineItem): boolean {
  return Boolean(item.payload.answered) || item.status === "answered";
}

export function decisionTimelineStatus(item: TimelineItem): string {
  if (!decisionItemWasAnswered(item)) return "review_pending";
  if (APPROVAL_EVENT_TYPES.has(item.type)) {
    const decision = String(item.payload.decision ?? "").trim().toLowerCase();
    if (["deny", "denied", "reject", "rejected"].includes(decision)) return "denied";
    if (decision) return "approved";
  }
  return "answered";
}

export function runtimeTimelineIcon(runtimeSdk?: string | null, provider?: string | null): TimelineEntry["icon"] | undefined {
  const runtime = String(runtimeSdk ?? "").toLowerCase();
  const providerName = String(provider ?? "").toLowerCase();
  if (runtime.includes("codex") || providerName.includes("codex")) return "codex";
  if (runtime.includes("claude") || providerName.includes("claude")) return "claude";
  return undefined;
}

export function approvalDecisionFromText(value: string): "allow" | "deny" | null {
  const normalized = value.trim().toLowerCase();
  if (!normalized) return null;
  if (/^(yes|yep|approve|approved|allow|start|ship|continue|go ahead|proceed)\b/.test(normalized)) {
    return "allow";
  }
  if (/^(no|deny|denied|hold|stop|cancel|do not|don't)\b/.test(normalized)) {
    return "deny";
  }
  return null;
}

export function formatTokenCount(value: number | null | undefined) {
  return Number(value ?? 0).toLocaleString();
}

export function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

export function numberFrom(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

export function formatRatio(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return "not recorded";
  return `${Math.round(value * 100)}%`;
}

export function runOptimization(run: TaskAgentRunSummary | null | undefined) {
  return asRecord(asRecord(run?.observability).optimization_summary);
}

export function tokenAccountingFromOptimization(
  optimization: Record<string, unknown>,
  fallback: {
    rawTotal?: number | null;
    input?: number | null;
    output?: number | null;
    cached?: number | null;
  } = {},
) {
  const tokens = asRecord(optimization.token_accounting);
  const input = numberFrom(tokens.input_tokens) ?? fallback.input ?? fallback.rawTotal ?? 0;
  const output = numberFrom(tokens.output_tokens) ?? fallback.output ?? 0;
  const cached = numberFrom(tokens.cached_input_tokens) ?? fallback.cached ?? 0;
  const rawTotal = numberFrom(tokens.raw_total_tokens) ?? fallback.rawTotal ?? input + output;
  return {
    rawTotal,
    input,
    output,
    cached,
    noncachedPlusOutput: numberFrom(tokens.noncached_plus_output_tokens) ?? Math.max(input - cached, 0) + output,
    cacheRatio: numberFrom(tokens.cache_ratio) ?? (input ? cached / input : 0),
  };
}

export function runTokenAccounting(run: TaskAgentRunSummary | null | undefined) {
  return tokenAccountingFromOptimization(runOptimization(run), {
    input: run?.tokens_input ?? 0,
    output: run?.tokens_output ?? 0,
    cached: run?.tokens_cached ?? 0,
  });
}

export function statusOptimization(status: AgentStatus | null | undefined) {
  return asRecord(asRecord(status?.observability).optimization_summary);
}

export function statusTokenAccounting(status: AgentStatus | null | undefined) {
  return tokenAccountingFromOptimization(statusOptimization(status), {
    rawTotal: status?.tokens_used ?? 0,
  });
}

export function runChunkAccounting(run: TaskAgentRunSummary | null | undefined) {
  return asRecord(runOptimization(run).event_accounting);
}

export function runToolAccounting(run: TaskAgentRunSummary | null | undefined) {
  return asRecord(runOptimization(run).tool_accounting);
}

export function runAvoidableFlags(run: TaskAgentRunSummary | null | undefined) {
  const rawFlags = runOptimization(run).avoidable_cost_flags;
  return Array.isArray(rawFlags) ? rawFlags.map((flag) => String(flag)) : [];
}

export function isUninformativeToolUse(event: TaskActivityEvent) {
  if (event.event_type !== "tool_use") return false;
  const action = String(event.action || "").trim().toLowerCase();
  const filePath = String(event.file_path || "").trim();
  return !filePath && (!action || action === "used tool" || action === "used tool on");
}

export function shouldShowCompactStatus(status: string | null | undefined) {
  const normalized = (status ?? "").trim().toLowerCase();
  return !["complete", "completed", "done", "passed", "shipped", "success", "succeeded"].includes(normalized);
}

export function runStartedAt(run: Pick<TaskAgentRunSummary, "started_at">) {
  return new Date(run.started_at).getTime() || 0;
}

export function sortRunsNewestFirst(runs: TaskAgentRunSummary[]) {
  return [...runs].sort((left, right) => runStartedAt(right) - runStartedAt(left));
}

export function taskLatestRunTime(task: TaskBoardItem) {
  const latestRun = sortRunsNewestFirst(task.agent_runs)[0];
  if (latestRun) return runStartedAt(latestRun);
  return new Date(task.updated_at ?? "").getTime() || 0;
}

export function formatStructuredValue(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (!trimmed) return "";
    if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
      try {
        return JSON.stringify(JSON.parse(trimmed), null, 2);
      } catch {
        return trimmed;
      }
    }
    return trimmed;
  }

  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export function truncateText(value: string, limit = 280): string {
  if (value.length <= limit) return value;
  return `${value.slice(0, limit - 3)}...`;
}

export function diagnosticForItem(item: TimelineItem): DiagnosticSummary {
  const diagnostic = item.payload.diagnostic;
  if (diagnostic && typeof diagnostic === "object") {
    return diagnostic as DiagnosticSummary;
  }

  if (item.type === "specialist_status") {
    return {
      kind: "specialist_status",
      outcome: String(item.payload.phase ?? "running"),
      summary: `Documentation agent: ${String(item.payload.phase ?? "running")}`,
      detail: String(item.payload.content ?? ""),
      raw_response: String(item.payload.content ?? ""),
    };
  }

  if (item.type === "todo_snapshot") {
    const inProgress = Number(item.payload.in_progress_count ?? 0);
    const pending = Number(item.payload.pending_count ?? 0);
    const completed = Number(item.payload.completed_count ?? 0);
    return {
      kind: "todo_snapshot",
      outcome: "progress",
      summary: `Todos updated: ${inProgress} in progress, ${pending} pending, ${completed} completed`,
      detail: formatStructuredValue(item.payload.todos),
      raw_response: formatStructuredValue(item.payload.todos),
    };
  }

  const content = formatStructuredValue(item.payload.content);
  return {
    kind: item.type,
    outcome: item.type === "tool_error" ? "error" : "ok",
    tool_name: String(item.payload.tool_name ?? ""),
    input_focus: formatStructuredValue(item.payload.tool_input),
    summary: String(item.payload.tool_name ?? item.type),
    detail: truncateText(content.replace(/\s+/g, " ").trim(), 220),
    raw_response: content,
  };
}

export function upsertTimelineItem(items: TimelineItem[], nextItem: TimelineItem): TimelineItem[] {
  const existingIndex = items.findIndex((item) => item.id === nextItem.id);
  const nextItems = existingIndex >= 0 ? [...items] : [...items, nextItem];
  if (existingIndex >= 0) {
    nextItems[existingIndex] = nextItem;
  }
  nextItems.sort(
    (left, right) => new Date(left.timestamp).getTime() - new Date(right.timestamp).getTime(),
  );
  return nextItems;
}
