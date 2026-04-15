import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { fetchBoard } from "@/lib/api";
import { useBoardAnimations } from "@/hooks/use-board-animations";
import type { BoardData, TaskBoardItem } from "@/lib/types";

const PHASE_STEPS = ["Plan", "Design", "Implement", "Gates", "PR", "Build"];

const STATUS_TO_PHASE: Record<string, number> = {
  planning: 0,
  design: 1,
  design_review: 1,
  implementation: 2,
  quality_gates: 3,
  pr_creation: 4,
  review_pending: 4,
  build_verify: 5,
  done: 6,
};

const STATUS_VARIANT: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  pending: "secondary",
  planning: "default",
  design: "default",
  design_review: "outline",
  implementation: "default",
  quality_gates: "outline",
  pr_creation: "default",
  review_pending: "outline",
  build_verify: "default",
  done: "secondary",
  blocked: "destructive",
  capability_limit: "destructive",
  failed: "destructive",
};

type SectionKey = "active" | "review" | "pending" | "done" | "blocked";

const SECTION_STYLE: Record<SectionKey, { dot: string; bg: string; label: string }> = {
  active:  { dot: "bg-status-active",  bg: "bg-status-active/5",  label: "text-status-active" },
  review:  { dot: "bg-status-review",  bg: "bg-status-review/5",  label: "text-status-review" },
  pending: { dot: "bg-status-pending", bg: "bg-status-pending/5", label: "text-status-pending" },
  done:    { dot: "bg-status-done",    bg: "bg-status-done/5",    label: "text-status-done" },
  blocked: { dot: "bg-status-blocked", bg: "bg-status-blocked/5", label: "text-status-blocked" },
};

function TaskCard({ task, isActive }: { task: TaskBoardItem; isActive?: boolean }) {
  return (
    <Card className="group relative transition-all duration-200 hover:shadow-lg hover:-translate-y-0.5 overflow-hidden">
      {isActive && (
        <div className="absolute top-3 right-3">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-status-active opacity-75" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-status-active" />
          </span>
        </div>
      )}
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-2 pr-4">
          <div className="min-w-0">
            <CardTitle className="text-sm font-semibold leading-tight truncate">
              {task.title}
            </CardTitle>
            <p className="text-[11px] text-muted-foreground mt-0.5 truncate">
              {task.feature_title}
            </p>
          </div>
          <Badge variant={STATUS_VARIANT[task.status] ?? "secondary"} className="shrink-0 text-[10px] uppercase tracking-wider">
            {task.status.replace(/_/g, " ")}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="pt-0 space-y-2.5">
        {task.agent_name && (
          <div className="flex items-center justify-between">
            <Badge variant="outline" className="text-[10px] font-mono">
              {task.agent_name}
            </Badge>
            <span className="font-mono text-[11px] text-muted-foreground tabular-nums">
              ${task.cost_usd.toFixed(4)}
            </span>
          </div>
        )}
        {task.total_cost > 0 && (
          <div className="flex gap-4 text-[11px] text-muted-foreground font-mono tabular-nums">
            <span>
              Total: <strong className="text-foreground">${task.total_cost.toFixed(4)}</strong>
            </span>
            {task.num_turns > 0 && <span>{task.num_turns} turns</span>}
            {task.duration_ms > 0 && <span>{(task.duration_ms / 1000).toFixed(1)}s</span>}
          </div>
        )}
        {task.blocked_reason && (
          <p className="text-[11px] text-status-blocked truncate font-medium">
            {task.blocked_reason}
          </p>
        )}
        {task.approval_gate_id && (
          <Button asChild size="sm" className="w-full mt-1 h-7 text-xs">
            <Link to={`/approvals/${task.approval_gate_id}`}>Review &rarr;</Link>
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

function Stepper({ status }: { status?: string }) {
  const current = status ? (STATUS_TO_PHASE[status] ?? -1) : -1;
  return (
    <div className="flex items-center gap-0 rounded-lg border border-border/50 bg-muted/30 p-2.5 mb-4 overflow-x-auto">
      {PHASE_STEPS.map((step, i) => (
        <div key={step} className="flex items-center">
          <div className="flex items-center gap-1.5 px-2.5 py-1">
            <div className="relative">
              <div
                className={`h-2 w-2 rounded-full transition-all duration-300 ${
                  i < current
                    ? "bg-status-active"
                    : i === current
                    ? "bg-status-active ring-[3px] ring-status-active/25"
                    : "bg-muted-foreground/25"
                }`}
              />
              {i === current && (
                <div className="absolute inset-0 h-2 w-2 rounded-full bg-status-active animate-ping opacity-40" />
              )}
            </div>
            <span
              className={`text-[10px] font-semibold tracking-wide uppercase whitespace-nowrap transition-colors ${
                i < current
                  ? "text-status-active"
                  : i === current
                  ? "text-foreground"
                  : "text-muted-foreground/60"
              }`}
            >
              {step}
            </span>
          </div>
          {i < PHASE_STEPS.length - 1 && (
            <div
              className={`h-px w-6 transition-colors duration-300 ${
                i < current ? "bg-status-active" : "bg-border"
              }`}
            />
          )}
        </div>
      ))}
    </div>
  );
}

interface SectionProps {
  title: string;
  count: number;
  tasks: TaskBoardItem[];
  sectionKey: SectionKey;
  showStepper?: boolean;
  activeStatus?: string;
  defaultOpen?: boolean;
}

function PipelineSection({
  title,
  count,
  tasks,
  sectionKey,
  showStepper,
  activeStatus,
  defaultOpen = true,
}: SectionProps) {
  const [open, setOpen] = useState(defaultOpen);
  const style = SECTION_STYLE[sectionKey];

  if (count === 0 && !defaultOpen) return null;

  return (
    <section
      className="rounded-xl border bg-card shadow-sm transition-shadow hover:shadow-md"
    >
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-3 p-5 text-left"
      >
        <div className={`h-2.5 w-2.5 rounded-full ${style.dot} ${sectionKey === "active" && count > 0 ? "animate-status-pulse" : ""}`} />
        <h2 className="text-sm font-bold uppercase tracking-wider">{title}</h2>
        <span className={`font-mono text-xs font-semibold tabular-nums ${style.label}`}>
          {count}
        </span>
        <span className="ml-auto text-xs text-muted-foreground font-medium">
          {open ? "collapse" : "expand"}
        </span>
      </button>

      {open && (
        <div className="px-5 pb-5">
          {showStepper && <Stepper status={activeStatus} />}
          {tasks.length > 0 ? (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
              {tasks.map((t) => (
                <TaskCard key={t.id} task={t} isActive={sectionKey === "active"} />
              ))}
            </div>
          ) : (
            <div className={`py-8 text-center text-sm text-muted-foreground rounded-lg ${style.bg}`}>
              No tasks
            </div>
          )}
        </div>
      )}
    </section>
  );
}

export default function BoardPage() {
  const animRef = useBoardAnimations();
  const [board, setBoard] = useState<BoardData | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    fetchBoard()
      .then(setBoard)
      .catch((e) => setError(e.message));
  };

  useEffect(() => {
    load();
    const interval = setInterval(load, 3000);
    return () => clearInterval(interval);
  }, []);

  if (error) {
    return (
      <div className="py-20 text-center">
        <div className="inline-flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3">
          <div className="h-2 w-2 rounded-full bg-destructive" />
          <p className="text-destructive text-sm font-medium">{error}</p>
        </div>
        <Button variant="ghost" size="sm" onClick={load} className="mt-3">
          Retry
        </Button>
      </div>
    );
  }

  if (!board) {
    return (
      <div className="py-20 text-center space-y-3">
        <div className="inline-flex gap-1">
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className="h-2 w-2 rounded-full bg-muted-foreground/30 animate-pulse"
              style={{ animationDelay: `${i * 150}ms` }}
            />
          ))}
        </div>
        <p className="text-sm text-muted-foreground">Loading pipeline...</p>
      </div>
    );
  }

  const totalTasks =
    board.active.length + board.review.length + board.pending.length + board.done.length + board.blocked.length;

  return (
    <div ref={animRef} className="space-y-5">
      <div className="flex items-baseline justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Task Pipeline</h1>
          <p className="text-xs text-muted-foreground mt-1 font-mono tabular-nums">
            {totalTasks} task{totalTasks !== 1 ? "s" : ""} &middot;{" "}
            {board.active.length} active &middot;{" "}
            {board.review.length} awaiting review
          </p>
        </div>
        <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
          <span className="relative flex h-1.5 w-1.5">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-status-active opacity-75" />
            <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-status-active" />
          </span>
          <span className="uppercase tracking-wider font-medium">Live</span>
        </div>
      </div>

      <Separator />

      <div className="space-y-4">
        <PipelineSection
          title="In Progress"
          count={board.active.length}
          tasks={board.active}
          sectionKey="active"
          showStepper
          activeStatus={board.active[0]?.status}
          defaultOpen
        />
        <PipelineSection
          title="Awaiting Review"
          count={board.review.length}
          tasks={board.review}
          sectionKey="review"
          defaultOpen
        />
        <PipelineSection
          title="Pending"
          count={board.pending.length}
          tasks={board.pending}
          sectionKey="pending"
          defaultOpen
        />
        <PipelineSection
          title="Done"
          count={board.done.length}
          tasks={board.done}
          sectionKey="done"
          defaultOpen={false}
        />
        <PipelineSection
          title="Blocked"
          count={board.blocked.length}
          tasks={board.blocked}
          sectionKey="blocked"
          defaultOpen={false}
        />
      </div>
    </div>
  );
}
