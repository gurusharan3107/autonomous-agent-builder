import type {
  CurrentSprintSummary,
  TaskAgentRunSummary,
  TaskBoardItem,
  TaskGateResultSummary,
} from "@/lib/types";

export type LaneKey = "active" | "review" | "pending" | "done" | "blocked";
export type SprintStage =
  | "plan"
  | "design"
  | "implementation"
  | "blocked"
  | "verify"
  | "pr_review"
  | "build"
  | "shipped";

export const LANE_ORDER: Array<{
  key: LaneKey;
  title: string;
  tone: "active" | "review" | "pending" | "done" | "blocked";
}> = [
  { key: "active", title: "In progress", tone: "active" },
  { key: "review", title: "Needs review", tone: "review" },
  { key: "pending", title: "Queued", tone: "pending" },
  { key: "done", title: "Shipped", tone: "done" },
  { key: "blocked", title: "Blocked", tone: "blocked" },
];

export const BOARD_TIMELINE_STAGES: Array<{
  id: string;
  label: string;
  stage: SprintStage;
  statusKey?: string;
}> = [
  { id: "plan", label: "Plan", stage: "plan" },
  { id: "design", label: "Design", stage: "design" },
  { id: "implementation", label: "Implement", stage: "implementation" },
  { id: "gates", label: "Gates", stage: "verify", statusKey: "verify" },
  { id: "review", label: "Review", stage: "pr_review" },
  { id: "build", label: "Build", stage: "build", statusKey: "build" },
  { id: "done", label: "Done", stage: "shipped", statusKey: "shipped" },
];

export const IMPLEMENTATION_STATUSES = new Set([
  "implementation",
  "quality_gates",
  "pr_creation",
  "build_verify",
]);
export const VERIFY_PHASE_AGENTS = new Set(["feature-verifier", "feature-acceptance-tests"]);
export const OPTIMIZATION_PHASE_AGENTS = new Set(["optimization-agent"]);
export const PHASE_LEVEL_AGENTS = new Set([
  ...VERIFY_PHASE_AGENTS,
  ...OPTIMIZATION_PHASE_AGENTS,
]);
export const IMPLEMENTATION_AGENT_NAMES = new Set(["code-gen", "integration-resolver"]);
export const REVIEW_AGENT_NAMES = new Set(["evidence-collector", "pr-creator"]);
export const BUILD_AGENT_NAMES = new Set([
  "build-verifier",
  "feature-acceptance-tests",
  "feature-verifier",
]);

const COMPACT_NUMBER_FORMATTER = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 0,
});

export function stringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.map((item) => String(item)).filter((item) => item.trim().length > 0)
    : [];
}

export function stringValue(value: unknown, fallback = ""): string {
  const text = String(value ?? "").trim();
  return text || fallback;
}

export function detailRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

export function formatDuration(durationMs: number) {
  const seconds = Math.round(durationMs / 1000);
  if (!seconds) return "0s";
  if (seconds < 60) return `${seconds}s`;
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

export function formatCompactNumber(value: number) {
  return COMPACT_NUMBER_FORMATTER.format(value);
}

export function compactClientText(value: string, limit = 260) {
  const text = value.trim().replace(/\s+/g, " ");
  return text.length <= limit ? text : `${text.slice(0, limit - 1).trim()}...`;
}

export function sprintStageFromPhase(phase?: string | null): SprintStage | null {
  switch (phase) {
    case "scope":
    case "planning":
      return "plan";
    case "design":
      return "design";
    case "implementation":
      return "implementation";
    case "blocked":
      return "blocked";
    case "verify":
      return "verify";
    case "pr_review":
      return "pr_review";
    case "build":
    case "build_verify":
      return "build";
    case "shipped":
      return "shipped";
    default:
      return null;
  }
}

export function taskSprintId(task: TaskBoardItem): string {
  const sprintId = task.sprint_execution?.sprint_id;
  return typeof sprintId === "string" ? sprintId : "";
}

export function isPhaseLevelRun(run: Pick<TaskAgentRunSummary, "agent_name">) {
  return PHASE_LEVEL_AGENTS.has(run.agent_name);
}

export function isVerificationRun(run: Pick<TaskAgentRunSummary, "agent_name">) {
  return VERIFY_PHASE_AGENTS.has(run.agent_name);
}

export function latestRun(runs: TaskAgentRunSummary[]) {
  return runs.length > 0 ? runs[runs.length - 1] : null;
}

export function runTime(run: Pick<TaskAgentRunSummary, "started_at">) {
  return new Date(run.started_at).getTime() || 0;
}

export function splitCurrentVerificationRuns(runs: TaskAgentRunSummary[]) {
  const verificationRuns = runs.filter(isVerificationRun).sort((a, b) => runTime(a) - runTime(b));
  const latestByAgent = new Map<string, TaskAgentRunSummary>();
  verificationRuns.forEach((run) => latestByAgent.set(run.agent_name, run));
  const current = Array.from(latestByAgent.values()).sort((a, b) => runTime(b) - runTime(a));
  const currentIds = new Set(current.map((run) => run.id));
  const history = verificationRuns.filter((run) => !currentIds.has(run.id));
  return { current, history };
}

export function runTokenTotal(run: TaskAgentRunSummary) {
  return (run.tokens_input || 0) + (run.tokens_output || 0);
}

export function runDiffText(run: TaskAgentRunSummary) {
  const diff = detailRecord(run.diff_summary);
  const files = Number(diff.files_changed ?? 0);
  const insertions = Number(diff.insertions ?? 0);
  const deletions = Number(diff.deletions ?? 0);
  if (!files && !insertions && !deletions) return "";
  return `${files} file${files === 1 ? "" : "s"} · +${insertions}/-${deletions}`;
}

export function stageRuns(tasks: TaskBoardItem[], agents: ReadonlySet<string>) {
  return tasks
    .flatMap((task) =>
      (task.agent_runs ?? [])
        .filter((run) => agents.has(run.agent_name))
        .map((run) => ({ task, run })),
    )
    .sort((a, b) => runTime(b.run) - runTime(a.run));
}

export function latestStageRun(task: TaskBoardItem, agents: ReadonlySet<string>) {
  return stageRuns([task], agents)[0]?.run ?? null;
}

export function gateResultsForTasks(tasks: TaskBoardItem[]) {
  return tasks.flatMap((task) =>
    (task.gate_results ?? []).map((gate: TaskGateResultSummary) => ({ task, gate })),
  );
}

export function evidenceSummary(value: unknown) {
  const evidence = detailRecord(value);
  return (
    stringValue(evidence.summary) ||
    stringValue(evidence.result) ||
    stringValue(evidence.command) ||
    stringValue(evidence.error) ||
    ""
  );
}

export function sprintStageFromVisibleTasks(board: Record<LaneKey, TaskBoardItem[]>): SprintStage | null {
  if (board.blocked.length > 0) return "blocked";
  const reviewOrActive = [...board.review, ...board.active];
  if (reviewOrActive.some((task) => task.status === "build_verify")) return "build";
  if (reviewOrActive.some((task) => task.status === "quality_gates" || task.phase === "verification")) {
    return "verify";
  }
  if (reviewOrActive.some((task) => ["pr_creation", "review_pending"].includes(task.status))) return "pr_review";
  if (board.active.some((task) => IMPLEMENTATION_STATUSES.has(task.status))) {
    return "implementation";
  }
  if (board.review.length > 0) return "pr_review";
  if (board.done.length > 0 && board.pending.length === 0 && board.active.length === 0 && board.review.length === 0) {
    return "shipped";
  }
  return null;
}

export function sprintShippedHistoryTasks(
  sprint: CurrentSprintSummary | null,
  existingTaskIds: Set<string>,
): TaskBoardItem[] {
  if (!sprint || sprint.active_phase !== "shipped") return [];
  const evidence = detailRecord(sprint.verification_evidence);
  const completedAt = String(evidence.completed_at ?? "").trim() || null;
  const summary = stringValue(
    evidence.summary,
    `${sprint.label} completed verification with ${sprint.generated_task_ids.length} generated task records.`,
  );

  return sprint.generated_task_ids
    .filter((taskId) => !existingTaskIds.has(taskId))
    .map((taskId, index) => {
      const plannedTask = sprint.generated_tasks.find((task) => task.id === taskId);
      const sprintExecution = detailRecord(plannedTask?.sprint_execution);
      const model = stringValue(sprintExecution.recommended_model, sprint.model);
      const effort = stringValue(sprintExecution.recommended_effort, sprint.effort);
      return {
        id: taskId,
        title: plannedTask?.title || `Generated sprint task ${index + 1}`,
        description: plannedTask?.description || summary,
        status: "done",
        phase: "complete",
        feature_id: sprint.sprint_id,
        feature_title: sprint.label,
        feature_description: summary,
        feature_priority: 0,
        feature_item_type: "sprint-task",
        acceptance_criteria: [],
        dependencies: plannedTask?.dependencies ?? [],
        sprint_execution: {
          sprint_id: sprint.sprint_id,
          label: sprint.label,
          verification_status: sprint.verification_status,
          ...sprintExecution,
        },
        agent_name: "",
        runtime_sdk: sprint.runtime_sdk,
        provider: "",
        model,
        effort: effort || null,
        cost_usd: 0,
        total_cost: 0,
        tokens_input: 0,
        tokens_output: 0,
        tokens_cached: 0,
        num_turns: 0,
        duration_ms: 0,
        approval_gate_id: "",
        approval_gate_type: "",
        pending_approval_count: 0,
        blocked_reason: "",
        latest_run_status: sprint.verification_status,
        observability: null,
        gate_results: [],
        agent_runs: [],
        activity_timeline: [],
        updated_at: completedAt,
      };
    });
}
