import { Button, Code, SectionLabel, StatusPill, SurfacePanel } from "@/design-system";
import { runtimeCostDisplay } from "@/lib/runtime-cost";
import type { TaskAgentRunSummary, TaskBoardItem } from "@/lib/types";
import { MetricRow } from "@/features/agent/AgentRunPresenters";
import {
  formatDuration,
  formatTime,
  formatTokenCount,
  shouldShowCompactStatus,
  type AgentMode,
  type AgentStatus,
} from "@/features/agent/agent-model";

interface TokenSummary {
  noncachedPlusOutput: number;
  rawTotal: number;
  cached: number;
}

interface AgentConversationRailProps {
  currentTurnTokens: TokenSummary;
  pendingBlocked: boolean;
  runVisualStatus: string;
  selectedRuntimeSdk: string | null;
  selectedTask: TaskBoardItem | null;
  recentRuns: TaskAgentRunSummary[];
  sessionId: string | null;
  status: AgentStatus | null;
  threadRuntimeSdk: string | null;
  onOpenTrace: () => void;
  onSelectRun: (runId: string, mode: AgentMode) => void;
}

export function AgentConversationRail({
  currentTurnTokens,
  pendingBlocked,
  runVisualStatus,
  selectedRuntimeSdk,
  selectedTask,
  recentRuns,
  sessionId,
  status,
  threadRuntimeSdk,
  onOpenTrace,
  onSelectRun,
}: AgentConversationRailProps) {
  return (
    <aside className="min-w-0 space-y-3">
      <SurfacePanel data-agent-stage="card" className="space-y-3">
        <SectionLabel>Session</SectionLabel>
        <div className="space-y-2">
          <MetricRow label="State" value={pendingBlocked ? "blocked" : status?.running ? "running" : "ready"} />
          <MetricRow label="Current runtime" value={selectedRuntimeSdk ?? "not selected"} mono />
          <MetricRow label="Thread runtime" value={status?.runtime_sdk ?? threadRuntimeSdk ?? "not started"} mono />
          <MetricRow label="Model" value={status?.model ?? "not selected"} mono />
          <MetricRow label="Non-cached + output" value={formatTokenCount(currentTurnTokens.noncachedPlusOutput)} mono />
          <MetricRow label="Raw tokens" value={formatTokenCount(currentTurnTokens.rawTotal)} mono />
          <MetricRow label="Cached tokens" value={formatTokenCount(currentTurnTokens.cached)} mono />
          <MetricRow
            label="Cost"
            value={runtimeCostDisplay(status?.cost_usd, status?.runtime_sdk, status?.provider, status?.observability)}
            mono
          />
        </div>
        <div className="flex flex-wrap gap-2">
          <StatusPill status={runVisualStatus} />
          <Code className="font-mono text-[10px] uppercase tracking-[0.16em]">
            {sessionId ? sessionId.slice(0, 8) : "new thread"}
          </Code>
        </div>
      </SurfacePanel>

      <SurfacePanel data-agent-stage="card" className="space-y-3">
        <SectionLabel>Selected task</SectionLabel>
        {selectedTask ? (
          <>
            <p className="text-sm font-medium leading-5 text-foreground">{selectedTask.title}</p>
            <p className="line-clamp-3 text-[12.5px] leading-5 text-muted-foreground">
              {selectedTask.description || selectedTask.feature_description}
            </p>
            <div className="flex flex-wrap gap-2">
              {shouldShowCompactStatus(selectedTask.status) ? <StatusPill status={selectedTask.status} /> : null}
              <Code className="font-mono text-[10px] uppercase tracking-[0.16em]">{selectedTask.phase}</Code>
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-8 rounded-full px-3 text-[12px]"
              onClick={onOpenTrace}
            >
              Open run trace
            </Button>
          </>
        ) : (
          <p className="rounded-[0.9rem] border border-dashed border-border/60 px-3 py-3 text-[12px] leading-5 text-muted-foreground">
            No work item is selected yet.
          </p>
        )}
      </SurfacePanel>

      <SurfacePanel data-agent-stage="card" className="space-y-3">
        <SectionLabel>Recent work</SectionLabel>
        {recentRuns.length === 0 ? (
          <p className="rounded-[0.9rem] border border-dashed border-border/60 px-3 py-3 text-[12px] leading-5 text-muted-foreground">
            Completed Builder work will appear here.
          </p>
        ) : (
          <div className="divide-y divide-border/55">
            {recentRuns.slice(0, 4).map((run) => (
              <button
                key={run.id}
                type="button"
                className="grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-3 rounded-[0.45rem] px-2 py-1.5 text-left transition hover:bg-muted/20"
                onClick={() => onSelectRun(run.id, "trace")}
              >
                <div className="min-w-0">
                  <span className="truncate font-mono text-[11px] uppercase tracking-[0.14em] text-foreground">
                    {run.agent_name}
                  </span>
                  <p className="font-mono text-[10.5px] text-muted-foreground">
                    {formatDuration(run.duration_ms)} · {run.num_turns} turns
                  </p>
                </div>
                <div className="space-y-1 text-right">
                  {shouldShowCompactStatus(run.status) ? <StatusPill status={run.status} /> : null}
                  <p className="font-mono text-[10px] text-muted-foreground">{formatTime(run.started_at)}</p>
                </div>
              </button>
            ))}
          </div>
        )}
      </SurfacePanel>
    </aside>
  );
}
