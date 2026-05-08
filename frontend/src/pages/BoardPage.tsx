import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Brain, ChevronDown, ChevronRight, CircleDot, FilePenLine, FilePlus2, FileX2, Gauge, Play, Terminal, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  PageFrame,
  PageHeader,
  SectionLabel,
  StatusDot,
  SurfacePanel,
} from "@/components/workspace";
import { TaskCard } from "@/components/agent-native";
import { dispatchTask, fetchBoard, openBoardStream, recoverTask } from "@/lib/api";
import { runtimeCostDisplay } from "@/lib/runtime-cost";
import type { BoardData, CurrentSprintSummary, SprintPlanSummary, TaskActivityEvent, TaskAgentRunSummary, TaskBoardItem } from "@/lib/types";
import { cn } from "@/lib/utils";

type LaneKey = "active" | "review" | "pending" | "done" | "blocked";
type SprintStage =
  | "plan"
  | "design"
  | "implementation"
  | "blocked"
  | "verify"
  | "pr_review"
  | "shipped";

const LANE_ORDER: Array<{ key: LaneKey; title: string; tone: "active" | "review" | "pending" | "done" | "blocked" }> = [
  { key: "active", title: "In progress", tone: "active" },
  { key: "review", title: "Needs review", tone: "review" },
  { key: "pending", title: "Queued", tone: "pending" },
  { key: "done", title: "Shipped", tone: "done" },
  { key: "blocked", title: "Blocked", tone: "blocked" },
];

const SPRINT_STAGES: Array<{ key: SprintStage; label: string }> = [
  { key: "plan", label: "Plan" },
  { key: "design", label: "Design" },
  { key: "implementation", label: "Implementation" },
  { key: "blocked", label: "Blocked" },
  { key: "verify", label: "Verify" },
  // Sprint-PR refactor: a single approval gate replaces N per-task PR gates.
  { key: "pr_review", label: "PR Review" },
  { key: "shipped", label: "Shipped" },
];

const IMPLEMENTATION_STATUSES = new Set(["implementation", "quality_gates", "pr_creation", "build_verify"]);
const VERIFY_PHASE_AGENTS = new Set(["feature-verifier", "feature-acceptance-tests"]);
const OPTIMIZATION_PHASE_AGENTS = new Set(["optimization-agent"]);
const PHASE_LEVEL_AGENTS = new Set([...VERIFY_PHASE_AGENTS, ...OPTIMIZATION_PHASE_AGENTS]);

function stringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.map((item) => String(item)).filter((item) => item.trim().length > 0)
    : [];
}

function stringValue(value: unknown, fallback = ""): string {
  const text = String(value ?? "").trim();
  return text || fallback;
}

type SprintOptimizationInsight = {
  status: string;
  recommendation: string;
  action: string;
  benefit: string;
  proof: string;
  commands: Array<{ command: string; result: string; summary: string }>;
};

function firstRegexMatch(text: string, pattern: RegExp): string {
  return text.match(pattern)?.[1]?.trim() ?? "";
}

function parseOptimizationJson(summary: string): Record<string, unknown> {
  const fenced = summary.match(/```json\s*([\s\S]*?)```/)?.[1];
  const start = summary.indexOf("{");
  const end = summary.lastIndexOf("}");
  const raw = fenced || (start >= 0 && end > start ? summary.slice(start, end + 1) : "");
  if (!raw.trim().startsWith("{")) return {};
  try {
    return JSON.parse(raw) as Record<string, unknown>;
  } catch {
    return {};
  }
}

function sprintOptimizationInsight(sprint?: CurrentSprintSummary | null): SprintOptimizationInsight | null {
  const evidence = detailRecord(sprint?.verification_evidence);
  const optimization = detailRecord(evidence.optimization_agent);
  const summary = stringValue(optimization.summary);
  const structured = parseOptimizationJson(summary);
  const status =
    stringValue(structured.status) ||
    firstRegexMatch(summary, /"status"\s*:\s*"([^"]+)/) ||
    stringValue(optimization.status);
  if (!status) return null;

  const recommendation =
    stringValue(optimization.selected_recommendation) ||
    stringValue(structured.selected_recommendation) ||
    firstRegexMatch(summary, /"selected_recommendation"\s*:\s*"([^"]+)/) ||
    stringValue(optimization.reason, "post_ship_optimization");
  const whySelected =
    stringValue(structured.why_selected) ||
    firstRegexMatch(summary, /"why_selected"\s*:\s*"([^"]+)/) ||
    summary;
  const nextAction =
    stringValue(structured.next_action) ||
    firstRegexMatch(summary, /"next_action"\s*:\s*"([^"]+)/);
  const estimatedSavings =
    firstRegexMatch(whySelected, /estimated\s+([0-9,]+)\s+(?:non-cached\+output\s+)?token/i) ||
    firstRegexMatch(summary, /estimated\s+([0-9,]+)\s+(?:non-cached\+output\s+)?token/i);
  const firstCommand = Array.isArray(structured.commands)
    ? stringValue(detailRecord(structured.commands[0]).command)
    : firstRegexMatch(summary, /"command"\s*:\s*"([^"]+)"/);
  const rawCommands = Array.isArray(optimization.commands)
    ? optimization.commands
    : Array.isArray(structured.commands)
      ? structured.commands
      : [];
  const structuredCommands = rawCommands.length > 0
    ? rawCommands
        .map((item) => {
          const record = detailRecord(item);
          return {
            command: stringValue(record.command),
            result: stringValue(record.result, "not_run"),
            summary: stringValue(record.summary),
          };
        })
        .filter((item) => item.command)
    : [];
  const regexCommand = firstRegexMatch(summary, /"command"\s*:\s*"([^"]+)/);
  const regexResult = firstRegexMatch(summary, /"result"\s*:\s*"([^"]+)/);
  const commands = structuredCommands.length > 0
    ? structuredCommands
    : regexCommand
      ? [{ command: regexCommand, result: stringValue(regexResult, status), summary: "" }]
      : [];
  const generatedAppSkip = stringValue(optimization.reason) === "generated_app_workspace";

  return {
    status,
    recommendation,
    action:
      nextAction ||
      (status === "skipped"
        ? stringValue(optimization.summary, "No model optimization action was needed for this sprint.")
        : status === "blocked"
          ? "Optimization needs the builder source workspace."
          : stringValue(optimization.summary, "Optimization evidence captured for the next delivery-system improvement.")),
    benefit: stringValue(optimization.benefit) || (estimatedSavings
      ? `Expected saving: about ${estimatedSavings} tokens by replacing repeatable model work with a deterministic script.`
      : generatedAppSkip
        ? "Expected saving: avoids spending post-ship optimization tokens inside generated app workspaces."
        : "Expected benefit: keeps the next optimization action visible from shipped sprint telemetry."),
    proof: stringValue(firstCommand, stringValue(optimization.agent_name, "telemetry")),
    commands,
  };
}

function formatDuration(durationMs: number) {
  const seconds = Math.round(durationMs / 1000);
  if (!seconds) return "0s";
  if (seconds < 60) return `${seconds}s`;
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

function activityIcon(eventType: string) {
  switch (eventType) {
    case "file_created":
      return FilePlus2;
    case "file_deleted":
      return FileX2;
    case "file_updated":
    case "file_renamed":
      return FilePenLine;
    case "agent_output":
    case "tool_use":
      return Terminal;
    case "thinking":
      return Brain;
    default:
      return CircleDot;
  }
}

function runtimePower(run: Pick<TaskAgentRunSummary, "runtime_sdk" | "provider">) {
  const runtime = `${run.runtime_sdk} ${run.provider}`.toLowerCase();
  if (runtime.includes("codex")) {
    return { label: "Codex", Icon: Terminal };
  }
  if (runtime.includes("claude") || runtime.includes("anthropic")) {
    return { label: "Claude", Icon: Brain };
  }
  return { label: run.runtime_sdk || "Runtime", Icon: CircleDot };
}

function isPhaseLevelRun(run: Pick<TaskAgentRunSummary, "agent_name">) {
  return PHASE_LEVEL_AGENTS.has(run.agent_name);
}

function isVerificationRun(run: Pick<TaskAgentRunSummary, "agent_name">) {
  return VERIFY_PHASE_AGENTS.has(run.agent_name);
}

function isOptimizationRun(run: Pick<TaskAgentRunSummary, "agent_name">) {
  return OPTIMIZATION_PHASE_AGENTS.has(run.agent_name);
}

function runCostTotal(runs: TaskAgentRunSummary[]) {
  return runs.reduce((total, run) => total + Number(run.cost_usd || run.estimated_cost_usd || 0), 0);
}

function latestRun(runs: TaskAgentRunSummary[]) {
  return runs.length > 0 ? runs[runs.length - 1] : null;
}

function runTime(run: Pick<TaskAgentRunSummary, "started_at">) {
  return new Date(run.started_at).getTime() || 0;
}

function splitCurrentVerificationRuns(runs: TaskAgentRunSummary[]) {
  const verificationRuns = runs.filter(isVerificationRun).sort((a, b) => runTime(a) - runTime(b));
  const latestByAgent = new Map<string, TaskAgentRunSummary>();
  verificationRuns.forEach((run) => latestByAgent.set(run.agent_name, run));
  const current = Array.from(latestByAgent.values()).sort((a, b) => runTime(b) - runTime(a));
  const currentIds = new Set(current.map((run) => run.id));
  const history = verificationRuns.filter((run) => !currentIds.has(run.id));
  return { current, history };
}

function taskRunLabel(count: number) {
  return `${count} task-owned run${count === 1 ? "" : "s"}`;
}

function eventHelpsUser(event: TaskActivityEvent) {
  const action = stringValue(event.action);
  if (!action) return false;
  if (event.event_type === "agent_output" && action.length < 8) return false;
  if (event.event_type === "tool_use" && !event.file_path && /commandExecution|tool/i.test(action)) return false;
  if (/item\/(started|completed)/i.test(action)) return false;
  if (event.event_type.startsWith("runtime_item") && /userMessage|runtime item/i.test(action)) return false;
  return true;
}

function compactClientText(value: string, limit = 260) {
  const text = value.trim().replace(/\s+/g, " ");
  return text.length <= limit ? text : `${text.slice(0, limit - 1).trim()}...`;
}

function usefulRunEvents(events: TaskActivityEvent[]) {
  const result: TaskActivityEvent[] = [];
  let outputBuffer: TaskActivityEvent | null = null;
  let outputText = "";

  const flushOutput = () => {
    if (!outputBuffer) return;
    const compact = compactClientText(outputText);
    if (compact.length >= 8) {
      result.push({
        ...outputBuffer,
        action: compact,
      });
    }
    outputBuffer = null;
    outputText = "";
  };

  for (const event of events) {
    if (event.event_type === "agent_output") {
      if (!eventHelpsUser(event)) continue;
      if (!outputBuffer) outputBuffer = event;
      outputText = `${outputText}${event.action}`;
      continue;
    }
    flushOutput();
    if (eventHelpsUser(event)) result.push(event);
  }
  flushOutput();
  return result;
}

function AgentRunTimelineList({
  runs,
  activityTimeline,
  expandedRunId,
  onToggleRun,
}: {
  runs: TaskAgentRunSummary[];
  activityTimeline: TaskActivityEvent[];
  expandedRunId: string | null;
  onToggleRun: (runId: string) => void;
}) {
  return (
    <div className="mt-3 overflow-hidden rounded-xl border border-border/65">
      {runs.map((run) => {
        const isExpanded = expandedRunId === run.id;
        const runEvents = usefulRunEvents(activityTimeline.filter((event) => event.run_id === run.id));
        const power = runtimePower(run);
        const PowerIcon = power.Icon;
        return (
          <div key={run.id} className="border-b border-border/55 last:border-b-0">
            <button
              type="button"
              className="flex w-full items-start gap-3 px-3 py-3 text-left transition hover:bg-muted/24"
              onClick={() => onToggleRun(run.id)}
              aria-expanded={isExpanded}
            >
              <div className="mt-0.5 text-muted-foreground">
                {isExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="inline-flex items-center gap-1 rounded-full border border-border/65 px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.12em] text-foreground">
                    <PowerIcon className="h-3 w-3" />
                    {power.label}
                  </span>
                  <span className="font-mono text-[10.5px] uppercase tracking-[0.14em] text-muted-foreground">
                    {run.agent_name}
                  </span>
                  <span className={cn(
                    "rounded-full px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.12em]",
                    run.status === "completed" || run.status === "running"
                      ? "bg-primary/10 text-primary"
                      : "bg-muted text-muted-foreground",
                  )}>
                    {run.status}
                  </span>
                </div>
                <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 font-mono text-[10.5px] text-muted-foreground">
                  <span>{run.model || run.runtime_sdk || "model selected"}</span>
                  <span>{run.num_turns || 0} turns</span>
                  <span>{(run.tokens_input || 0) + (run.tokens_output || 0)} tokens</span>
                  <span>{run.duration_ms > 0 ? formatDuration(run.duration_ms) : "running"}</span>
                </div>
              </div>
            </button>
            {isExpanded ? (
              <div className="border-t border-border/55 bg-muted/14 px-3 py-3">
                {runEvents.length > 0 ? (
                  <ol className="space-y-2">
                    {runEvents.map((event) => {
                      const Icon = activityIcon(event.event_type);
                      return (
                        <li key={event.id} className="grid grid-cols-[18px_1fr] gap-3">
                          <div className="pt-0.5 text-muted-foreground">
                            <Icon className="h-4 w-4" />
                          </div>
                          <div className="min-w-0">
                            <div className="flex flex-wrap items-center gap-2 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
                              <span>{event.event_type.replaceAll("_", " ")}</span>
                              <span>{new Date(event.timestamp).toLocaleTimeString()}</span>
                            </div>
                            <p className="mt-1 break-words text-[12.5px] leading-5 text-foreground">
                              {event.action}
                            </p>
                          </div>
                        </li>
                      );
                    })}
                  </ol>
                ) : (
                  <p className="text-[12px] leading-6 text-muted-foreground">
                    This run has started, but no user-meaningful activity has been emitted yet.
                  </p>
                )}
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

function sprintStageFromPhase(phase?: string | null): SprintStage | null {
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
    case "shipped":
      return "shipped";
    default:
      return null;
  }
}

function taskSprintId(task: TaskBoardItem): string {
  const sprintId = task.sprint_execution?.sprint_id;
  return typeof sprintId === "string" ? sprintId : "";
}

function BoardSprintStrip({
  plan,
  currentSprint,
  observedRuntimeLabel,
  activeStage,
  dispatchableTask,
  dispatchingTaskId,
  onDispatch,
  onOpenStage,
}: {
  plan?: SprintPlanSummary | null;
  currentSprint?: CurrentSprintSummary | null;
  observedRuntimeLabel?: string;
  activeStage: SprintStage | null;
  dispatchableTask: TaskBoardItem | null;
  dispatchingTaskId: string | null;
  onDispatch: () => void;
  onOpenStage: (stage: SprintStage) => void;
}) {
  const optimization = sprintOptimizationInsight(currentSprint);
  const runtimeLabel = observedRuntimeLabel
    ? `Sprint agents ${observedRuntimeLabel}`
    : currentSprint?.runtime_sdk
      ? `Sprint runtime ${currentSprint.runtime_sdk}${currentSprint.model ? ` / ${currentSprint.model}` : ""}`
      : plan?.model
        ? `Planned runtime ${plan.model} / ${plan.effort || "medium"}`
        : "Runtime selected";
  return (
    <div className="relative mb-5 flex min-h-12 flex-col gap-3 border-y border-border/65 py-3 lg:flex-row lg:items-center lg:justify-between">
      <Button
        type="button"
        className="h-9 w-fit rounded-full"
        onClick={onDispatch}
        disabled={!dispatchableTask || dispatchingTaskId === dispatchableTask.id}
      >
        <Play className="h-3.5 w-3.5" />
        Dispatch task
      </Button>

      <div className="lg:absolute lg:left-1/2 lg:top-1/2 lg:-translate-x-1/2 lg:-translate-y-1/2">
        <div className="flex flex-wrap items-center justify-center gap-2 rounded-full border border-border/75 bg-background/78 px-3 py-2 shadow-[var(--shadow-xs)]">
          <span className="font-mono text-[10.5px] uppercase tracking-[0.18em] text-muted-foreground">
            {currentSprint?.label ?? `Sprint ${plan?.sprint_number ?? 1}`}
          </span>
          {SPRINT_STAGES.map((stage, index) => {
            const isActive = activeStage === stage.key;
            const phaseStatus = currentSprint?.phase_statuses?.[stage.key] ?? "";
            const isCompleted = phaseStatus === "complete";
            const isBlocked = phaseStatus === "blocked" || stage.key === "blocked";
            const isEnabled = Boolean(plan || currentSprint);
            return (
            <div key={stage.key} className="flex items-center gap-2">
              {index > 0 ? <span className="h-px w-4 bg-border" aria-hidden="true" /> : null}
              <button
                type="button"
                onClick={() => onOpenStage(stage.key)}
                disabled={!isEnabled}
                aria-pressed={isActive}
                className={cn(
                  "rounded-full px-2.5 py-1 text-[11px] font-medium transition",
                  isActive
                    ? isBlocked
                      ? "bg-status-blocked text-primary-foreground shadow-[var(--shadow-xs)]"
                      : "bg-primary text-primary-foreground shadow-[var(--shadow-xs)]"
                    : isCompleted
                      ? "bg-status-done/12 text-foreground hover:bg-status-done/18"
                      : phaseStatus === "blocked"
                        ? "bg-status-blocked/12 text-status-blocked hover:bg-status-blocked/18"
                      : "bg-muted text-muted-foreground hover:bg-muted/80",
                  !isEnabled ? "cursor-not-allowed opacity-55" : "",
                )}
              >
                {stage.label}
              </button>
            </div>
            );
          })}
        </div>
      </div>

      <div className="flex min-w-0 flex-col items-start gap-2 lg:w-[260px] lg:items-end">
        <div className="font-mono text-[10.5px] uppercase tracking-[0.14em] text-muted-foreground lg:text-right">
          {runtimeLabel}
        </div>
        {optimization && currentSprint?.active_phase === "shipped" ? (
          <button
            type="button"
            onClick={() => onOpenStage("shipped")}
            className="flex max-w-full items-center gap-2 rounded-full border border-status-done/35 bg-status-done/10 px-2.5 py-1 text-left text-[11px] text-foreground transition hover:bg-status-done/16"
            aria-label={`Optimization ${optimization.status}: ${optimization.recommendation}`}
          >
            <Gauge className="h-3.5 w-3.5 shrink-0 text-status-done" />
            <span className="min-w-0 truncate">
              Optimization {optimization.status} · {optimization.recommendation}
            </span>
          </button>
        ) : null}
      </div>
    </div>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-border/55 py-2 text-[12px]">
      <span className="text-muted-foreground">{label}</span>
      <span className="min-w-0 truncate text-right font-mono text-foreground">{value}</span>
    </div>
  );
}

function detailRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function SprintDetailSidebar({
  stage,
  plan,
  currentSprint,
  activeTasks,
  sprintTasks,
  onClose,
}: {
  stage: SprintStage | null;
  plan?: SprintPlanSummary | null;
  currentSprint?: CurrentSprintSummary | null;
  activeTasks: TaskBoardItem[];
  sprintTasks: TaskBoardItem[];
  onClose: () => void;
}) {
  if (!stage || (!plan && !currentSprint)) return null;
  const designDetails = detailRecord(plan?.design_details);
  const title =
    stage === "implementation"
      ? "Sprint implementation"
      : stage === "verify"
        ? "Sprint verification"
        : stage === "shipped"
          ? "Sprint shipped"
      : stage === "design"
        ? "Sprint design"
        : "Sprint plan";
  const subtitle =
    stage === "implementation"
      ? `${sprintTasks.length || activeTasks.length} implementation task${(sprintTasks.length || activeTasks.length) === 1 ? "" : "s"}`
      : stage === "verify" || stage === "shipped"
        ? `${currentSprint?.verification_status ?? "pending"} verification`
        : `${plan?.batch_count ?? 0} batches · ${plan?.model || "runtime selected"} / ${plan?.effort || "medium"}`;
  const sharedConcerns = stringList(designDetails.shared_concerns);
  const includedItems = currentSprint?.included_items ?? [];
  const optimization = sprintOptimizationInsight(currentSprint);
  const phaseStatus = currentSprint?.phase_statuses?.[stage] ?? currentSprint?.active_phase ?? "pending";
  const runtimeSummary = `${plan?.model || currentSprint?.model || "runtime selected"} / ${plan?.effort || currentSprint?.effort || "medium"}`;
  const executionSummary =
    plan?.batch_count && plan.batch_count > 0
      ? `${plan.batch_count} batch${plan.batch_count === 1 ? "" : "es"} · ${plan.sequential_count ?? 0} sequential · ${plan.parallel_count ?? 0} parallel`
      : plan?.strategy || plan?.mode || "sprint";
  const summaryRows = [
    { label: "Status", value: phaseStatus },
    { label: "Runtime", value: runtimeSummary },
    { label: "Execution", value: executionSummary },
  ];
  if (stage === "verify" || stage === "shipped") {
    summaryRows.push({ label: "Verification", value: currentSprint?.verification_status ?? "pending" });
  }
  const implementationTasks = sprintTasks.length > 0 ? sprintTasks : activeTasks;
  const verificationRuns = sprintTasks.flatMap((task) =>
    (task.agent_runs ?? [])
      .filter(isVerificationRun)
      .map((run) => ({ task, run })),
  );
  const verificationSplit = splitCurrentVerificationRuns(verificationRuns.map(({ run }) => run));
  const currentVerificationRunIds = new Set(verificationSplit.current.map((run) => run.id));
  const latestVerificationRuns = verificationRuns
    .filter(({ run }) => currentVerificationRunIds.has(run.id))
    .sort((a, b) => runTime(b.run) - runTime(a.run));
  const failedRepairRuns = verificationSplit.history.filter((run) => run.status !== "completed").length;

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-foreground/12 backdrop-blur-[2px]">
      <button
        type="button"
        aria-label="Close sprint details"
        className="absolute inset-0 cursor-default"
        onClick={onClose}
      />
      <aside className="relative h-full w-full max-w-[520px] overflow-y-auto border-l border-border bg-background px-5 py-5 shadow-[var(--shadow-lg)]">
        <div className="mb-5 flex items-start justify-between gap-4">
          <div className="min-w-0 space-y-2">
            <div className="font-mono text-[10.5px] uppercase tracking-[0.16em] text-muted-foreground">
              {currentSprint?.label ?? `Sprint ${plan?.sprint_number ?? 1}`} · {stage}
            </div>
            <h2 className="text-[20px] font-medium leading-tight text-foreground">{title}</h2>
            <p className="text-[12.5px] leading-6 text-muted-foreground">{subtitle}</p>
          </div>
          <Button type="button" variant="ghost" size="icon-sm" onClick={onClose} aria-label="Close">
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="space-y-5">
          <section>
            <SectionLabel>Summary</SectionLabel>
            <div className="mt-3 rounded-xl border border-border/65 px-3">
              {summaryRows.map((row) => (
                <DetailRow key={row.label} label={row.label} value={row.value} />
              ))}
            </div>
          </section>

          {stage === "shipped" && optimization ? (
            <section>
              <SectionLabel>Optimization</SectionLabel>
              <div className="mt-3 rounded-xl border border-status-done/35 bg-status-done/8 px-3 py-3">
                <div className="mb-2 flex items-center gap-2">
                  <Gauge className="h-4 w-4 text-status-done" />
                  <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-foreground">
                    {optimization.status} · {optimization.recommendation}
                  </span>
                </div>
                <div className="rounded-lg border border-border/55 px-3">
                  <DetailRow label="Action" value={optimization.action} />
                  <DetailRow label="Benefit" value={optimization.benefit} />
                  <DetailRow label="Proof" value={optimization.proof} />
                </div>
                <div className="mt-3">
                  <SectionLabel>Command timeline</SectionLabel>
                  {optimization.commands.length > 0 ? (
                    <ol className="mt-2 space-y-2">
                      {optimization.commands.map((item, index) => (
                        <li
                          key={`${item.command}-${index}`}
                          className="grid grid-cols-[18px_1fr] gap-3 rounded-lg border border-border/55 bg-background/70 px-3 py-2.5"
                        >
                          <div className="pt-0.5 text-muted-foreground">
                            <Terminal className="h-4 w-4" />
                          </div>
                          <div className="min-w-0">
                            <div className="font-mono text-[10.5px] uppercase tracking-[0.12em] text-muted-foreground">
                              step {index + 1} · {item.result}
                            </div>
                            <p className="mt-1 break-words font-mono text-[12px] leading-5 text-foreground">
                              {item.command}
                            </p>
                            {item.summary ? (
                              <p className="mt-1 text-[12px] leading-5 text-muted-foreground">
                                {item.summary}
                              </p>
                            ) : null}
                          </div>
                        </li>
                      ))}
                    </ol>
                  ) : (
                    <p className="mt-2 rounded-lg border border-border/55 bg-background/70 px-3 py-2.5 text-[12px] leading-5 text-muted-foreground">
                      No per-command optimization events were persisted for this run.
                    </p>
                  )}
                  <p className="mt-2 text-[11px] leading-5 text-muted-foreground">
                    Builder logs analysis reports OTEL reachable, with hook/tool span timeline not yet captured in builder-local events.
                  </p>
                </div>
              </div>
            </section>
          ) : null}

          {(stage === "verify" || stage === "shipped") ? (
            <section>
              <SectionLabel>Verification evidence</SectionLabel>
              {latestVerificationRuns.length > 0 ? (
                <div className="mt-3 space-y-2">
                  {latestVerificationRuns.map(({ task, run }) => {
                    const failed = run.status !== "completed" && run.status !== "running";
                    return (
                      <div
                        key={`${task.id}:${run.id}`}
                        className={cn(
                          "rounded-xl border px-3 py-3",
                          failed ? "border-status-blocked/35 bg-status-blocked/8" : "border-border/65",
                        )}
                      >
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-mono text-[10.5px] uppercase tracking-[0.14em] text-muted-foreground">
                            {run.agent_name}
                          </span>
                          <span className={cn(
                            "rounded-full px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.12em]",
                            failed ? "bg-status-blocked/12 text-status-blocked" : "bg-primary/10 text-primary",
                          )}>
                            {run.status}
                          </span>
                        </div>
                        <p className="mt-1 text-[12px] leading-5 text-foreground">
                          {task.feature_title || task.title}
                        </p>
                        <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 font-mono text-[10.5px] text-muted-foreground">
                          <span>{run.model || run.runtime_sdk || "deterministic"}</span>
                          <span>{run.num_turns || 0} turns</span>
                          <span>{(run.tokens_input || 0) + (run.tokens_output || 0)} tokens</span>
                          <span>{run.duration_ms > 0 ? formatDuration(run.duration_ms) : "running"}</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="mt-3 rounded-xl border border-border/65 px-3 py-3 text-[12px] leading-6 text-muted-foreground">
                  No feature verifier or deterministic acceptance evidence has been recorded for this sprint yet.
                </p>
              )}
              {verificationSplit.history.length > 0 ? (
                <p className="mt-3 rounded-xl border border-border/65 bg-muted/24 px-3 py-3 text-[12px] leading-6 text-muted-foreground">
                  Repair history: {verificationSplit.history.length} earlier verifier/acceptance run{verificationSplit.history.length === 1 ? "" : "s"} were superseded by the current evidence{failedRepairRuns > 0 ? `, including ${failedRepairRuns} resolved failed check${failedRepairRuns === 1 ? "" : "s"}` : ""}.
                </p>
              ) : null}
            </section>
          ) : null}

          {stage === "implementation" ? (
            <section>
              <SectionLabel>Implementation tasks</SectionLabel>
              <div className="mt-3 space-y-2">
                {implementationTasks.length > 0 ? (
                  implementationTasks.map((task) => {
                    const run = latestRun((task.agent_runs ?? []).filter((item) => !isPhaseLevelRun(item)));
                    return (
                    <div key={task.id} className="rounded-xl border border-border/65 px-3 py-3">
                      <div className="flex items-center justify-between gap-3">
                        <span className="min-w-0 truncate text-[13px] font-medium text-foreground">
                          {task.title}
                        </span>
                        <span className="shrink-0 font-mono text-[10.5px] uppercase tracking-[0.12em] text-muted-foreground">
                          {task.status}
                        </span>
                      </div>
                      <div className="mt-2 font-mono text-[11px] text-muted-foreground">
                        {run?.agent_name || task.agent_name || "implementation"} · {run?.runtime_sdk || task.runtime_sdk || currentSprint?.runtime_sdk || "runtime selected"}
                        {run?.duration_ms ? ` · ${formatDuration(run.duration_ms)}` : ""}
                      </div>
                    </div>
                    );
                  })
                ) : (
                  <p className="rounded-xl border border-border/65 px-3 py-3 text-[12px] leading-6 text-muted-foreground">
                    No implementation task evidence has been recorded for this sprint yet.
                  </p>
                )}
              </div>
            </section>
          ) : null}

          {includedItems.length > 0 ? (
            <section>
              <SectionLabel>Included outcomes</SectionLabel>
              <div className="mt-3 space-y-2">
                {includedItems.map((item) => (
                  <div key={item.id} className="rounded-xl border border-border/65 px-3 py-2">
                    <div className="text-[12px] font-medium text-foreground">{item.title}</div>
                    <div className="mt-1 font-mono text-[10.5px] uppercase tracking-[0.12em] text-muted-foreground">
                      {item.status}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          ) : null}

          {stage === "design" && sharedConcerns.length > 0 ? (
            <section>
              <SectionLabel>Shared concerns</SectionLabel>
              <ul className="mt-3 space-y-2">
                {sharedConcerns.map((item) => (
                  <li key={item} className="rounded-xl border border-border/65 px-3 py-2 text-[12px] leading-5 text-muted-foreground">
                    {item}
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          <section>
            <SectionLabel>Batches</SectionLabel>
            <div className="mt-3 space-y-2">
                {(plan?.batches ?? []).map((batch) => (
                <div key={batch.id} className="grid grid-cols-[86px_1fr_auto] items-center gap-3 border-b border-border/55 py-2 text-[12px]">
                  <span className="font-mono text-[11px] text-muted-foreground">{batch.id}</span>
                  <span className="min-w-0 truncate text-foreground">{batch.title}</span>
                  <span className="font-mono text-[11px] text-muted-foreground">
                    {batch.model || plan?.model} / {batch.effort || plan?.effort}
                  </span>
                </div>
              ))}
            </div>
          </section>
        </div>
      </aside>
    </div>
  );
}

function TaskDetailSidebar({
  task,
  onClose,
}: {
  task: TaskBoardItem | null;
  onClose: () => void;
}) {
  if (!task) return null;
  const sprint = task.sprint_execution ?? {};
  const acceptance = task.acceptance_criteria ?? [];
  const dependencies = task.dependencies ?? [];
  const activityTimeline = task.activity_timeline ?? [];
  const agentRuns = task.agent_runs ?? [];
  const taskRuns = agentRuns.filter((run) => !isPhaseLevelRun(run));
  const phaseRuns = agentRuns.filter(isPhaseLevelRun);
  const verifyPhaseRuns = phaseRuns.filter(isVerificationRun);
  const optimizationPhaseRuns = phaseRuns.filter(isOptimizationRun);
  const verifyPhaseSplit = splitCurrentVerificationRuns(verifyPhaseRuns);
  const taskDisplayRun = latestRun(taskRuns);
  const defaultExpandedRunId = [...taskRuns].reverse().find((run) => run.status === "running")?.id ?? null;
  const [expandedRunId, setExpandedRunId] = useState<string | null>(defaultExpandedRunId);
  useEffect(() => {
    setExpandedRunId(defaultExpandedRunId);
  }, [task.id, defaultExpandedRunId]);
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-foreground/12 backdrop-blur-[2px]">
      <button
        type="button"
        aria-label="Close task details"
        className="absolute inset-0 cursor-default"
        onClick={onClose}
      />
      <aside className="relative h-full w-full max-w-[460px] overflow-y-auto border-l border-border bg-background px-5 py-5 shadow-[var(--shadow-lg)]">
        <div className="mb-5 flex items-start justify-between gap-4">
          <div className="min-w-0 space-y-2">
            <div className="flex flex-wrap items-center gap-2 font-mono text-[10.5px] uppercase tracking-[0.16em] text-muted-foreground">
              <span>{task.id.slice(0, 8)}</span>
              <span>{task.feature_item_type}</span>
              <span>{task.status}</span>
            </div>
            <h2 className="text-[20px] font-medium leading-tight text-foreground">{task.title}</h2>
            <p className="text-[12.5px] leading-6 text-muted-foreground">
              {task.description || task.feature_description || task.feature_title}
            </p>
          </div>
          <Button type="button" variant="ghost" size="icon-sm" onClick={onClose} aria-label="Close">
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="space-y-5">
          <section>
            <SectionLabel>Task</SectionLabel>
            <div className="mt-3 rounded-xl border border-border/65 px-3">
              <DetailRow label="Feature" value={task.feature_title || task.feature_id} />
              <DetailRow label="Phase" value={task.phase} />
              <DetailRow label="Task runs" value={taskRunLabel(taskRuns.length)} />
              <DetailRow label="Cost usage" value={runtimeCostDisplay(runCostTotal(taskRuns), taskDisplayRun?.runtime_sdk || task.runtime_sdk, taskDisplayRun?.provider || task.provider, task.observability)} />
              <DetailRow label="Turns" value={String(taskRuns.reduce((total, run) => total + (run.num_turns || 0), 0))} />
              <DetailRow label="Duration" value={taskDisplayRun && taskDisplayRun.duration_ms > 0 ? formatDuration(taskDisplayRun.duration_ms) : "not started"} />
              <DetailRow label="Runtime" value={taskDisplayRun?.runtime_sdk || "not assigned"} />
              <DetailRow label="Model" value={taskDisplayRun?.model || stringValue(sprint.recommended_model, "runtime selected")} />
              <DetailRow label="Effort" value={taskDisplayRun?.effort || stringValue(sprint.recommended_effort, "medium")} />
            </div>
          </section>

          <section>
            <SectionLabel>Task run timeline</SectionLabel>
            <p className="mt-1 text-[12px] leading-5 text-muted-foreground">
              Task-owned implementation and local verification runs. Sprint-level feature verification and optimization are tracked on the phase pill.
            </p>
            {taskRuns.length > 0 ? (
              <AgentRunTimelineList
                runs={taskRuns}
                activityTimeline={activityTimeline}
                expandedRunId={expandedRunId}
                onToggleRun={(runId) => setExpandedRunId(expandedRunId === runId ? null : runId)}
              />
            ) : (
              <p className="mt-3 rounded-xl border border-border/65 px-3 py-3 text-[12px] leading-6 text-muted-foreground">
                No task-owned agent activity recorded yet.
              </p>
            )}
            {phaseRuns.length > 0 ? (
              <div className="mt-3 rounded-xl border border-primary/25 bg-primary/6 px-3 py-3">
                <div className="font-mono text-[10.5px] uppercase tracking-[0.14em] text-foreground">
                  Phase evidence attached here
                </div>
                <p className="mt-1 text-[12px] leading-5 text-muted-foreground">
                  {verifyPhaseSplit.current.length} current verification signal{verifyPhaseSplit.current.length === 1 ? "" : "s"}, {verifyPhaseSplit.history.length} repair-history run{verifyPhaseSplit.history.length === 1 ? "" : "s"}, and {optimizationPhaseRuns.length} optimization run{optimizationPhaseRuns.length === 1 ? "" : "s"} are sprint-level evidence. Inspect them from the Verify or Shipped pill so this task drawer stays focused on task-owned work.
                </p>
              </div>
            ) : null}
          </section>

          <section>
            <SectionLabel>Sprint handoff</SectionLabel>
            <div className="mt-3 rounded-xl border border-border/65 px-3">
              <DetailRow label="Batch" value={stringValue(sprint.batch_id, "unassigned")} />
              <DetailRow label="Execution" value={stringValue(sprint.execution_mode, "sequential")} />
              <DetailRow label="Parallel group" value={stringValue(sprint.parallel_group, "none")} />
              <DetailRow label="Plan" value={stringValue(sprint.plan_id, "shared sprint plan")} />
              <DetailRow label="Design" value={stringValue(sprint.design_id, "shared sprint design")} />
            </div>
            {stringValue(sprint.implementation_brief) ? (
              <p className="mt-3 rounded-xl border border-border/65 bg-muted/28 px-3 py-3 text-[12px] leading-6 text-muted-foreground">
                {compactClientText(stringValue(sprint.implementation_brief), 420)}
              </p>
            ) : null}
            {stringValue(sprint.file_ownership_hint) ? (
              <p className="mt-2 font-mono text-[11px] text-muted-foreground">
                {stringValue(sprint.file_ownership_hint)}
              </p>
            ) : null}
          </section>

          {acceptance.length > 0 ? (
            <section>
              <SectionLabel>Acceptance</SectionLabel>
              <ul className="mt-3 space-y-2">
                {acceptance.map((item) => (
                  <li key={item} className="rounded-xl border border-border/65 px-3 py-2 text-[12px] leading-5 text-muted-foreground">
                    {item}
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          {dependencies.length > 0 ? (
            <section>
              <SectionLabel>Dependencies</SectionLabel>
              <div className="mt-3 flex flex-wrap gap-2">
                {dependencies.map((item) => (
                  <span key={item} className="rounded-full border border-border/65 px-2.5 py-1 font-mono text-[11px] text-muted-foreground">
                    {item}
                  </span>
                ))}
              </div>
            </section>
          ) : null}

          {task.approval_gate_id ? (
            <Button asChild className="w-full rounded-full">
              <Link to={`/approvals/${task.approval_gate_id}`}>
                Review approval
                <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
          ) : null}
        </div>
      </aside>
    </div>
  );
}

function Lane({
  title,
  tasks,
  density,
  tone,
  onSelect,
  onRecover,
  recoveringTaskId,
}: {
  title: string;
  tasks: TaskBoardItem[];
  density: "comfortable" | "compact";
  tone: "active" | "review" | "pending" | "done" | "blocked";
  onSelect: (task: TaskBoardItem) => void;
  onRecover?: (task: TaskBoardItem) => void;
  recoveringTaskId?: string | null;
}) {
  return (
    <SurfacePanel
      className={[
        "flex min-h-[400px] flex-col space-y-4",
        tone === "blocked" ? "hatch" : "",
      ].join(" ")}
      style={{
        background: `oklch(from var(--status-${tone}) l c h / 0.04)`,
      }}
    >
      <div className="space-y-3 border-b border-border/60 pb-3">
        <div className="flex h-8 items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2">
            <StatusDot tone={tone} pulse={tone === "active"} className="h-2 w-2" />
            <span className="truncate text-[12px] font-medium text-foreground">{title}</span>
          </div>
          <span className="font-mono text-[11px] text-muted-foreground">{tasks.length}</span>
        </div>
      </div>
      {tasks.length === 0 ? (
        <EmptyState
          className="flex-1"
          label={`No ${title.toLowerCase()} work right now.`}
          detail="The board keeps the lane visible so the operator can see what is empty, not just what is populated."
        />
      ) : (
        <div className={density === "compact" ? "space-y-2" : "space-y-3"}>
          {tasks.map((task) => (
            <TaskCard
              key={task.id}
              task={task}
              density={density}
              onSelect={onSelect}
              onRecover={onRecover}
              recovering={recoveringTaskId === task.id}
            />
          ))}
        </div>
      )}
    </SurfacePanel>
  );
}

function sprintShippedHistoryTasks(
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
        agent_runs: [],
        activity_timeline: [],
        updated_at: completedAt,
      };
    });
}

function SprintHistoryStrip({
  sprints,
  selectedSprintId,
  onSelect,
}: {
  sprints: CurrentSprintSummary[];
  selectedSprintId: string;
  onSelect: (sprintId: string) => void;
}) {
  if (sprints.length === 0) return null;

  return (
    <div className="mb-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
      {sprints.map((sprint) => {
        const selected = sprint.sprint_id === selectedSprintId;
        const taskTotal = Object.values(sprint.task_counts ?? {}).reduce((sum, count) => sum + Number(count || 0), 0);
        return (
          <button
            key={sprint.sprint_id}
            type="button"
            onClick={() => onSelect(sprint.sprint_id)}
            className={cn(
              "rounded-xl border px-3 py-3 text-left transition",
              selected
                ? "border-foreground/70 bg-foreground text-background shadow-[var(--shadow-sm)]"
                : "border-border/70 bg-background/80 hover:border-foreground/30 hover:bg-muted/30",
            )}
            aria-pressed={selected}
          >
            <div className="flex items-center justify-between gap-3">
              <span className="text-[13px] font-medium">{sprint.label}</span>
              <span className="font-mono text-[10.5px] uppercase tracking-[0.14em] opacity-70">
                {sprint.active_phase}
              </span>
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-2 font-mono text-[10.5px] uppercase tracking-[0.12em] opacity-75">
              <span>{sprint.verification_status || "pending"} verify</span>
              <span>{taskTotal || sprint.generated_task_ids.length} tasks</span>
            </div>
          </button>
        );
      })}
    </div>
  );
}

export default function BoardPage() {
  const density: "comfortable" | "compact" = "comfortable";
  const [board, setBoard] = useState<BoardData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dispatchingTaskId, setDispatchingTaskId] = useState<string | null>(null);
  const [recoveringTaskId, setRecoveringTaskId] = useState<string | null>(null);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [sprintDetailStage, setSprintDetailStage] = useState<SprintStage | null>(null);
  const [selectedSprintId, setSelectedSprintId] = useState<string>("");
  const [streamKey, setStreamKey] = useState(0);

  const loadFallback = async () => {
    try {
      const data = await fetchBoard();
      setBoard(data);
      setError(null);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Failed to load board");
    }
  };

  useEffect(() => {
    let active = true;
    let receivedSnapshot = false;
    const fallbackTimer = window.setTimeout(() => {
      if (active && !receivedSnapshot) {
        void loadFallback();
      }
    }, 1500);
    const stream = openBoardStream((data) => {
      if (!active) return;
      receivedSnapshot = true;
      window.clearTimeout(fallbackTimer);
      setBoard(data);
      setError(null);
    });

    stream.onerror = () => {
      if (!active) return;
      if (!receivedSnapshot) {
        window.clearTimeout(fallbackTimer);
        void loadFallback();
      }
    };

    return () => {
      active = false;
      window.clearTimeout(fallbackTimer);
      stream.close();
    };
  }, [streamKey]);

  useEffect(() => {
    if (!board) return;
    const sprintIds = new Set((board.sprints ?? []).map((sprint) => sprint.sprint_id));
    const currentId = board.current_sprint?.sprint_id ?? "";
    if (!selectedSprintId || (selectedSprintId !== "all" && !sprintIds.has(selectedSprintId))) {
      setSelectedSprintId(currentId || "all");
    }
  }, [board, selectedSprintId]);

  const sprints = board?.sprints ?? [];
  const selectedSprint = sprints.find((sprint) => sprint.sprint_id === selectedSprintId) ?? board?.current_sprint ?? null;
  const selectedPlan =
    selectedSprint && selectedSprint.sprint_id === board?.current_sprint?.sprint_id
      ? board?.sprint_plan
      : null;
  const selectedSprintTaskIds = new Set(selectedSprint?.generated_task_ids ?? []);
  const filterTasks = (tasks: TaskBoardItem[]) => {
    if (!selectedSprint || selectedSprintId === "all") return tasks;
    return tasks.filter((task) => selectedSprintTaskIds.has(task.id) || taskSprintId(task) === selectedSprint.sprint_id);
  };
  const filteredBoard = board
    ? {
        pending: filterTasks(board.pending),
        active: filterTasks(board.active),
        review: filterTasks(board.review),
        done: [
          ...filterTasks(board.done),
          ...sprintShippedHistoryTasks(
            selectedSprint,
            new Set(
              [...board.pending, ...board.active, ...board.review, ...board.done, ...board.blocked]
                .map((task) => task.id),
            ),
          ),
        ],
        blocked: filterTasks(board.blocked),
      }
    : { pending: [], active: [], review: [], done: [], blocked: [] };
  const allTasks = LANE_ORDER.flatMap((lane) => filteredBoard[lane.key]);
  const selectedTask = allTasks.find((task) => task.id === selectedTaskId) ?? null;
  const dispatchableTask = filteredBoard.active[0] ?? filteredBoard.pending[0] ?? null;
  const observedRuntime = allTasks
    .flatMap((task) => task.agent_runs ?? [])
    .find((run) => run.runtime_sdk && run.runtime_sdk !== "deterministic");
  const observedRuntimeLabel = observedRuntime
    ? `${observedRuntime.runtime_sdk}${observedRuntime.model ? ` / ${observedRuntime.model}` : ""}`
    : "";
  const activeSprintStage: SprintStage | null =
    sprintStageFromPhase(selectedSprint?.active_phase)
    ?? (filteredBoard.active.some((task) => IMPLEMENTATION_STATUSES.has(task.status)) ? "implementation" : null);

  const handleDispatch = async () => {
    if (!dispatchableTask) return;
    setDispatchingTaskId(dispatchableTask.id);
    try {
      await dispatchTask(dispatchableTask.id);
    } catch (dispatchError) {
      setError(dispatchError instanceof Error ? dispatchError.message : "Failed to dispatch task");
    } finally {
      setDispatchingTaskId(null);
    }
  };

  const handleRecover = async (task: TaskBoardItem) => {
    setRecoveringTaskId(task.id);
    setError(null);
    try {
      await recoverTask(task.id);
      setBoard(await fetchBoard());
    } catch (recoverError) {
      setError(recoverError instanceof Error ? recoverError.message : "Failed to recover task");
    } finally {
      setRecoveringTaskId(null);
    }
  };

  if (error && !board) {
    return <ErrorState message={error} onRetry={() => setStreamKey((value) => value + 1)} />;
  }

  if (!board) {
    return <LoadingState label="Loading pipeline..." />;
  }

  return (
    <PageFrame variant="overview">
      <PageHeader
        eyebrow="Pipeline · board"
        title="Every task, every phase - one horizon."
        description="Five status lanes, one unified visual grammar. Active runs breathe, blocked work is hatched, reviewable work is warm, and every card stays grounded in real runtime data."
      />

      <BoardSprintStrip
        plan={selectedPlan}
        currentSprint={selectedSprint}
        observedRuntimeLabel={observedRuntimeLabel}
        activeStage={activeSprintStage}
        dispatchableTask={dispatchableTask}
        dispatchingTaskId={dispatchingTaskId}
        onDispatch={handleDispatch}
        onOpenStage={setSprintDetailStage}
      />

      {error ? (
        <div className="mb-4">
          <ErrorState message={error} onRetry={() => setStreamKey((value) => value + 1)} />
        </div>
      ) : null}

      <div className="mb-4 flex flex-wrap items-center justify-between gap-3 border-b border-border/65 pb-4">
        <div className="min-w-0">
          <SectionLabel>Sprint view</SectionLabel>
          <p className="mt-1 text-[12.5px] text-muted-foreground">
            Showing tasks for {selectedSprint?.label ?? "all sprints"}.
          </p>
        </div>
        <Select value={selectedSprintId || board.current_sprint?.sprint_id || "all"} onValueChange={setSelectedSprintId}>
          <SelectTrigger className="min-w-[180px] justify-between" aria-label="Select sprint">
            <SelectValue placeholder="Select sprint" />
          </SelectTrigger>
          <SelectContent align="end">
            {sprints.map((sprint) => (
              <SelectItem key={sprint.sprint_id} value={sprint.sprint_id}>
                {sprint.label}
              </SelectItem>
            ))}
            <SelectItem value="all">All sprints</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <SprintHistoryStrip
        sprints={sprints}
        selectedSprintId={selectedSprintId}
        onSelect={setSelectedSprintId}
      />

      <div className="grid gap-4 xl:grid-cols-5">
        {LANE_ORDER.map((lane) => (
          <Lane
            key={lane.key}
            title={lane.title}
            tasks={filteredBoard[lane.key]}
            density={density}
            tone={lane.tone}
            onSelect={(task) => setSelectedTaskId(task.id)}
            onRecover={lane.key === "blocked" ? handleRecover : undefined}
            recoveringTaskId={recoveringTaskId}
          />
        ))}
      </div>
      <TaskDetailSidebar task={selectedTask} onClose={() => setSelectedTaskId(null)} />
      <SprintDetailSidebar
        stage={sprintDetailStage}
        plan={selectedPlan}
        currentSprint={selectedSprint}
        activeTasks={filteredBoard.active.filter((task) => IMPLEMENTATION_STATUSES.has(task.status))}
        sprintTasks={allTasks.filter((task) => taskSprintId(task) === (selectedSprint?.sprint_id ?? ""))}
        onClose={() => setSprintDetailStage(null)}
      />
    </PageFrame>
  );
}
