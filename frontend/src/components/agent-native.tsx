import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, RotateCcw } from "lucide-react";
import { Button, Code } from "@/design-system";
import { cn } from "@/lib/utils";
import type { AgentRunItem, DiffSummary, TaskBoardItem, TodoSnapshot } from "@/lib/types";
import {
  Meter,
  StatusDot,
  StatusPill,
  SurfacePanel,
} from "@/design-system";
import { toStatusTone, type StatusTone } from "@/lib/status";
import { runtimeCostDisplay } from "@/lib/runtime-cost";

function telemetryTokenCount(item: {
  tokens_input?: number;
  tokens_output?: number;
  tokens_cached?: number;
}): number {
  return Number(item.tokens_input ?? 0) + Number(item.tokens_output ?? 0);
}

function backlogItemDisplayId(value: string): string {
  if (/^[a-z]+-\d+$/i.test(value)) return value;
  return value.slice(0, 8);
}

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
  displayValue,
  className,
}: {
  value: number;
  budget?: number;
  sparkline?: number[];
  label?: string;
  displayValue?: string;
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
            {displayValue ?? `$${value.toFixed(4)}`}
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

export type TimelineKind = "user" | "assistant" | "thinking" | "tool" | "gate";

export interface TimelineEntry {
  id: string;
  kind: TimelineKind;
  timestamp: string;
  label?: string;
  status?: string;
  heading?: string;
  icon?: "codex" | "claude" | "openai";
  body?: ReactNode;
  args?: string;
  result?: string;
  count?: number;
}

function runtimeGlyph(icon?: TimelineEntry["icon"]) {
  if (icon === "codex") {
    return (
      <span
        className="inline-flex h-3.5 w-3.5 items-center justify-center overflow-hidden rounded-[3px] ring-1 ring-black/10"
        aria-hidden="true"
      >
        <svg width="14" height="14" viewBox="0 0 512 509.639" fillRule="evenodd" clipRule="evenodd"><path fill="#fff" d="M115.612 0h280.775C459.974 0 512 52.026 512 115.612v278.415c0 63.587-52.026 115.613-115.613 115.613H115.612C52.026 509.64 0 457.614 0 394.027V115.612C0 52.026 52.026 0 115.612 0z"/><path fillRule="nonzero" d="M412.037 221.764a90.834 90.834 0 004.648-28.67 90.79 90.79 0 00-12.443-45.87c-16.37-28.496-46.738-46.089-79.605-46.089-6.466 0-12.943.683-19.264 2.04a90.765 90.765 0 00-67.881-30.515h-.576c-.059.002-.149.002-.216.002-39.807 0-75.108 25.686-87.346 63.554-25.626 5.239-47.748 21.31-60.682 44.03a91.873 91.873 0 00-12.407 46.077 91.833 91.833 0 0023.694 61.553 90.802 90.802 0 00-4.649 28.67 90.804 90.804 0 0012.442 45.87c16.369 28.504 46.74 46.087 79.61 46.087a91.81 91.81 0 0019.253-2.04 90.783 90.783 0 0067.887 30.516h.576l.234-.001c39.829 0 75.119-25.686 87.357-63.588 25.626-5.242 47.748-21.312 60.682-44.033a91.718 91.718 0 0012.383-46.035 91.83 91.83 0 00-23.693-61.553l-.004-.005zM275.102 413.161h-.094a68.146 68.146 0 01-43.611-15.8 56.936 56.936 0 002.155-1.221l72.54-41.901a11.799 11.799 0 005.962-10.251V241.651l30.661 17.704c.326.163.55.479.596.84v84.693c-.042 37.653-30.554 68.198-68.21 68.273h.001zm-146.689-62.649a68.128 68.128 0 01-9.152-34.085c0-3.904.341-7.817 1.005-11.663.539.323 1.48.897 2.155 1.285l72.54 41.901a11.832 11.832 0 0011.918-.002l88.563-51.137v35.408a1.1 1.1 0 01-.438.94l-73.33 42.339a68.43 68.43 0 01-34.11 9.12 68.359 68.359 0 01-59.15-34.11l-.001.004zm-19.083-158.36a68.044 68.044 0 0135.538-29.934c0 .625-.036 1.731-.036 2.5v83.801l-.001.07a11.79 11.79 0 005.954 10.242l88.564 51.13-30.661 17.704a1.096 1.096 0 01-1.034.093l-73.337-42.375a68.36 68.36 0 01-34.095-59.143 68.412 68.412 0 019.112-34.085l-.004-.003zm251.907 58.621l-88.563-51.137 30.661-17.697a1.097 1.097 0 011.034-.094l73.337 42.339c21.109 12.195 34.132 34.746 34.132 59.132 0 28.604-17.849 54.199-44.686 64.078v-86.308c.004-.032.004-.065.004-.096 0-4.219-2.261-8.119-5.919-10.217zm30.518-45.93c-.539-.331-1.48-.898-2.155-1.286l-72.54-41.901a11.842 11.842 0 00-5.958-1.611c-2.092 0-4.15.558-5.957 1.611l-88.564 51.137v-35.408l-.001-.061a1.1 1.1 0 01.44-.88l73.33-42.303a68.301 68.301 0 0134.108-9.129c37.704 0 68.281 30.577 68.281 68.281a68.69 68.69 0 01-.984 11.545v.005zm-191.843 63.109l-30.668-17.704a1.09 1.09 0 01-.596-.84v-84.692c.016-37.685 30.593-68.236 68.281-68.236a68.332 68.332 0 0143.689 15.804 63.09 63.09 0 00-2.155 1.222l-72.54 41.9a11.794 11.794 0 00-5.961 10.248v.068l-.05 102.23zm16.655-35.91l39.445-22.782 39.444 22.767v45.55l-39.444 22.767-39.445-22.767v-45.535z"/></svg>
      </span>
    );
  }
  if (icon === "claude") {
    return (
      <span
        className="inline-flex h-3.5 w-3.5 items-center justify-center overflow-hidden rounded-[3px] ring-1 ring-black/10"
        aria-hidden="true"
      >
        <svg width="14" height="14" viewBox="0 0 512 509.64" fillRule="evenodd" clipRule="evenodd"><path fill="#D77655" d="M115.612 0h280.775C459.974 0 512 52.026 512 115.612v278.415c0 63.587-52.026 115.612-115.613 115.612H115.612C52.026 509.639 0 457.614 0 394.027V115.612C0 52.026 52.026 0 115.612 0z"/><path fill="#FCF2EE" fillRule="nonzero" d="M142.27 316.619l73.655-41.326 1.238-3.589-1.238-1.996-3.589-.001-12.31-.759-42.084-1.138-36.498-1.516-35.361-1.896-8.897-1.895-8.34-10.995.859-5.484 7.482-5.03 10.717.935 23.683 1.617 35.537 2.452 25.782 1.517 38.193 3.968h6.064l.86-2.451-2.073-1.517-1.618-1.517-36.776-24.922-39.81-26.338-20.852-15.166-11.273-7.683-5.687-7.204-2.451-15.721 10.237-11.273 13.75.935 3.513.936 13.928 10.716 29.749 23.027 38.848 28.612 5.687 4.727 2.275-1.617.278-1.138-2.553-4.271-21.13-38.193-22.546-38.848-10.035-16.101-2.654-9.655c-.935-3.968-1.617-7.304-1.617-11.374l11.652-15.823 6.445-2.073 15.545 2.073 6.547 5.687 9.655 22.092 15.646 34.78 24.265 47.291 7.103 14.028 3.791 12.992 1.416 3.968 2.449-.001v-2.275l1.997-26.641 3.69-32.707 3.589-42.084 1.239-11.854 5.863-14.206 11.652-7.683 9.099 4.348 7.482 10.716-1.036 6.926-4.449 28.915-8.72 45.294-5.687 30.331h3.313l3.792-3.791 15.342-20.372 25.782-32.227 11.374-12.789 13.27-14.129 8.517-6.724 16.1-.001 11.854 17.617-5.307 18.199-16.581 21.029-13.75 17.819-19.716 26.54-12.309 21.231 1.138 1.694 2.932-.278 44.536-9.479 24.062-4.347 28.714-4.928 12.992 6.066 1.416 6.167-5.106 12.613-30.71 7.583-36.018 7.204-53.636 12.689-.657.48.758.935 24.164 2.275 10.337.556h25.301l47.114 3.514 12.309 8.139 7.381 9.959-1.238 7.583-18.957 9.655-25.579-6.066-59.702-14.205-20.474-5.106-2.83-.001v1.694l17.061 16.682 31.266 28.233 39.152 36.397 1.997 8.999-5.03 7.102-5.307-.758-34.401-25.883-13.27-11.651-30.053-25.302-1.996-.001v2.654l6.926 10.136 36.574 54.975 1.895 16.859-2.653 5.485-9.479 3.311-10.414-1.895-21.408-30.054-22.092-33.844-17.819-30.331-2.173 1.238-10.515 113.261-4.929 5.788-11.374 4.348-9.478-7.204-5.03-11.652 5.03-23.027 6.066-30.052 4.928-23.886 4.449-29.674 2.654-9.858-.177-.657-2.173.278-22.37 30.71-34.021 45.977-26.919 28.815-6.445 2.553-11.173-5.789 1.037-10.337 6.243-9.2 37.257-47.392 22.47-29.371 14.508-16.961-.101-2.451h-.859l-98.954 64.251-17.618 2.275-7.583-7.103.936-11.652 3.589-3.791 29.749-20.474-.101.102.024.101z"/></svg>
      </span>
    );
  }
  if (icon === "openai") {
    return (
      <span className="inline-flex h-3.5 w-3.5 items-center justify-center" aria-hidden="true">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
          <path
            d="M12 4.2c2.6-2.3 6.3-.5 6.2 3-.1 1.2-.7 2.2-1.6 2.9 2.2.5 3.4 2.9 2.3 5-1 1.9-3.3 2.5-5.1 1.7-.8 2.6-3.9 3.6-6 1.8-1.1-.9-1.5-2.3-1.1-3.6-2.5-.5-3.8-3.4-2.5-5.5.8-1.3 2.3-1.9 3.7-1.6-.3-2.4 1.9-4.4 4.1-3.7Z"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinejoin="round"
          />
          <path
            d="M8.1 8.1 15.9 16M15.9 8.1 8.1 16M12 4.6v14.8"
            stroke="currentColor"
            strokeWidth="1.3"
            strokeLinecap="round"
          />
        </svg>
      </span>
    );
  }
  return null;
}

function kindGlyph(kind: TimelineKind, icon?: TimelineEntry["icon"]) {
  const runtime = runtimeGlyph(icon);
  if (runtime) return runtime;
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
  if (kind === "assistant" || kind === "thinking") {
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
  assistant: "text-primary",
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
              {kindGlyph(entry.kind, entry.icon)}
            </div>
            <div className="mb-1 flex flex-wrap items-center gap-2">
              <span className="font-mono text-[10.5px] uppercase tracking-[0.16em] text-foreground/75">
                {entry.heading ?? `${entry.kind}${entry.label ? ` · ${entry.label}` : ""}`}
              </span>
              {entry.count && entry.count > 1 ? (
                <span className="rounded-full border border-border/70 bg-background/60 px-2 py-0.5 font-mono text-[10px] text-muted-foreground">
                  {entry.count} calls
                </span>
              ) : null}
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
              <div className="space-y-2">
                <div className="text-[13.5px] leading-[1.55] text-foreground">{entry.body}</div>
                {entry.result ? (
                  <div className="rounded-[0.7rem] border border-border/70 bg-background-sunk px-2.5 py-2 text-[12px] leading-5 text-foreground/85">
                    <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                      Result
                    </span>
                    <p className="mt-1">{entry.result}</p>
                  </div>
                ) : null}
              </div>
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
        <Code className="font-mono text-[10px] uppercase tracking-[0.14em]">
          mode · {permissionMode}
        </Code>
        <Code className="font-mono text-[10px] uppercase tracking-[0.14em]">
          mcp · {serverCount}
        </Code>
        <Code className="font-mono text-[10px] uppercase tracking-[0.14em]">
          tools · {toolCount}
        </Code>
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

function backlogPriorityLabel(priority: number): string {
  if (priority >= 90) return "P0";
  if (priority >= 70) return "P1";
  if (priority >= 40) return "P2";
  return "P3";
}

export function TaskCard({
  task,
  density = "comfortable",
  onSelect,
  onRecover,
  recovering = false,
  className,
}: {
  task: TaskBoardItem;
  density?: "comfortable" | "compact";
  onSelect?: (task: TaskBoardItem) => void;
  onRecover?: (task: TaskBoardItem) => void;
  recovering?: boolean;
  className?: string;
}) {
  const tone = toStatusTone(task.status);
  const pulseActive = tone === "active";
  const progress = TASK_PROGRESS[task.status] ?? 0;
  return (
    <div
      role={onSelect ? "button" : undefined}
      tabIndex={onSelect ? 0 : undefined}
      onClick={onSelect ? () => onSelect(task) : undefined}
      onKeyDown={
        onSelect
          ? (event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                onSelect(task);
              }
            }
          : undefined
      }
      className={cn(
        "relative rounded-[1rem] border border-border/75 bg-background/70 transition hover:-translate-y-px hover:border-border hover:shadow-[var(--shadow-md)]",
        onSelect ? "cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/35" : "",
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
            <Code className="rounded-full px-2 py-0.5 text-[10px] uppercase tracking-[0.18em]">
              {backlogPriorityLabel(task.feature_priority)}
            </Code>
            <span className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
              {task.feature_item_type}
            </span>
          </div>
          <p className="truncate text-[14px] font-medium leading-[1.35] text-foreground">
            {task.title}
          </p>
          <p className="truncate text-[11px] text-muted-foreground">
            {task.feature_id ? (
              <span className="font-mono uppercase tracking-[0.14em]">
                {backlogItemDisplayId(task.feature_id)}
              </span>
            ) : null}
            {task.feature_id ? " · " : ""}
            {task.feature_title || "Backlog item"}
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
        <span>
          cost {runtimeCostDisplay(task.total_cost || task.cost_usd, task.runtime_sdk, task.provider, task.observability)}
        </span>
        <span>{task.num_turns} turns</span>
        {task.runtime_sdk ? <span>{task.runtime_sdk}</span> : null}
        {task.duration_ms > 0 ? <span>{formatDuration(task.duration_ms)}</span> : null}
        {task.pending_approval_count > 0 ? (
          <span className="text-status-review">
            {task.pending_approval_count} pending approval
          </span>
        ) : null}
        {task.approval_gate_id ? (
          <Button asChild variant="ghost" className="ml-auto h-7 rounded-full px-2" onClick={(event) => event.stopPropagation()}>
            <Link to={`/approvals/${task.approval_gate_id}`} className="inline-flex items-center gap-1 text-[11px]">
              Review
              <ArrowRight className="h-3 w-3" />
            </Link>
          </Button>
        ) : null}
        {/* Gate the Recover button on the API's can_recover signal so we
            never render a 409 trap. Fall back to status-based heuristic when
            the API hasn't included the field yet (older payload shape). */}
        {(
          task.can_recover ??
          ["blocked", "capability_limit", "failed"].includes(task.status)
        ) && onRecover ? (
          <Button
            type="button"
            variant="ghost"
            className="ml-auto h-7 rounded-full px-2"
            disabled={recovering}
            onClick={(event) => {
              event.stopPropagation();
              onRecover(task);
            }}
          >
            <RotateCcw className="h-3 w-3" />
            Recover
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
          <span className="font-mono tabular-nums">
            {runtimeCostDisplay(run.cost_usd, run.runtime_sdk, run.provider, run.observability)}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-muted-foreground">Turns</span>
          <span className="font-mono tabular-nums">{run.num_turns}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-muted-foreground">Tokens</span>
          <span className="font-mono tabular-nums">
            {telemetryTokenCount(run).toLocaleString()}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-muted-foreground">Duration</span>
          <span className="font-mono tabular-nums">{formatDuration(run.duration_ms)}</span>
        </div>
        {run.runtime_sdk ? (
          <div className="col-span-2 flex items-center justify-between">
            <span className="text-muted-foreground">Runtime</span>
            <span className="font-mono tabular-nums">{run.runtime_sdk}</span>
          </div>
        ) : null}
      </div>
    </SurfacePanel>
  );
}
