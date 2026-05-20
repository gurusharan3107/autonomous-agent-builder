import type { ReactNode } from "react";
import { AgentTimeline, LogBlock, type TimelineEntry, type TimelineLogItem } from "@/components/agent-native";
import { EmptyState, LoadingState, SectionLabel, StatusPill, SurfacePanel } from "@/design-system";
import type { BoardData, DiffSummary, TaskAgentRunSummary, TaskBoardItem } from "@/lib/types";
import { MetricRow } from "@/features/agent/AgentRunPresenters";
import type { TranscriptFilter } from "@/features/agent/agent-model";

interface AgentRunTracePanelProps {
  boardData: BoardData | null;
  boardError: string | null;
  selectedTraceRun: TaskAgentRunSummary | null;
  selectedTraceTask: TaskBoardItem | null;
  taskRunDiff: DiffSummary | null;
  taskRunLogItems: TimelineLogItem[];
  taskRunTraceEntries: TimelineEntry[];
  traceSelectorRail: ReactNode;
  transcriptFilter: TranscriptFilter;
}

export function AgentRunTracePanel({
  boardData,
  boardError,
  selectedTraceRun,
  selectedTraceTask,
  taskRunDiff,
  taskRunLogItems,
  taskRunTraceEntries,
  traceSelectorRail,
  transcriptFilter,
}: AgentRunTracePanelProps) {
  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_340px] xl:items-start">
      <div className="min-w-0 space-y-4">
        <SurfacePanel data-agent-stage="section" className="space-y-4 rounded-[1.35rem] px-3.5 py-3.5 sm:px-4 sm:py-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <SectionLabel>Run trace</SectionLabel>
              <p className="mt-2 max-w-[60ch] text-sm leading-6 text-muted-foreground">
                Inspect the selected task-owned run from Board: task prompt, run events, cost, token, runtime, stop reason, and diff evidence.
              </p>
            </div>
            <StatusPill status={selectedTraceRun?.status ?? "pending"} />
          </div>
          <div className="stream-inner-panel px-3 py-3">
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
              Task run
            </p>
            <p className="mt-1 truncate font-mono text-[12px] text-foreground">
              {selectedTraceTask?.id ?? "No task selected"} {selectedTraceRun ? `· ${selectedTraceRun.id.slice(0, 8)}` : ""}
            </p>
            {selectedTraceTask ? (
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                {selectedTraceTask.title}
              </p>
            ) : null}
          </div>

          {boardError && !boardData ? (
            <EmptyState
              label="Could not load task runs"
              detail={boardError}
            />
          ) : !boardData ? (
            <LoadingState label="Loading task run trace..." />
          ) : !selectedTraceRun ? (
            <EmptyState
              label="No task run selected"
              detail="Open Run trace from a Board task run, or dispatch a task so run evidence can appear here."
            />
          ) : transcriptFilter === "logs" && taskRunLogItems.length === 0 ? (
            <EmptyState
              label="No task-run log yet"
              detail="Persisted task activity for this run will appear here when the run records tool or lifecycle events."
            />
          ) : transcriptFilter === "full" && taskRunTraceEntries.length === 0 ? (
            <EmptyState
              label="No task-run trace yet"
              detail="Task prompt, lifecycle events, status, and diff evidence will appear here."
            />
          ) : transcriptFilter === "thread" ? (
            <div className="scroll-panel max-h-[calc(100vh-20rem)] overflow-y-auto pr-1">
              <AgentTimeline entries={taskRunTraceEntries.filter((entry) => entry.kind !== "tool")} />
            </div>
          ) : transcriptFilter === "logs" ? (
            <div className="scroll-panel max-h-[calc(100vh-20rem)] overflow-y-auto pr-1">
              <LogBlock items={taskRunLogItems} emptyLabel="No task-run log events yet." maxHeight={560} />
            </div>
          ) : (
            <div className="scroll-panel max-h-[calc(100vh-20rem)] overflow-y-auto pr-1">
              <AgentTimeline entries={taskRunTraceEntries} />
            </div>
          )}
        </SurfacePanel>

        {transcriptFilter === "full" && taskRunDiff ? (
          <SurfacePanel data-agent-stage="section" className="space-y-3 rounded-[1.35rem] px-3.5 py-3.5 sm:px-4 sm:py-4">
            <SectionLabel>Diff evidence</SectionLabel>
            <div className="grid gap-2 sm:grid-cols-3">
              <MetricRow label="Files" value={String(taskRunDiff.files_changed)} />
              <MetricRow label="Insertions" value={`+${taskRunDiff.insertions}`} mono />
              <MetricRow label="Deletions" value={`-${taskRunDiff.deletions}`} mono />
            </div>
            {taskRunDiff.hunks.length > 0 ? (
              <div className="space-y-2">
                {taskRunDiff.hunks.slice(0, 4).map((hunk) => (
                  <div key={`${hunk.file}:${hunk.added_lines}:${hunk.removed_lines}`} className="stream-inner-panel px-3 py-3">
                    <p className="truncate font-mono text-[11px] text-foreground">{hunk.file}</p>
                    <p className="mt-1 font-mono text-[11px] text-muted-foreground">
                      +{hunk.added_lines} / -{hunk.removed_lines}
                    </p>
                    {hunk.preview ? <pre className="mt-2 whitespace-pre-wrap text-[11px] leading-5 text-muted-foreground">{hunk.preview}</pre> : null}
                  </div>
                ))}
              </div>
            ) : null}
          </SurfacePanel>
        ) : null}
      </div>

      {traceSelectorRail}
    </div>
  );
}
