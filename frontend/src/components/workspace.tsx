import type { HTMLAttributes, ReactNode } from "react";
import { AlertCircle, Bot, Cpu, MessageSquare } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

export type StatusTone =
  | "active"
  | "review"
  | "pending"
  | "done"
  | "blocked"
  | "muted";

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

interface PageFrameProps {
  variant?: "explorer" | "overview" | "review";
  children: ReactNode;
  className?: string;
}

export function PageFrame({
  variant = "overview",
  children,
  className,
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
  className?: string;
}

export function PageHeader({
  eyebrow,
  title,
  description,
  meta,
  className,
}: PageHeaderProps) {
  return (
    <header className={cn("page-intro", className)}>
      <div className="space-y-3">
        <p className="page-eyebrow">{eyebrow}</p>
        <div className="max-w-[74ch] space-y-3">
          <h1 className="font-[family:var(--font-heading)] text-[2.45rem] font-normal leading-[0.98] tracking-[-0.045em] text-foreground sm:text-[2.9rem]">
            {title}
          </h1>
          <p className="max-w-[68ch] text-[14px] leading-[1.7] text-muted-foreground sm:text-[15px]">
            {description}
          </p>
        </div>
      </div>
      {meta ? <div className="page-meta">{meta}</div> : null}
    </header>
  );
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
        "surface-elevated rounded-[1.5rem] border border-border/75 px-4 py-4 sm:px-5 sm:py-5",
        className,
      )}
      {...props}
    >
      {children}
    </section>
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
        <div className="h-2.5 w-2.5 rounded-full bg-foreground/75 shadow-[0_0_0_4px_rgba(30,26,21,0.06)] dark:shadow-[0_0_0_4px_rgba(243,242,237,0.08)]" />
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
      <span className="font-mono text-[11px] text-foreground">{value}</span>
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
      <p className="font-[family:var(--font-heading)] text-[1.2rem] font-normal tracking-[-0.02em] text-foreground">
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
