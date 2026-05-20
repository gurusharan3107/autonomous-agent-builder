import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/design-system";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  PageFrame,
  PageHeader,
  SectionLabel,
  StatPill,
  StatusDot,
  StatusPill,
  SurfacePanel,
} from "@/design-system";
import { fetchInbox } from "@/lib/api";
import type { InboxItem } from "@/lib/types";

type Urgency = "high" | "med" | "low" | "resolved";

function formatDuration(durationMs: number) {
  if (!durationMs) return "0s";
  const seconds = Math.round(durationMs / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return `${minutes}m ${remainder}s`;
}

function formatAge(createdAt: string | null): string {
  if (!createdAt) return "unknown";
  const createdMs = new Date(createdAt).getTime();
  if (Number.isNaN(createdMs)) return "unknown";
  const ageMs = Date.now() - createdMs;
  const mins = Math.floor(ageMs / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  return `${days}d`;
}

function urgencyOf(item: InboxItem): Urgency {
  if (item.status !== "pending") return "resolved";
  if (!item.created_at) return "low";
  const ageHours = (Date.now() - new Date(item.created_at).getTime()) / 3_600_000;
  if (ageHours < 1) return "high";
  if (ageHours < 24) return "med";
  return "low";
}

const URGENCY_META: Record<Urgency, { label: string; tone: "blocked" | "review" | "pending" | "muted" }> = {
  high: { label: "High", tone: "blocked" },
  med: { label: "Medium", tone: "review" },
  low: { label: "Low", tone: "pending" },
  resolved: { label: "Resolved", tone: "muted" },
};

const URGENCY_ORDER: Urgency[] = ["high", "med", "low", "resolved"];

export default function InboxPage() {
  const [items, setItems] = useState<InboxItem[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<"pending" | "all">("pending");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const data = await fetchInbox();
      setItems(data);
      setSelectedId((current) => current ?? data[0]?.id ?? null);
      setError(null);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Failed to load inbox");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const filteredItems = useMemo(
    () => items.filter((item) => statusFilter === "all" || item.status === "pending"),
    [items, statusFilter],
  );

  const groupedItems = useMemo(() => {
    const groups = new Map<Urgency, InboxItem[]>();
    URGENCY_ORDER.forEach((key) => groups.set(key, []));
    for (const item of filteredItems) {
      groups.get(urgencyOf(item))!.push(item);
    }
    return URGENCY_ORDER
      .map((key) => ({ key, items: groups.get(key) ?? [] }))
      .filter((group) => group.items.length > 0);
  }, [filteredItems]);

  const urgencyCounts = useMemo(() => {
    const counts: Record<Urgency, number> = { high: 0, med: 0, low: 0, resolved: 0 };
    for (const item of items) counts[urgencyOf(item)] += 1;
    return counts;
  }, [items]);

  const selectedItem = filteredItems.find((item) => item.id === selectedId) ?? filteredItems[0] ?? null;

  if (loading) {
    return <LoadingState label="Loading approval inbox..." />;
  }

  if (error) {
    return <ErrorState message={error} onRetry={load} />;
  }

  return (
    <PageFrame variant="overview" data-screen-label="Inbox">
      <PageHeader
        className="page-intro-compact"
        eyebrow="Approval inbox"
        title="Review pending decisions without leaving the operator lane."
        description="The inbox aggregates approval gates into one queue so you can see what is blocked, what just resolved, and where the latest run left off before you jump into the full approval record."
        meta={
          <>
            <StatPill label="High" value={String(urgencyCounts.high)} tone="blocked" />
            <StatPill label="Medium" value={String(urgencyCounts.med)} tone="review" />
            <StatPill label="Low" value={String(urgencyCounts.low)} tone="pending" />
            <StatPill label="Visible" value={String(filteredItems.length)} tone="active" />
          </>
        }
      />

      <div className="grid gap-4 lg:grid-cols-[380px_minmax(0,1fr)] lg:items-start">
        <SurfacePanel className="space-y-2 p-3">
          <div className="flex gap-1">
            {[
              ["pending", "Pending", filteredItems.filter((item) => item.status === "pending").length],
              ["all", "All", items.length],
            ].map(([value, label, count]) => {
              const active = statusFilter === value;
              return (
                <button
                  key={String(value)}
                  type="button"
                  onClick={() => setStatusFilter(value as "pending" | "all")}
                  className={[
                    "inline-flex h-7 flex-1 items-center justify-center gap-1 rounded-[var(--radius-sm)] border text-[11px] font-medium transition-colors",
                    active
                      ? "border-primary/40 bg-primary text-primary-foreground"
                      : "border-border/70 bg-background-sunk text-muted-foreground hover:text-foreground",
                  ].join(" ")}
                >
                  <span>{label}</span>
                  <span className="font-mono text-[9.5px] opacity-75">{count}</span>
                </button>
              );
            })}
            <Button variant="outline" onClick={load} className="h-7 rounded-[var(--radius-sm)] px-2 text-[11px]">
              Refresh
            </Button>
          </div>

          <SectionLabel
            trailing={
              <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
                {filteredItems.length} visible
              </span>
            }
          >
            Review queue
          </SectionLabel>

          {filteredItems.length === 0 ? (
            <EmptyState
              label="No approval gates in this view."
              detail="Dispatch work or wait for the next approval checkpoint to arrive."
            />
          ) : (
            <div className="space-y-2">
              {groupedItems.map((group) => {
                const meta = URGENCY_META[group.key];
                return (
                  <div key={group.key} className="space-y-1.5">
                    <div className="flex items-center gap-2 px-1">
                      <StatusDot
                        tone={meta.tone}
                        pulse={group.key === "high"}
                        className="h-1.5 w-1.5"
                      />
                      <span className="font-mono text-[10.5px] uppercase tracking-[0.18em] text-muted-foreground">
                        {meta.label}
                      </span>
                      <span className="font-mono text-[10px] text-muted-foreground">
                        · {group.items.length}
                      </span>
                    </div>
                    <div className="space-y-1">
                      {group.items.map((item) => {
                        const isActive = item.id === (selectedItem?.id ?? "");
                        return (
                          <button
                            key={item.id}
                            type="button"
                            onClick={() => setSelectedId(item.id)}
                            className={[
                              "w-full rounded-[var(--radius-md)] border px-3 py-3 text-left transition",
                              isActive
                                ? "border-primary/30 bg-primary-soft"
                                : "border-transparent hover:border-border/70 hover:bg-background/70",
                            ].join(" ")}
                          >
                            <div className="flex items-start justify-between gap-3">
                              <div className="min-w-0 space-y-1.5">
                                <div className="flex flex-wrap items-center gap-1.5">
                                  <StatusPill status={item.status} />
                                  <StatusPill status={item.task_status} />
                                </div>
                                <p className="truncate text-sm font-medium text-foreground">
                                  {item.task_title || item.id}
                                </p>
                                <p className="truncate text-[11px] text-muted-foreground">
                                  {item.project_name || "Project"} / {item.feature_title || "Feature"} /{" "}
                                  <span className="font-mono">{item.gate_type}</span>
                                </p>
                              </div>
                              <span className="shrink-0 font-mono text-[10.5px] uppercase tracking-[0.14em] text-muted-foreground">
                                {formatAge(item.created_at)}
                              </span>
                            </div>
                            <div className="mt-2 flex flex-wrap gap-2 font-mono text-[10.5px] text-muted-foreground">
                              <span>{item.latest_run_agent || "no run"}</span>
                              <span>${item.latest_run_cost_usd.toFixed(4)}</span>
                              <span>{item.latest_run_turns} turns</span>
                              <span>{formatDuration(item.latest_run_duration_ms)}</span>
                              {item.resolved_at ? (
                                <span className="text-status-done">
                                  resolved {formatAge(item.resolved_at)} ago
                                </span>
                              ) : null}
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </SurfacePanel>

        <SurfacePanel className="space-y-5 p-6">
          {selectedItem ? (
            <div className="space-y-5">
              <div className="space-y-2">
                <div className="flex flex-wrap items-center gap-2">
                  <StatusPill status={selectedItem.status === "pending" ? "review_pending" : selectedItem.status} />
                  <span className="font-mono text-[11px] text-muted-foreground">{selectedItem.id}</span>
                  <span className="font-mono text-[11px] text-muted-foreground">· {formatAge(selectedItem.created_at)} ago</span>
                </div>
                <h2 className="display-serif text-[1.8rem] leading-[1.12] text-foreground">{selectedItem.task_title}</h2>
                <p className="max-w-[68ch] text-sm leading-6 text-muted-foreground">
                  {selectedItem.project_name || "Project"} / {selectedItem.feature_title || "Feature"} / {selectedItem.gate_type}
                </p>
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <div className="rounded-[1rem] border border-border/70 bg-background/55 p-4">
                  <p className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">Gate</p>
                  <p className="mt-2 font-mono text-sm text-foreground">{selectedItem.gate_type}</p>
                </div>
                <div className="rounded-[1rem] border border-border/70 bg-background/55 p-4">
                  <p className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">Task status</p>
                  <div className="mt-2">
                    <StatusPill status={selectedItem.task_status} />
                  </div>
                </div>
                <div className="rounded-[1rem] border border-border/70 bg-background/55 p-4">
                  <p className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">Latest run</p>
                  <p className="mt-2 text-sm text-foreground">
                    <span className="font-mono">{selectedItem.latest_run_agent || "No run yet"}</span>
                    {selectedItem.latest_run_status ? (
                      <>
                        {" · "}
                        <span className="font-mono text-muted-foreground">{selectedItem.latest_run_status}</span>
                      </>
                    ) : null}
                  </p>
                </div>
                <div className="rounded-[1rem] border border-border/70 bg-background/55 p-4">
                  <p className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">Timing</p>
                  <p className="mt-2 text-sm text-foreground">
                    {selectedItem.created_at ? new Date(selectedItem.created_at).toLocaleString() : "Unknown"}
                  </p>
                  {selectedItem.resolved_at ? (
                    <p className="mt-1 text-[11px] text-status-done">
                      resolved {new Date(selectedItem.resolved_at).toLocaleString()}
                    </p>
                  ) : (
                    <p className="mt-1 text-[11px] text-muted-foreground">
                      pending · {formatAge(selectedItem.created_at)} old
                    </p>
                  )}
                </div>
              </div>

              <Button asChild className="h-10 rounded-full">
                <Link to={selectedItem.approval_url}>Open approval review</Link>
              </Button>
            </div>
          ) : (
            <EmptyState
              label="Nothing selected."
              detail="Choose an inbox item to review its latest run context and jump into the full approval page."
            />
          )}
        </SurfacePanel>
      </div>
    </PageFrame>
  );
}
