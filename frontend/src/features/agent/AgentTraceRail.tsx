import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { CostMeter } from "@/components/agent-native";
import { SectionLabel, StatusPill, SurfacePanel } from "@/design-system";
import { runtimeCostDisplay } from "@/lib/runtime-cost";
import type { CurrentSprintSummary, TaskAgentRunSummary, TaskBoardItem } from "@/lib/types";
import { MetricRow, TokenMetric } from "@/features/agent/AgentRunPresenters";
import {
  asRecord,
  formatDuration,
  formatRatio,
  formatTime,
  formatTokenCount,
  numberFrom,
  runAvoidableFlags,
  runChunkAccounting,
  runTokenAccounting,
  runToolAccounting,
  shouldShowCompactStatus,
} from "@/features/agent/agent-model";

interface AgentTraceRailProps {
  activeSprintId: string | null;
  sprintOptions: CurrentSprintSummary[];
  traceTasks: TaskBoardItem[];
  selectedTraceTask: TaskBoardItem | null;
  selectedTraceRuns: TaskAgentRunSummary[];
  selectedTraceRun: TaskAgentRunSummary | null;
  onSelectSprint: (value: string) => void;
  onSelectTask: (taskId: string) => void;
  onSelectRun: (runId: string) => void;
}

export function AgentTraceRail({
  activeSprintId,
  sprintOptions,
  traceTasks,
  selectedTraceTask,
  selectedTraceRuns,
  selectedTraceRun,
  onSelectSprint,
  onSelectTask,
  onSelectRun,
}: AgentTraceRailProps) {
  const selectedRunTokens = runTokenAccounting(selectedTraceRun);
  const selectedRunChunk = runChunkAccounting(selectedTraceRun);
  const selectedRunTools = runToolAccounting(selectedTraceRun);
  const selectedRunFlags = runAvoidableFlags(selectedTraceRun);
  const selectedRunLargeOutput = asRecord(asRecord(selectedTraceRun?.observability).large_output_artifacts);
  const selectedRunRetrievalCount = numberFrom(selectedRunTools.file_read_or_search_count) ?? 0;
  const selectedRunRepeatedRetrieval =
    selectedRunFlags.includes("redundant_scan") || selectedRunRetrievalCount >= 8;
  const selectedRunChunkRisk = Boolean(selectedRunChunk.chunk_pressure_risk);
  const selectedRunLargeOutputCount = numberFrom(selectedRunLargeOutput.count) ?? 0;
  const selectedRunHasLargeOutput =
    selectedRunLargeOutputCount > 0 ||
    selectedRunFlags.includes("large_command_output") ||
    selectedRunFlags.includes("large_final_response");
  const selectedRunBlocker =
    selectedTraceRun?.error ||
    selectedRunFlags.find((flag) => flag.includes("failed") || flag.includes("chunk")) ||
    selectedTraceRun?.stop_reason ||
    "none";

  return (
    <aside className="min-w-0 space-y-3">
      <SurfacePanel data-agent-stage="card" className="space-y-3">
        <SectionLabel>Run explorer</SectionLabel>
        <div className="space-y-2">
          <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">Sprint</p>
          <Select value={activeSprintId ?? "all"} onValueChange={onSelectSprint}>
            <SelectTrigger className="h-9 rounded-full">
              <SelectValue placeholder="Select sprint" />
            </SelectTrigger>
            <SelectContent>
              {sprintOptions.map((sprint) => (
                <SelectItem key={sprint.sprint_id} value={sprint.sprint_id}>
                  {sprint.label}
                </SelectItem>
              ))}
              <SelectItem value="all">All sprints</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-2">
          <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">Tasks</p>
          <div className="scroll-panel max-h-[260px] divide-y divide-border/55 overflow-y-auto pr-1">
            {traceTasks.length === 0 ? (
              <p className="rounded-[0.9rem] border border-dashed border-border/60 px-3 py-3 text-[12px] leading-5 text-muted-foreground">
                No tasks are available for this sprint yet.
              </p>
            ) : (
              traceTasks.map((task) => {
                const selected = selectedTraceTask?.id === task.id;
                return (
                  <button
                    key={task.id}
                    type="button"
                    className={[
                      "grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-3 rounded-[0.45rem] px-2 py-1.5 text-left transition",
                      selected ? "bg-muted/35" : "hover:bg-muted/20",
                    ].join(" ")}
                    onClick={() => onSelectTask(task.id)}
                  >
                    <div className="min-w-0">
                      <p className="truncate text-[12.5px] font-medium text-foreground">{task.title}</p>
                      <p className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
                        {task.agent_runs.length} run{task.agent_runs.length === 1 ? "" : "s"} · {task.phase}
                      </p>
                    </div>
                    {shouldShowCompactStatus(task.status) ? <StatusPill status={task.status} /> : null}
                  </button>
                );
              })
            )}
          </div>
        </div>
      </SurfacePanel>

      <SurfacePanel data-agent-stage="card" className="space-y-3">
        <SectionLabel>Agent runs</SectionLabel>
        {selectedTraceRuns.length === 0 ? (
          <p className="rounded-[0.9rem] border border-dashed border-border/60 px-3 py-3 text-[12px] leading-5 text-muted-foreground">
            Select a task with recorded agent runs, or dispatch queued work from the Board.
          </p>
        ) : (
          <div className="scroll-panel max-h-[320px] divide-y divide-border/55 overflow-y-auto pr-1">
            {selectedTraceRuns.map((run) => {
              const selected = selectedTraceRun?.id === run.id;
              return (
                <button
                  key={run.id}
                  type="button"
                  className={[
                    "grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-3 rounded-[0.45rem] px-2 py-1.5 text-left transition",
                    selected ? "bg-muted/35" : "hover:bg-muted/20",
                  ].join(" ")}
                  onClick={() => onSelectRun(run.id)}
                >
                  <div className="min-w-0">
                    <span className="truncate font-mono text-[11px] uppercase tracking-[0.14em] text-foreground">
                      {run.agent_name}
                    </span>
                    <p className="font-mono text-[10.5px] text-muted-foreground">
                      {formatDuration(run.duration_ms)} · {run.num_turns} turns · {run.runtime_sdk}
                    </p>
                  </div>
                  <div className="space-y-1 text-right">
                    {shouldShowCompactStatus(run.status) ? <StatusPill status={run.status} /> : null}
                    <p className="font-mono text-[10px] text-muted-foreground">{formatTime(run.started_at)}</p>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </SurfacePanel>

      <SurfacePanel data-agent-stage="card" className="space-y-3">
        <SectionLabel>Selected run</SectionLabel>
        <div className="space-y-2">
          <MetricRow label="Agent" value={selectedTraceRun?.agent_name ?? "not selected"} mono />
          <MetricRow label="Runtime" value={selectedTraceRun?.runtime_sdk ?? "not selected"} mono />
          <MetricRow label="Model" value={selectedTraceRun?.model ?? "not selected"} mono />
          <MetricRow label="Turns" value={String(selectedTraceRun?.num_turns ?? 0)} />
          <MetricRow label="Duration" value={selectedTraceRun ? formatDuration(selectedTraceRun.duration_ms) : "not recorded"} mono />
          <MetricRow label="Stop reason" value={selectedTraceRun?.stop_reason ?? "not recorded"} mono />
        </div>
        <div className="space-y-2 rounded-[1.05rem] border border-border/65 bg-background/45 px-3 py-3">
          <TokenMetric label="Raw tokens" value={formatTokenCount(selectedRunTokens.rawTotal)} />
          <TokenMetric label="Input tokens" value={formatTokenCount(selectedRunTokens.input)} />
          <TokenMetric label="Output tokens" value={formatTokenCount(selectedRunTokens.output)} />
          <TokenMetric label="Cached tokens" value={formatTokenCount(selectedRunTokens.cached)} />
          <TokenMetric label="Non-cached + output" value={formatTokenCount(selectedRunTokens.noncachedPlusOutput)} />
          <TokenMetric label="Cache ratio" value={formatRatio(selectedRunTokens.cacheRatio)} />
        </div>
        <div className="space-y-2 rounded-[1.05rem] border border-border/65 bg-background/45 px-3 py-3">
          <TokenMetric label="Chunk pressure" value={selectedRunChunkRisk ? "risk" : "clear"} />
          <TokenMetric
            label="Large-output flags"
            value={selectedRunHasLargeOutput ? selectedRunFlags.filter((flag) => flag.includes("large")).join(", ") || `${selectedRunLargeOutputCount} artifact(s)` : "none"}
          />
          <TokenMetric label="Zero-turn run" value={(selectedTraceRun?.num_turns ?? 0) === 0 ? "yes" : "no"} />
          <TokenMetric label="Repeated retrieval" value={selectedRunRepeatedRetrieval ? `${selectedRunRetrievalCount} retrieval event(s)` : "not flagged"} />
          <TokenMetric label="Blocker" value={selectedRunBlocker} />
        </div>
        <CostMeter
          value={selectedTraceRun?.cost_usd ?? 0}
          budget={selectedTraceRun?.max_budget_usd ?? undefined}
          label="Run cost"
          displayValue={runtimeCostDisplay(
            selectedTraceRun?.cost_usd,
            selectedTraceRun?.runtime_sdk,
            selectedTraceRun?.provider,
            selectedTraceRun?.observability,
          )}
        />
      </SurfacePanel>
    </aside>
  );
}
