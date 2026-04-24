import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Play } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  PageFrame,
  PageHeader,
  StatusDot,
  SurfacePanel,
} from "@/components/workspace";
import { dispatchTask, fetchBoard, openBoardStream } from "@/lib/api";
import type { BoardData, TaskBoardItem } from "@/lib/types";

type LaneKey = keyof BoardData;

const LANE_ORDER: Array<{ key: LaneKey; title: string; tone: "active" | "review" | "pending" | "done" | "blocked" }> = [
  { key: "active", title: "In progress", tone: "active" },
  { key: "review", title: "Needs review", tone: "review" },
  { key: "pending", title: "Queued", tone: "pending" },
  { key: "done", title: "Shipped", tone: "done" },
  { key: "blocked", title: "Blocked", tone: "blocked" },
];

function formatDuration(durationMs: number) {
  const seconds = Math.round(durationMs / 1000);
  if (!seconds) return "0s";
  if (seconds < 60) return `${seconds}s`;
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

function BoardCard({
  task,
  density,
}: {
  task: TaskBoardItem;
  density: "comfortable" | "compact";
}) {
  return (
    <div
      className={[
        "rounded-[1rem] border border-border/75 bg-background/70 transition hover:border-border hover:bg-background/90",
        density === "compact" ? "space-y-2 px-3 py-3" : "space-y-3 px-4 py-4",
      ].join(" ")}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <p className="truncate text-sm font-medium text-foreground">{task.title}</p>
          <p className="truncate text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
            {task.feature_title || "Feature"}
          </p>
        </div>
        {task.approval_gate_id ? <Badge variant="outline">{task.approval_gate_type || "approval"}</Badge> : null}
      </div>

      <div className="flex flex-wrap gap-2 text-[11px] text-muted-foreground">
        <span>{task.agent_name || "No run yet"}</span>
        <span>{task.latest_run_status || task.status}</span>
        <span>${task.cost_usd.toFixed(4)}</span>
        <span>{task.num_turns} turns</span>
        <span>{formatDuration(task.duration_ms)}</span>
      </div>

      {task.blocked_reason ? (
        <p className="text-xs text-status-blocked">{task.blocked_reason}</p>
      ) : null}

      <div className="flex items-center justify-between gap-3 text-[11px] text-muted-foreground">
        <span>{task.pending_approval_count ? `${task.pending_approval_count} pending approval` : "No pending approval"}</span>
        {task.approval_gate_id ? (
          <Button asChild variant="ghost" className="h-8 rounded-full px-3">
            <Link to={`/approvals/${task.approval_gate_id}`}>
              Review
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </Button>
        ) : null}
      </div>
    </div>
  );
}

function Lane({
  title,
  tasks,
  density,
  tone,
}: {
  title: string;
  tasks: TaskBoardItem[];
  density: "comfortable" | "compact";
  tone: "active" | "review" | "pending" | "done" | "blocked";
}) {
  return (
    <SurfacePanel
      className="flex min-h-[400px] flex-col space-y-4"
      style={{
        background: `oklch(from var(--status-${tone}) l c h / 0.04)`,
        backgroundImage: tone === "blocked"
          ? `repeating-linear-gradient(135deg, oklch(from var(--status-${tone}) l c h / 0.07) 0 1px, transparent 1px 10px)`
          : undefined,
      }}
    >
      <div className="flex h-10 items-center justify-between gap-2 border-b border-border/60 pb-3">
        <div className="flex min-w-0 items-center gap-2">
          <StatusDot tone={tone} pulse={tone === "active"} className="h-2 w-2" />
          <span className="truncate text-[12px] font-medium text-foreground">{title}</span>
        </div>
        <span className="font-mono text-[11px] text-muted-foreground">{tasks.length}</span>
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
            <BoardCard key={task.id} task={task} density={density} />
          ))}
        </div>
      )}
    </SurfacePanel>
  );
}

export default function BoardPage() {
  const density: "comfortable" | "compact" = "comfortable";
  const [board, setBoard] = useState<BoardData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dispatchingTaskId, setDispatchingTaskId] = useState<string | null>(null);
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
    const stream = openBoardStream((data) => {
      if (!active) return;
      receivedSnapshot = true;
      setBoard(data);
      setError(null);
    });

    stream.onerror = () => {
      if (!active) return;
      if (!receivedSnapshot) {
        void loadFallback();
      }
    };

    return () => {
      active = false;
      stream.close();
    };
  }, [streamKey]);

  const pendingTask = board?.pending[0] ?? null;

  const handleDispatch = async () => {
    if (!pendingTask) return;
    setDispatchingTaskId(pendingTask.id);
    try {
      await dispatchTask(pendingTask.id);
    } catch (dispatchError) {
      setError(dispatchError instanceof Error ? dispatchError.message : "Failed to dispatch task");
    } finally {
      setDispatchingTaskId(null);
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
        meta={
          <Button
            type="button"
            className="h-9 rounded-full"
            onClick={handleDispatch}
            disabled={!pendingTask || dispatchingTaskId === pendingTask.id}
          >
            <Play className="h-3.5 w-3.5" />
            Dispatch task
          </Button>
        }
      />

      {error ? (
        <div className="mb-4">
          <ErrorState message={error} onRetry={() => setStreamKey((value) => value + 1)} />
        </div>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-5">
        {LANE_ORDER.map((lane) => (
          <Lane
            key={lane.key}
            title={lane.title}
            tasks={board[lane.key]}
            density={density}
            tone={lane.tone}
          />
        ))}
      </div>
    </PageFrame>
  );
}
