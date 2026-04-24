import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  PageFrame,
  PageHeader,
  SectionLabel,
  StatPill,
  SurfacePanel,
} from "@/components/workspace";
import { fetchInbox } from "@/lib/api";
import type { InboxItem } from "@/lib/types";

function formatDuration(durationMs: number) {
  if (!durationMs) return "0s";
  const seconds = Math.round(durationMs / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return `${minutes}m ${remainder}s`;
}

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
  const selectedItem = filteredItems.find((item) => item.id === selectedId) ?? filteredItems[0] ?? null;

  if (loading) {
    return <LoadingState label="Loading approval inbox..." />;
  }

  if (error) {
    return <ErrorState message={error} onRetry={load} />;
  }

  return (
    <PageFrame variant="overview">
      <PageHeader
        className="page-intro-compact"
        eyebrow="Approval inbox"
        title="Review pending decisions without leaving the operator lane."
        description="The inbox aggregates approval gates into one queue so you can see what is blocked, what just resolved, and where the latest run left off before you jump into the full approval record."
        meta={
          <>
            <StatPill label="Pending" value={String(items.filter((item) => item.status === "pending").length)} tone="review" />
            <StatPill label="Resolved" value={String(items.filter((item) => item.status !== "pending").length)} tone="muted" />
            <StatPill label="Visible" value={String(filteredItems.length)} tone="active" />
          </>
        }
      />

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.05fr)_minmax(320px,0.95fr)] lg:items-start">
        <SurfacePanel className="space-y-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <SectionLabel>Review queue</SectionLabel>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
              <Select value={statusFilter} onValueChange={(value: "pending" | "all") => setStatusFilter(value)}>
                <SelectTrigger className="h-10 rounded-full border-border/80 bg-background/70 sm:w-[180px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="pending">Pending only</SelectItem>
                  <SelectItem value="all">All approvals</SelectItem>
                </SelectContent>
              </Select>
              <Button variant="outline" onClick={load} className="h-10 rounded-full">
                Refresh queue
              </Button>
            </div>
          </div>

          {filteredItems.length === 0 ? (
            <EmptyState
              label="No approval gates in this view."
              detail="Dispatch work or wait for the next approval checkpoint to arrive."
            />
          ) : (
            <div className="space-y-3">
              {filteredItems.map((item) => {
                const isActive = item.id === (selectedItem?.id ?? "");
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => setSelectedId(item.id)}
                    className={[
                      "w-full rounded-[1rem] border px-4 py-4 text-left transition",
                      isActive
                        ? "border-foreground/15 bg-foreground/[0.045] shadow-[0_20px_50px_-40px_rgba(17,24,39,0.45)]"
                        : "border-border/70 bg-background/60 hover:border-border hover:bg-background/85",
                    ].join(" ")}
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="space-y-2">
                        <p className="text-sm font-medium text-foreground">{item.task_title || item.id}</p>
                        <p className="text-xs text-muted-foreground">
                          {item.project_name || "Project"} / {item.feature_title || "Feature"} / {item.gate_type}
                        </p>
                      </div>
                      <Badge variant={item.status === "pending" ? "outline" : "secondary"}>{item.status}</Badge>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-muted-foreground">
                      <span>Run {item.latest_run_agent || "none"}</span>
                      <span>${item.latest_run_cost_usd.toFixed(4)}</span>
                      <span>{item.latest_run_turns} turns</span>
                      <span>{formatDuration(item.latest_run_duration_ms)}</span>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </SurfacePanel>

        <SurfacePanel className="space-y-4">
          <SectionLabel>Selected approval</SectionLabel>
          {selectedItem ? (
            <div className="space-y-4">
              <div className="space-y-2">
                <p className="text-lg font-medium text-foreground">{selectedItem.task_title}</p>
                <p className="text-sm text-muted-foreground">
                  {selectedItem.project_name || "Project"} / {selectedItem.feature_title || "Feature"}
                </p>
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <div className="rounded-[1rem] border border-border/70 bg-background/55 p-4">
                  <p className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">Gate</p>
                  <p className="mt-2 text-sm text-foreground">{selectedItem.gate_type}</p>
                </div>
                <div className="rounded-[1rem] border border-border/70 bg-background/55 p-4">
                  <p className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">Task status</p>
                  <p className="mt-2 text-sm text-foreground">{selectedItem.task_status}</p>
                </div>
                <div className="rounded-[1rem] border border-border/70 bg-background/55 p-4">
                  <p className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">Latest run</p>
                  <p className="mt-2 text-sm text-foreground">
                    {selectedItem.latest_run_agent || "No run yet"} / {selectedItem.latest_run_status || "idle"}
                  </p>
                </div>
                <div className="rounded-[1rem] border border-border/70 bg-background/55 p-4">
                  <p className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">Started at</p>
                  <p className="mt-2 text-sm text-foreground">
                    {selectedItem.created_at ? new Date(selectedItem.created_at).toLocaleString() : "Unknown"}
                  </p>
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
