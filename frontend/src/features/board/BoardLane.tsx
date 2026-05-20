import { EmptyState, StatusDot, SurfacePanel } from "@/design-system";
import { TaskCard } from "@/components/agent-native";
import type { TaskBoardItem } from "@/lib/types";

export function BoardLane({
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
        "flex min-h-[320px] flex-col space-y-3 px-3 py-3 sm:px-3.5 sm:py-3.5",
        tone === "blocked" ? "hatch" : "",
      ].join(" ")}
      style={{
        background: `oklch(from var(--status-${tone}) l c h / 0.04)`,
      }}
    >
      <div className="border-b border-border/60 pb-2.5">
        <div className="flex h-7 items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2">
            <StatusDot tone={tone} pulse={tone === "active"} className="h-2 w-2" />
            <span className="truncate text-[12px] font-medium text-foreground">{title}</span>
          </div>
          <span className="rounded-full bg-[color-mix(in_oklab,var(--status-active)_9%,transparent)] px-2 py-0.5 font-mono text-[10.5px] text-muted-foreground">
            {tasks.length}
          </span>
        </div>
      </div>
      {tasks.length === 0 ? (
        <EmptyState
          className="flex-1 rounded-[0.85rem] px-3 py-8"
          label={`No ${title.toLowerCase()} work right now.`}
          detail="Empty lane."
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
