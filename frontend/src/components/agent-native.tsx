import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { AgentRunItem, DiffSummary, TaskBoardItem, TodoSnapshot } from "@/lib/types";
import {
  Meter,
  StatusDot,
  StatusPill,
  SurfacePanel,
} from "@/components/workspace";
import { toStatusTone, type StatusTone } from "@/lib/status";

export function LivePulse({
  running,
  label,
  className,
}: {
  running: boolean;
  label: string;
  className?: string;
}) {
  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <span className="relative inline-flex h-2 w-2">
        <span
          className={cn(
            "relative inline-flex h-2 w-2 rounded-full",
            running ? "bg-status-active" : "bg-muted-foreground/40",
          )}
        />
        {running ? (
          <>
            <span
              className="absolute inset-0 rounded-full bg-status-active"
              style={{ animation: "pulse-ring 1.8s ease-out infinite" }}
            />
            <span
              className="absolute -inset-1 rounded-full breathe"
              style={{ background: "var(--status-active-soft)" }}
            />
          </>
        ) : null}
      </span>
      <span
        className={cn(
          "font-mono text-[10.5px] uppercase tracking-[0.18em]",
          running ? "text-foreground/80" : "text-muted-foreground",
        )}
      >
        {label}
      </span>
    </span>
  );
}

export function Sparkline({
  data,
  height = 32,
  className,
}: {
  data: number[];
  height?: number;
  className?: string;
}) {
  if (data.length < 2) return null;
  const max = Math.max(...data, 0.0001);
  const min = Math.min(...data);
  const range = max - min || 1;
  const pts = data
    .map((v, i) => {
      const x = (i / (data.length - 1)) * 100;
      const y = 100 - ((v - min) / range) * 100;
      return `${x},${y.toFixed(2)}`;
    })
    .join(" ");
  const area = `0,100 ${pts} 100,100`;
  return (
    <svg
      viewBox="0 0 100 100"
      preserveAspectRatio="none"
      className={cn("block w-full", className)}
      style={{ height }}
      aria-hidden="true"
    >
      <polygon points={area} fill="var(--primary)" opacity="0.12" />
      <polyline
        points={pts}
        fill="none"
        stroke="var(--primary)"
        strokeWidth="1.2"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

export function CostMeter({
  value,
  budget,
  sparkline,
  label = "Run cost",
  className,
}: {
  value: number;
  budget?: number;
  sparkline?: number[];
  label?: string;
  className?: string;
}) {
  const pct = budget ? Math.min(value / budget, 1) : 0;
  const over = pct > 0.8;
  return (
    <div className={cn("space-y-2", className)}>
      <div className="flex items-baseline justify-between gap-3">
        <div>
          <p className="font-mono text-[10.5px] uppercase tracking-[0.18em] text-muted-foreground">
            {label}
          </p>
          <p className="mt-1 font-mono text-[22px] leading-none tabular-nums text-foreground">
            ${value.toFixed(4)}
          </p>
        </div>
        {budget ? (
          <div className="text-right">
            <p className="font-mono text-[10.5px] uppercase tracking-[0.18em] text-muted-foreground">
              Budget
            </p>
            <p
              className={cn(
                "mt-1 font-mono text-[12px] tabular-nums",
                over ? "text-status-review" : "text-muted-foreground",
              )}
            >
              of ${budget.toFixed(2)}
            </p>
          </div>
        ) : null}
      </div>
      {budget ? (
        <div className="meter-track" style={{ height: 3 }}>
          <div
            className="meter-fill"
            style={{
              width: `${pct * 100}%`,
              background: over ? "var(--status-review)" : "var(--primary)",
            }}
          />
        </div>
      ) : null}
      {sparkline && sparkline.length > 1 ? <Sparkline data={sparkline} /> : null}
    </div>
  );
}

export function ProgressMeter({
  current,
  max,
  label = "Turns",
  className,
}: {
  current: number;
  max: number;
  label?: string;
  className?: string;
}) {
  if (!max) {
    return (
      <div className={cn("flex items-center justify-between gap-3 text-[12.5px]", className)}>
        <span className="text-muted-foreground">{label}</span>
        <span className="font-mono tabular-nums text-foreground">{current}</span>
      </div>
    );
  }
  const ratio = max > 0 ? current / max : 0;
  return (
    <div className={cn("space-y-1.5", className)}>
      <div className="flex items-center justify-between gap-2 text-[11px]">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-mono tabular-nums text-foreground/80">
          {current} / {max}
        </span>
      </div>
      <div className="meter-track">
        <div
          className="meter-fill bg-status-active"
          style={{ width: `${Math.min(ratio, 1) * 100}%` }}
        />
      </div>
    </div>
  );
}

export interface TimelineLogItem {
  id: string;
  type: string;
  timestamp: string;
  tool_name?: string;
  summary?: string;
  preview?: string;
}

export function LogBlock({
  items,
  emptyLabel,
  maxHeight = 360,
  className,
}: {
  items: TimelineLogItem[];
  emptyLabel?: string;
  maxHeight?: number;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "overflow-hidden rounded-[1rem] border border-border/70 font-mono",
        className,
      )}
      style={{
        background: "var(--background-sunk)",
        fontSize: "12px",
        lineHeight: 1.6,
      }}
    >
      <div
        className="flex items-center justify-between border-b border-border/60 px-3 py-1.5"
        style={{ background: "oklch(from var(--foreground) l c h / 0.03)" }}
      >
        <span className="text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
          builder · log stream
        </span>
        <span className="text-[10px] text-muted-foreground">{items.length} entries</span>
      </div>
      <div className="overflow-auto p-3" style={{ maxHeight }}>
        {items.length === 0 ? (
          <div className="py-6 text-center text-[11.5px] text-muted-foreground">
            {emptyLabel ?? "No log events yet."}
          </div>
        ) : (
          items.map((item, idx) => {
            const color =
              item.type === "tool_error"
                ? "text-status-blocked"
                : item.type === "specialist_status"
                  ? "text-status-active"
                  : item.type === "todo_snapshot"
                    ? "text-status-review"
                    : "text-foreground/80";
            const glyph =
              item.type === "tool_error"
                ? "!"
                : item.type === "specialist_status"
                  ? "*"
                  : item.type === "todo_snapshot"
                    ? "▲"
                    : "$";
            return (
              <div key={item.id} className="flex gap-3">
                <span className="w-8 shrink-0 select-none text-right text-muted-foreground">
                  {String(idx + 1).padStart(3, "0")}
                </span>
                <span className={cn("shrink-0", color)}>{glyph}</span>
                <span className="min-w-0 whitespace-pre-wrap text-foreground/85">
                  <span className={cn("font-semibold", color)}>
                    {item.tool_name ?? item.type}
                  </span>
                  {item.summary ? <> · {item.summary}</> : null}
                  {item.preview ? (
                    <span className="block text-muted-foreground">{item.preview}</span>
                  ) : null}
                </span>
              </div>
            );
          })
        )}
        <span
          className="ml-[52px] mt-1 inline-block h-[13px] w-[7px] align-middle blink"
          style={{ background: "var(--primary)" }}
          aria-hidden="true"
        />
      </div>
    </div>
  );
}

export type TimelineKind = "user" | "thinking" | "tool" | "gate";

export interface TimelineEntry {
  id: string;
  kind: TimelineKind;
  timestamp: string;
  label?: string;
  status?: string;
  body?: ReactNode;
  args?: string;
  result?: string;
}

function kindGlyph(kind: TimelineKind) {
  if (kind === "user") {
    return (
      <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
        <circle cx="6" cy="4" r="2.4" stroke="currentColor" strokeWidth="1.2" />
        <path
          d="M2 10c.6-1.8 2.2-3 4-3s3.4 1.2 4 3"
          stroke="currentColor"
          strokeWidth="1.2"
          strokeLinecap="round"
        />
      </svg>
    );
  }
  if (kind === "thinking") {
    return (
      <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
        <circle cx="6" cy="6" r="2.2" stroke="currentColor" strokeWidth="1.2" />
        <circle cx="6" cy="6" r="4.8" stroke="currentColor" strokeWidth="0.8" opacity="0.5" />
      </svg>
    );
  }
  if (kind === "tool") {
    return (
      <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
        <path d="M3 3h6v6H3z" stroke="currentColor" strokeWidth="1.2" />
        <path
          d="M5 1v2M7 1v2M5 9v2M7 9v2M1 5h2M1 7h2M9 5h2M9 7h2"
          stroke="currentColor"
          strokeWidth="1.2"
          strokeLinecap="round"
        />
      </svg>
    );
  }
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
      <path
        d="M2 6l3 3 5-6"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

const KIND_COLOR: Record<TimelineKind, string> = {
  user: "text-foreground/80",
  thinking: "text-primary",
  tool: "text-foreground/70",
  gate: "text-status-review",
};

export function AgentTimeline({ entries }: { entries: TimelineEntry[] }) {
  if (entries.length === 0) {
    return (
      <p className="rounded-[1.2rem] border border-dashed border-border/60 bg-background/55 px-4 py-4 text-sm text-muted-foreground">
        The timeline will populate as the agent reasons, calls tools, and triggers gates.
      </p>
    );
  }
  return (
    <div className="relative">
      <div
        className="absolute bottom-0 top-0 w-px bg-border"
        style={{ left: 15 }}
        aria-hidden="true"
      />
      <div className="space-y-4">
        {entries.map((entry) => (
          <div key={entry.id} className="relative pl-10" style={{ animation: "fade-up 420ms var(--ease-emphasized)" }}>
            <div
              className={cn(
                "absolute left-0 top-0.5 grid h-[31px] w-[31px] place-items-center rounded-full border border-border bg-background",
                KIND_COLOR[entry.kind],
              )}
            >
              {kindGlyph(entry.kind)}
            </div>
            <div className="mb-1 flex flex-wrap items-center gap-2">
              <span className="font-mono text-[10.5px] uppercase tracking-[0.16em] text-foreground/75">
                {entry.kind}
                {entry.label ? ` · ${entry.label}` : ""}
              </span>
              {entry.status ? <StatusPill status={entry.status} /> : null}
              <span className="ml-auto font-mono text-[10.5px] text-muted-foreground">
                {entry.timestamp}
              </span>
            </div>
            {entry.kind === "tool" ? (
              <div className="space-y-1 rounded-[0.7rem] border border-border/70 bg-background-sunk p-2 font-mono text-[11.5px]">
                {entry.args ? (
                  <div className="flex gap-2">
                    <span className="text-muted-foreground">args</span>
                    <span className="text-foreground/80">{entry.args}</span>
                  </div>
                ) : null}
                {entry.result ? (
                  <div className="flex gap-2">
                    <span className="text-muted-foreground">→</span>
                    <span className="text-status-done">{entry.result}</span>
                  </div>
                ) : null}
              </div>
            ) : entry.kind === "thinking" ? (
              <p className="display-serif text-[13.5px] leading-[1.6] text-foreground/80">
                {entry.body}
              </p>
            ) : (
              <div className="text-[13.5px] leading-[1.55] text-foreground">{entry.body}</div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

export function TodoStrip({
  snapshot,
  className,
}: {
  snapshot: TodoSnapshot | null | undefined;
  className?: string;
}) {
  if (!snapshot) return null;
  const total = snapshot.in_progress_count + snapshot.pending_count + snapshot.completed_count;
  const completedPct = total > 0 ? snapshot.completed_count / total : 0;
  return (
    <div className={cn("space-y-2", className)}>
      <div className="flex items-center justify-between gap-2 text-[11px]">
        <span className="font-mono uppercase tracking-[0.18em] text-muted-foreground">
          Todos · {snapshot.session_id.slice(0, 8)}
        </span>
        <span className="font-mono tabular-nums text-foreground/80">
          {snapshot.completed_count}/{total || 0}
        </span>
      </div>
      <div className="meter-track">
        <div
          className="meter-fill bg-status-done"
          style={{ width: `${completedPct * 100}%` }}
        />
      </div>
      <div className="flex items-center gap-3 text-[10.5px] text-muted-foreground">
        <span className="inline-flex items-center gap-1.5">
          <StatusDot tone="active" pulse={snapshot.in_progress_count > 0} className="h-1.5 w-1.5" />
          {snapshot.in_progress_count} active
        </span>
        <span className="inline-flex items-center gap-1.5">
          <StatusDot tone="pending" className="h-1.5 w-1.5" />
          {snapshot.pending_count} pending
        </span>
        <span className="inline-flex items-center gap-1.5">
          <StatusDot tone="done" className="h-1.5 w-1.5" />
          {snapshot.completed_count} done
        </span>
      </div>
    </div>
  );
}

export function MCPChips({
  servers,
  tools,
  permissionMode,
  className,
}: {
  servers: string[];
  tools: string[];
  permissionMode: string;
  className?: string;
}) {
  const serverCount = servers.length;
  const toolCount = tools.length;
  return (
    <div className={cn("space-y-2", className)}>
      <p className="font-mono text-[10.5px] uppercase tracking-[0.18em] text-muted-foreground">
        Capability surface
      </p>
      <div className="flex flex-wrap gap-1.5">
        <Badge variant="outline" className="font-mono text-[10px] uppercase tracking-[0.14em]">
          mode · {permissionMode}
        </Badge>
        <Badge variant="outline" className="font-mono text-[10px] uppercase tracking-[0.14em]">
          mcp · {serverCount}
        </Badge>
        <Badge variant="outline" className="font-mono text-[10px] uppercase tracking-[0.14em]">
          tools · {toolCount}
        </Badge>
      </div>
      {toolCount > 0 ? (
        <p className="line-clamp-2 text-[11px] leading-[1.4] text-muted-foreground">
          {tools.slice(0, 8).join(" · ")}
          {tools.length > 8 ? ` · +${tools.length - 8} more` : ""}
        </p>
      ) : null}
    </div>
  );
}

function formatDuration(durationMs: number) {
  const seconds = Math.round(durationMs / 1000);
  if (!seconds) return "0s";
  if (seconds < 60) return `${seconds}s`;
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

const TASK_PROGRESS: Record<string, number> = {
  pending: 0.02,
  planning: 0.15,
  design: 0.3,
  design_review: 0.35,
  implementation: 0.55,
  quality_gates: 0.7,
  pr_creation: 0.82,
  review_pending: 0.86,
  build_verify: 0.92,
  done: 1,
  completed: 1,
  blocked: 0.5,
  failed: 0.5,
  capability_limit: 0.4,
};

export function TaskCard({
  task,
  density = "comfortable",
  className,
}: {
  task: TaskBoardItem;
  density?: "comfortable" | "compact";
  className?: string;
}) {
  const tone = toStatusTone(task.status);
  const pulseActive = tone === "active";
  const progress = TASK_PROGRESS[task.status] ?? 0;
  return (
    <div
      className={cn(
        "relative rounded-[1rem] border border-border/75 bg-background/70 transition hover:-translate-y-px hover:border-border hover:shadow-[var(--shadow-md)]",
        density === "compact" ? "space-y-2 px-3 py-3" : "space-y-3 px-4 py-4",
        className,
      )}
    >
      {pulseActive ? (
        <span className="absolute right-3 top-3" aria-hidden="true">
          <StatusDot tone="active" pulse className="h-2 w-2" />
        </span>
      ) : null}
      <div className="flex items-start justify-between gap-3 pr-5">
        <div className="min-w-0 space-y-1">
          <div className="flex items-center gap-2">
            <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
              {task.id.slice(0, 8)}
            </span>
            <StatusPill status={task.status} />
          </div>
          <p className="truncate text-[14px] font-medium leading-[1.35] text-foreground">
            {task.title}
          </p>
          <p className="truncate text-[11px] text-muted-foreground">
            {task.feature_title || "Feature"}
            {task.agent_name ? (
              <>
                {" · "}
                <span className="font-mono">{task.agent_name}</span>
              </>
            ) : null}
          </p>
        </div>
      </div>

      {progress > 0 ? <Meter value={progress} tone={tone as StatusTone} showValue={false} /> : null}

      {task.blocked_reason ? (
        <div
          className="hatch rounded-[0.6rem] border border-dashed border-status-blocked/35 px-2 py-1.5 text-[11.5px] text-status-blocked"
        >
          {task.blocked_reason}
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-3 font-mono text-[10.5px] text-muted-foreground">
        <span>${task.cost_usd.toFixed(4)}</span>
        <span>{task.num_turns} turns</span>
        {task.duration_ms > 0 ? <span>{formatDuration(task.duration_ms)}</span> : null}
        {task.pending_approval_count > 0 ? (
          <span className="text-status-review">
            {task.pending_approval_count} pending approval
          </span>
        ) : null}
        {task.approval_gate_id ? (
          <Button asChild variant="ghost" className="ml-auto h-7 rounded-full px-2">
            <Link to={`/approvals/${task.approval_gate_id}`} className="inline-flex items-center gap-1 text-[11px]">
              Review
              <ArrowRight className="h-3 w-3" />
            </Link>
          </Button>
        ) : null}
      </div>
    </div>
  );
}

const CONFIDENCE_SEGMENTS = 10;

function confidenceTone(value: number): StatusTone {
  if (value > 0.75) return "done";
  if (value > 0.5) return "active";
  if (value > 0.25) return "review";
  return "blocked";
}

const CONFIDENCE_SEGMENT_FILL: Record<StatusTone, string> = {
  active: "bg-status-active",
  review: "bg-status-review",
  pending: "bg-status-pending",
  done: "bg-status-done",
  blocked: "bg-status-blocked",
  muted: "bg-muted-foreground/35",
};

export function ConfidenceBar({
  value,
  className,
}: {
  value: number | null | undefined;
  className?: string;
}) {
  if (value == null) {
    return (
      <div className={cn("flex items-center gap-2", className)}>
        <span className="font-mono text-[10.5px] uppercase tracking-[0.18em] text-muted-foreground">
          Conf
        </span>
        <div className="flex gap-[2px]" aria-hidden="true">
          {Array.from({ length: CONFIDENCE_SEGMENTS }).map((_, i) => (
            <span
              key={i}
              className="block h-[10px] w-[6px] rounded-[2px] bg-muted-foreground/20"
            />
          ))}
        </div>
        <span className="font-mono text-[10.5px] text-muted-foreground">not captured</span>
      </div>
    );
  }
  const clamped = Math.max(0, Math.min(1, value));
  const filled = Math.round(clamped * CONFIDENCE_SEGMENTS);
  const tone = confidenceTone(clamped);
  return (
    <div className={cn("flex items-center gap-2", className)}>
      <span className="font-mono text-[10.5px] uppercase tracking-[0.18em] text-muted-foreground">
        Conf
      </span>
      <div className="flex gap-[2px]">
        {Array.from({ length: CONFIDENCE_SEGMENTS }).map((_, i) => (
          <span
            key={i}
            className={cn(
              "block h-[10px] w-[6px] rounded-[2px]",
              i < filled ? CONFIDENCE_SEGMENT_FILL[tone] : "bg-muted-foreground/15",
            )}
          />
        ))}
      </div>
      <span className="font-mono text-[11px] tabular-nums text-foreground/85">
        {(clamped * 100).toFixed(0)}
      </span>
    </div>
  );
}

export function DiffBlock({
  diff,
  maxHunks = 3,
  className,
}: {
  diff: DiffSummary | null | undefined;
  maxHunks?: number;
  className?: string;
}) {
  if (!diff || diff.files_changed === 0) {
    return (
      <div
        className={cn(
          "rounded-[1rem] border border-dashed border-border/60 bg-background/55 px-4 py-3 text-[12px] text-muted-foreground",
          className,
        )}
      >
        No workspace changes captured for this run.
      </div>
    );
  }
  const hunks = diff.hunks.slice(0, maxHunks);
  return (
    <div
      className={cn(
        "overflow-hidden rounded-[1rem] border border-border/70 bg-background/60",
        className,
      )}
    >
      <div className="flex flex-wrap items-center gap-3 border-b border-border/60 bg-muted/30 px-4 py-2 font-mono text-[10.5px] uppercase tracking-[0.16em] text-muted-foreground">
        <span>{diff.files_changed} file{diff.files_changed === 1 ? "" : "s"}</span>
        <span className="text-status-done">+{diff.insertions}</span>
        <span className="text-status-blocked">−{diff.deletions}</span>
        {diff.hunks.length > maxHunks ? (
          <span className="ml-auto">showing {maxHunks} of {diff.hunks.length} hunks</span>
        ) : null}
      </div>
      <div className="divide-y divide-border/60">
        {hunks.map((hunk, idx) => (
          <div key={`${hunk.file}-${idx}`} className="px-4 py-3">
            <div className="mb-2 flex items-center justify-between gap-3">
              <span className="truncate font-mono text-[12px] text-foreground/90">{hunk.file}</span>
              <span className="shrink-0 font-mono text-[10.5px] text-muted-foreground">
                <span className="text-status-done">+{hunk.added_lines}</span>
                {" / "}
                <span className="text-status-blocked">−{hunk.removed_lines}</span>
              </span>
            </div>
            {hunk.preview ? (
              <pre className="max-h-[200px] overflow-auto whitespace-pre-wrap break-words font-mono text-[11.5px] leading-5 text-foreground/80">
                {hunk.preview.split("\n").map((line, i) => {
                  const prefix = line[0];
                  let bg = "transparent";
                  let color = "var(--foreground)";
                  if (prefix === "+") {
                    bg = "var(--diff-added-bg)";
                    color = "var(--diff-added-fg)";
                  } else if (prefix === "-") {
                    bg = "var(--diff-removed-bg)";
                    color = "var(--diff-removed-fg)";
                  } else if (prefix === "@") {
                    color = "var(--primary)";
                  }
                  return (
                    <span
                      key={i}
                      style={{ background: bg, color, display: "block", padding: "0 6px" }}
                    >
                      {line || " "}
                    </span>
                  );
                })}
              </pre>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
}

export function AgentRunSummary({
  run,
  className,
}: {
  run: AgentRunItem;
  className?: string;
}) {
  return (
    <SurfacePanel className={cn("space-y-2", className)}>
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-[10.5px] uppercase tracking-[0.18em] text-muted-foreground">
          Run · {run.agent_name}
        </span>
        <StatusPill status={run.status} />
      </div>
      <div className="grid grid-cols-2 gap-2 text-[12px]">
        <div className="flex items-center justify-between">
          <span className="text-muted-foreground">Cost</span>
          <span className="font-mono tabular-nums">${run.cost_usd.toFixed(4)}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-muted-foreground">Turns</span>
          <span className="font-mono tabular-nums">{run.num_turns}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-muted-foreground">Tokens</span>
          <span className="font-mono tabular-nums">
            {(run.tokens_input + run.tokens_output).toLocaleString()}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-muted-foreground">Duration</span>
          <span className="font-mono tabular-nums">{formatDuration(run.duration_ms)}</span>
        </div>
      </div>
    </SurfacePanel>
  );
}
