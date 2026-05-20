import type { HTMLAttributes, ReactNode } from "react";
import { AlertCircle, Bot, Cpu, MessageSquare } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import type { TaskStatus } from "@/lib/types";
import {
  ACTIVE_STATUSES,
  STATUS_LABEL,
  normalizeStatusForDisplay,
  toStatusTone,
  type StatusTone,
} from "@/lib/status";

const STATUS_FILL: Record<StatusTone, string> = {
  active: "bg-status-active",
  review: "bg-status-review",
  pending: "bg-status-pending",
  done: "bg-status-done",
  blocked: "bg-status-blocked",
  muted: "bg-muted-foreground/35",
};

const STATUS_TEXT: Record<StatusTone, string> = {
  active: "text-status-active",
  review: "text-status-review",
  pending: "text-status-pending",
  done: "text-status-done",
  blocked: "text-status-blocked",
  muted: "text-muted-foreground",
};

interface PageFrameProps extends HTMLAttributes<HTMLDivElement> {
  variant?: "explorer" | "overview" | "review";
  children: ReactNode;
  className?: string;
}

export function PageFrame({
  variant = "overview",
  children,
  className,
  ...props
}: PageFrameProps) {
  return (
    <div
      className={cn(
        "mx-auto w-full",
        variant === "explorer" && "max-w-[1488px]",
        variant === "overview" && "max-w-[1360px]",
        variant === "review" && "max-w-[1100px]",
        className,
      )}
      {...props}
    >
      {children}
    </div>
  );
}

interface PageHeaderProps {
  eyebrow: string;
  title: string;
  description: string;
  meta?: ReactNode;
  aside?: ReactNode;
  className?: string;
}

export function PageHeader({
  eyebrow,
  title,
  description,
  meta,
  aside,
  className,
}: PageHeaderProps) {
  return (
    <header className={cn("page-intro", className)} data-stagger>
      <div className={cn("space-y-3", aside && "lg:grid lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end lg:gap-4 lg:space-y-0")}>
        <div className="space-y-2.5">
          <Eyebrow>{eyebrow}</Eyebrow>
          <div className="max-w-[60ch] space-y-2.5">
            <h1 className="display-serif text-[2.2rem] leading-[1.08] text-foreground sm:text-[2.25rem]">
              {title}
            </h1>
            <p className="max-w-[60ch] text-[14px] leading-[1.7] text-foreground-3 sm:text-[15px]">
              {description}
            </p>
          </div>
        </div>
        {aside ? <div className="flex flex-wrap gap-2 lg:justify-end">{aside}</div> : null}
      </div>
      {meta ? <div className="page-meta">{meta}</div> : null}
    </header>
  );
}

export function Eyebrow({ children, className }: { children: ReactNode; className?: string }) {
  return <p className={cn("page-eyebrow", className)}>{children}</p>;
}

export function WorkspaceGrid({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={cn("workspace-grid", className)}>{children}</div>;
}

export function WorkspaceRail({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <aside className={cn("workspace-rail space-y-4", className)}>{children}</aside>;
}

export function WorkspaceLane({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <section className={cn("workspace-lane space-y-4", className)}>{children}</section>;
}

export function WorkspaceDetail({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <aside className={cn("workspace-detail space-y-4", className)}>{children}</aside>;
}

export function SurfacePanel({
  children,
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <section
      className={cn(
        "surface-elevated rounded-[var(--radius-md)] border border-[var(--line)] px-3.5 py-3.5 sm:px-4 sm:py-4",
        className,
      )}
      {...props}
    >
      {children}
    </section>
  );
}

export function BrandMark({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "brand-mark flex h-10 w-10 shrink-0 items-center justify-center rounded-[var(--radius-lg)]",
        className,
      )}
    >
      <Bot className="h-5 w-5" />
    </div>
  );
}

export function SectionLabel({
  children,
  trailing,
  className,
}: {
  children: ReactNode;
  trailing?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex items-center justify-between gap-3", className)}>
      <div className="flex min-w-0 items-center gap-3">
        <div className="h-2.5 w-2.5 rounded-full bg-foreground/75 shadow-[0_0_0_4px_color-mix(in_oklab,var(--foreground)_8%,transparent)]" />
        <span className="text-[10.5px] font-medium uppercase tracking-[0.22em] text-muted-foreground">
          {children}
        </span>
      </div>
      {trailing ? <div className="shrink-0">{trailing}</div> : null}
    </div>
  );
}

export function StatusDot({
  tone = "muted",
  pulse = false,
  className,
}: {
  tone?: StatusTone;
  pulse?: boolean;
  className?: string;
}) {
  return (
    <span className={cn("relative inline-flex h-2.5 w-2.5", className)}>
      {pulse ? (
        <span
          className={cn("absolute inset-0 rounded-full opacity-70", STATUS_FILL[tone])}
          style={{ animation: "pulse-ring 1.8s ease-out infinite" }}
        />
      ) : null}
      <span className={cn("relative inline-flex h-2.5 w-2.5 rounded-full", STATUS_FILL[tone])} />
    </span>
  );
}

export function StatPill({
  label,
  value,
  tone = "muted",
  compact = false,
  icon,
}: {
  label: string;
  value: string;
  tone?: StatusTone;
  compact?: boolean;
  icon?: "messages" | "assistant" | "model";
}) {
  const iconNode =
    icon === "messages" ? <MessageSquare className="h-3.5 w-3.5" /> :
    icon === "assistant" ? <Bot className="h-3.5 w-3.5" /> :
    icon === "model" ? <Cpu className="h-3.5 w-3.5" /> :
    null;

  const baseClass = compact
    ? "px-2.5 py-2"
    : "px-3.5 py-2.5";

  return (
    <div
      className={cn(
        "inline-flex items-center gap-2 rounded-full border border-border/75 bg-background/72 text-foreground",
        baseClass,
      )}
      title={`${label} ${value}`}
    >
      <span className={cn("inline-flex items-center gap-2", STATUS_TEXT[tone])}>
        {iconNode ?? <StatusDot tone={tone} />}
      </span>
      <span className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
        {label}
      </span>
      <span className="font-mono text-[11px] tabular-nums text-foreground">{value}</span>
    </div>
  );
}

export function LoadingState({ label }: { label: string }) {
  return (
    <div className="surface-empty">
      <div className="inline-flex gap-1.5">
        {[0, 1, 2].map((i) => (
          <div
            key={i}
            className="h-2 w-2 rounded-full bg-muted-foreground/32"
            style={{ animation: `fade-up 0.45s ease-out ${i * 120}ms infinite alternate` }}
          />
        ))}
      </div>
      <p className="mt-4 text-sm text-muted-foreground">{label}</p>
    </div>
  );
}

export function EmptyState({
  label,
  detail,
  className,
}: {
  label: string;
  detail: string;
  className?: string;
}) {
  return (
    <div className={cn("surface-empty text-left", className)}>
      <p className="font-[family:var(--font-heading)] text-[1.2rem] font-normal tracking-normal text-foreground">
        {label}
      </p>
      <p className="mt-2 max-w-[54ch] text-[14px] leading-[1.7] text-muted-foreground">
        {detail}
      </p>
    </div>
  );
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="surface-empty">
      <div className="inline-flex items-center gap-2 rounded-full border border-status-blocked/25 bg-status-blocked/8 px-4 py-2">
        <AlertCircle className="h-4 w-4 text-status-blocked" />
        <span className="text-sm font-medium text-status-blocked">{message}</span>
      </div>
      {onRetry ? (
        <Button variant="outline" size="sm" onClick={onRetry} className="mt-4 rounded-full">
          Retry
        </Button>
      ) : null}
    </div>
  );
}

const STATUS_SOFT_BG: Record<StatusTone, string> = {
  active: "bg-[color:var(--status-active-soft)]",
  review: "bg-[color:var(--status-review-soft)]",
  pending: "bg-[color:var(--status-pending-soft)]",
  done: "bg-[color:var(--status-done-soft)]",
  blocked: "bg-[color:var(--status-blocked-soft)]",
  muted: "bg-muted",
};

export function StatusPill({
  status,
  pulse,
  withDot = true,
  className,
}: {
  status: string;
  pulse?: boolean;
  withDot?: boolean;
  className?: string;
}) {
  const displayStatus = normalizeStatusForDisplay(status, pulse);
  const tone = toStatusTone(displayStatus);
  const label = STATUS_LABEL[displayStatus];
  const showPulse = pulse ?? ACTIVE_STATUSES.has(displayStatus);
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-medium tracking-normal",
        STATUS_SOFT_BG[tone],
        STATUS_TEXT[tone],
        "border-transparent",
        className,
      )}
    >
      {withDot ? <StatusDot tone={tone} pulse={showPulse} className="h-1.5 w-1.5" /> : null}
      <span>{label}</span>
    </span>
  );
}

export function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="inline-flex min-w-[20px] items-center justify-center rounded-[5px] border border-border/80 bg-muted px-1.5 font-mono text-[10px] text-foreground/80 shadow-[inset_0_-1px_0_oklch(0_0_0_/_0.06)]">
      {children}
    </kbd>
  );
}

const METER_FILL: Record<StatusTone, string> = {
  active: "bg-status-active",
  review: "bg-status-review",
  pending: "bg-status-pending",
  done: "bg-status-done",
  blocked: "bg-status-blocked",
  muted: "bg-muted-foreground/40",
};

export function Meter({
  value,
  tone = "active",
  label,
  showValue = true,
  className,
}: {
  value: number;
  tone?: StatusTone;
  label?: string;
  showValue?: boolean;
  className?: string;
}) {
  const pct = Math.max(0, Math.min(1, value));
  return (
    <div className={cn("space-y-1", className)}>
      {(label || showValue) && (
        <div className="flex items-center justify-between gap-2 text-[11px]">
          {label ? <span className="text-muted-foreground">{label}</span> : <span />}
          {showValue ? (
            <span className="font-mono tabular-nums text-foreground/80">{Math.round(pct * 100)}%</span>
          ) : null}
        </div>
      )}
      <div className="meter-track">
        <div className={cn("meter-fill", METER_FILL[tone])} style={{ width: `${pct * 100}%` }} />
      </div>
    </div>
  );
}

export interface TabsItem<T extends string = string> {
  value: T;
  label: ReactNode;
}

export function Tabs<T extends string>({
  value,
  onChange,
  items,
  className,
}: {
  value: T;
  onChange: (next: T) => void;
  items: Array<TabsItem<T>>;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "inline-flex items-center gap-0.5 rounded-full border border-border/70 bg-background-sunk p-1",
        className,
      )}
      role="tablist"
    >
      {items.map((item) => {
        const active = item.value === value;
        return (
          <button
            key={item.value}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(item.value)}
            className={cn(
              "rounded-full px-3 py-1 text-[12px] font-medium transition-colors",
              active
                ? "bg-[color:var(--card)] text-foreground shadow-[var(--shadow-sm)]"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {item.label}
          </button>
        );
      })}
    </div>
  );
}

const PHASES: Array<{ key: string; label: string }> = [
  { key: "planning", label: "Plan" },
  { key: "design", label: "Design" },
  { key: "implementation", label: "Implement" },
  { key: "verification", label: "Gates" },
  { key: "integration", label: "PR" },
  { key: "complete", label: "Done" },
];

const PHASE_INDEX_BY_PHASE: Record<string, number> = {
  requirements: 0,
  planning: 0,
  design: 1,
  implementation: 2,
  verification: 3,
  integration: 4,
  complete: 5,
};

const PHASE_INDEX_BY_STATUS: Record<string, number> = {
  pending: 0,
  planning: 0,
  design: 1,
  design_review: 1,
  implementation: 2,
  quality_gates: 3,
  pr_creation: 4,
  review_pending: 4,
  build_verify: 4,
  done: 5,
  completed: 5,
  blocked: -1,
  failed: -1,
  capability_limit: -1,
};

export function PhaseStepper({
  phase,
  status,
  className,
}: {
  phase?: string;
  status?: TaskStatus | string;
  className?: string;
}) {
  const current =
    phase != null
      ? (PHASE_INDEX_BY_PHASE[phase] ?? 0)
      : status != null
        ? (PHASE_INDEX_BY_STATUS[status] ?? 0)
        : 0;
  return (
    <div className={cn("flex items-center gap-0", className)} aria-label="Phase progress">
      {PHASES.map((phase, i) => {
        const state: "done" | "active" | "muted" =
          current < 0 ? "muted" : i < current ? "done" : i === current ? "active" : "muted";
        return (
          <div key={phase.key} className="flex items-center gap-0">
            <span className="flex items-center gap-1.5">
              <span
                className={cn(
                  "inline-block h-[7px] w-[7px] rounded-full",
                  state === "done" && "bg-status-done",
                  state === "active" && "bg-status-active shadow-[0_0_0_3px_var(--status-active-soft)]",
                  state === "muted" && "bg-muted-foreground/30",
                )}
              />
              <span
                className={cn(
                  "font-mono text-[10px] uppercase tracking-[0.16em]",
                  state === "muted" ? "text-muted-foreground/70" : "text-foreground/80",
                )}
              >
                {phase.label}
              </span>
            </span>
            {i < PHASES.length - 1 ? (
              <span
                className={cn(
                  "mx-2 h-px w-4",
                  state === "done" ? "bg-status-done" : "bg-border",
                )}
              />
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
