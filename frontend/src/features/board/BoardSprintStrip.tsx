import { Play } from "lucide-react";
import { Button } from "@/design-system";
import type { CurrentSprintSummary, SprintPlanSummary, TaskBoardItem } from "@/lib/types";
import { cn } from "@/lib/utils";
import { BOARD_TIMELINE_STAGES, type SprintStage } from "./board-model";

export function BoardSprintStrip({
  plan,
  currentSprint,
  activeStage,
  dispatchableTask,
  dispatchingTaskId,
  hasRunningTask,
  hasStartedWork,
  hasUnresolvedStartedWork,
  onDispatch,
  onOpenStage,
}: {
  plan?: SprintPlanSummary | null;
  currentSprint?: CurrentSprintSummary | null;
  activeStage: SprintStage | null;
  dispatchableTask: TaskBoardItem | null;
  dispatchingTaskId: string | null;
  hasRunningTask: boolean;
  hasStartedWork: boolean;
  hasUnresolvedStartedWork: boolean;
  onDispatch: () => void;
  onOpenStage: (stage: SprintStage) => void;
}) {
  let dispatchLabel = "No work to start";
  let dispatchButtonLabel = "Start work";
  if (hasRunningTask) {
    dispatchLabel = "Work is running";
    dispatchButtonLabel = "Work running";
  } else if (hasUnresolvedStartedWork) {
    dispatchLabel = "Work already started";
    dispatchButtonLabel = "Work already started";
  } else if (dispatchableTask && hasStartedWork) {
    dispatchLabel = `Continue ${dispatchableTask.title}`;
    dispatchButtonLabel = "Continue work";
  } else if (dispatchableTask) {
    dispatchLabel = `Start ${dispatchableTask.title}`;
  }

  return (
    <div className="rounded-[22px] border border-border/65 bg-surface/92 px-4 py-4 shadow-[var(--shadow-xs)]">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-2">
          {BOARD_TIMELINE_STAGES.map((item, index) => {
            const statusKey = item.statusKey ?? item.stage;
            const phaseStatus = currentSprint?.phase_statuses?.[statusKey] ?? "";
            const isBlocked =
              phaseStatus === "blocked" || (activeStage === "blocked" && item.stage === "implementation");
            const isCompleted = phaseStatus === "complete" || (item.stage === "shipped" && activeStage === "shipped");
            const isActive =
              !isBlocked
              && !isCompleted
              && (phaseStatus === "active" || activeStage === item.stage);
            const isEnabled = Boolean(plan || currentSprint);
            return (
              <div key={item.id} className="flex items-center gap-2">
                {index > 0 ? (
                  <span
                    className={cn(
                      "h-px w-5 shrink-0",
                      isCompleted || isActive ? "bg-status-done" : "bg-border",
                    )}
                    aria-hidden="true"
                  />
                ) : null}
                <button
                  type="button"
                  onClick={() => onOpenStage(item.stage)}
                  disabled={!isEnabled}
                  aria-pressed={isActive}
                  className={cn(
                    "group inline-flex items-center gap-2 rounded-full px-1.5 py-1 text-left font-mono text-[10.5px] uppercase tracking-[0.08em] transition",
                    isEnabled ? "text-muted-foreground hover:text-foreground" : "cursor-not-allowed text-muted-foreground/55",
                  )}
                >
                  <span
                    className={cn(
                      "h-2.5 w-2.5 rounded-full ring-2 ring-background transition",
                      isBlocked
                        ? "bg-status-blocked"
                        : isActive
                          ? "bg-primary"
                          : isCompleted
                            ? "bg-status-done"
                            : "bg-muted-foreground/40 group-hover:bg-muted-foreground/65",
                    )}
                    aria-hidden="true"
                  />
                  <span>{item.label}</span>
                </button>
              </div>
            );
          })}
        </div>

        <Button
          type="button"
          variant="outline"
          size="sm"
          className="h-8 w-fit rounded-full px-3 text-[12px]"
          onClick={onDispatch}
          disabled={!dispatchableTask || hasUnresolvedStartedWork || dispatchingTaskId === dispatchableTask.id}
          aria-label={dispatchLabel}
          title={dispatchLabel}
        >
          <Play className="h-3.5 w-3.5" />
          {dispatchButtonLabel}
        </Button>
      </div>
    </div>
  );
}
