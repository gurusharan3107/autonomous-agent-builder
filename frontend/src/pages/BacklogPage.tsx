import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { EditorialContent } from "@/components/EditorialContent";
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

interface FeatureItem {
  id: string;
  title: string;
  description?: string;
  status: string;
  priority?: number;
  acceptance_criteria?: string[];
  dependencies?: string[];
}

const STATUS_TONE: Record<string, "active" | "review" | "pending" | "done" | "blocked"> = {
  planning: "review",
  design: "review",
  implementation: "active",
  quality_gates: "review",
  done: "done",
  blocked: "blocked",
  pending: "pending",
};

const STATUS_ORDER = [
  "implementation",
  "planning",
  "design",
  "quality_gates",
  "pending",
  "done",
  "blocked",
];

export default function BacklogPage() {
  const [features, setFeatures] = useState<FeatureItem[]>([]);
  const [projectName, setProjectName] = useState("");
  const [stats, setStats] = useState({ total: 0, done: 0, pending: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [selectedFeatureId, setSelectedFeatureId] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const response = await fetch("/api/dashboard/features");
      const data = await response.json();
      setProjectName(data.project_name);
      setFeatures(data.features);
      setStats({ total: data.total, done: data.done, pending: data.pending });
      if (!selectedFeatureId && data.features.length > 0) {
        setSelectedFeatureId(data.features[0].id);
      }
      setError(null);
    } catch (error: unknown) {
      setError(error instanceof Error ? error.message : "Failed to load backlog ledger");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const filteredFeatures =
    statusFilter === "all"
      ? features
      : features.filter((feature) => feature.status === statusFilter);

  const selectedFeature =
    filteredFeatures.find((feature) => feature.id === selectedFeatureId) ??
    filteredFeatures[0] ??
    null;

  const groupedFeatures = STATUS_ORDER.map((status) => ({
    status,
    items: filteredFeatures.filter((feature) => feature.status === status),
  })).filter((group) => group.items.length > 0);

  if (error) {
    return <ErrorState message={error} onRetry={load} />;
  }

  if (loading) {
    return <LoadingState label="Loading backlog ledger..." />;
  }

  const detailPanel = selectedFeature ? (
    <SurfacePanel className="scroll-panel space-y-4 lg:max-h-[calc(100vh-12rem)] lg:overflow-y-auto">
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline" className="text-[10px] font-mono uppercase tracking-[0.18em]">
            {selectedFeature.id}
          </Badge>
          <Badge className="text-[10px] uppercase tracking-[0.18em]" variant="secondary">
            {selectedFeature.status}
          </Badge>
        </div>
        <div>
          <h2 className="text-[1.65rem] font-semibold tracking-tight text-foreground">
            {selectedFeature.title}
          </h2>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            Priority {selectedFeature.priority ?? "unassigned"} · structured program detail
          </p>
        </div>
      </div>

      <div className="space-y-3">
        <SectionLabel>Summary</SectionLabel>
        <EditorialContent content={selectedFeature.description || "No description available."} />
      </div>

      <div className="space-y-3">
        <SectionLabel>Acceptance criteria</SectionLabel>
        {selectedFeature.acceptance_criteria?.length ? (
          <ul className="space-y-2 text-[13px] leading-6 text-muted-foreground">
            {selectedFeature.acceptance_criteria.map((criterion, index) => (
              <li key={`${selectedFeature.id}-criterion-${index}`} className="flex gap-3">
                <span className="mt-2 h-1.5 w-1.5 rounded-full bg-status-active" />
                <span>{criterion}</span>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState
            label="No acceptance criteria recorded."
            detail="This feature does not yet have explicit acceptance criteria in the current dashboard response."
          />
        )}
      </div>

      <div className="space-y-3">
        <SectionLabel>Dependencies</SectionLabel>
        {selectedFeature.dependencies?.length ? (
          <div className="flex flex-wrap gap-1.5">
            {selectedFeature.dependencies.map((dependency) => (
              <span
                key={dependency}
                className="rounded-full border border-border/70 bg-background/65 px-2.5 py-1 text-[10px] font-mono uppercase tracking-[0.16em] text-muted-foreground"
              >
                {dependency}
              </span>
            ))}
          </div>
        ) : (
          <EmptyState
            label="No dependencies listed."
            detail="This item can currently be read as an independent backlog entry."
          />
        )}
      </div>
    </SurfacePanel>
  ) : (
    <EmptyState
      label="Select a backlog item to inspect."
      detail="Choose an item to open its current program detail and acceptance scope."
      className="h-full"
    />
  );

  return (
    <PageFrame variant="overview">
      <PageHeader
        className="page-intro-compact"
        eyebrow="Backlog surface"
        title={projectName || "Backlog ledger"}
        description="The backlog stays a program ledger rather than an explorer surface: controls remain compact, grouped work stays readable, and the selected feature detail stays close at hand."
        meta={
          <>
            <StatPill label="Total" value={String(stats.total)} tone="muted" />
            <StatPill label="Done" value={String(stats.done)} tone="done" />
            <StatPill label="Pending" value={String(stats.pending)} tone="pending" />
          </>
        }
      />

      <div className="mb-4 grid gap-4 lg:grid-cols-[minmax(0,1fr)]">
        <SurfacePanel className="flex flex-col gap-3 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-4 sm:py-3">
          <SectionLabel>Program controls</SectionLabel>

          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className="h-10 rounded-full border-border/80 bg-background/70 sm:w-[180px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All statuses</SelectItem>
                {Array.from(new Set(features.map((feature) => feature.status))).map((status) => (
                  <SelectItem key={status} value={status}>
                    {status}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

          <Button variant="outline" onClick={load} className="h-10 rounded-full">
            Refresh ledger
          </Button>
          </div>
        </SurfacePanel>

        <SurfacePanel className="hidden">
          <SectionLabel>Current view</SectionLabel>

          <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-1">
            <div className="rounded-[1.4rem] border border-border/70 bg-background/55 px-4 py-4 text-sm text-muted-foreground">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                Items visible
              </p>
              <p className="mt-3 font-mono text-2xl text-foreground">{filteredFeatures.length}</p>
              <p className="mt-1 text-xs text-muted-foreground">currently in the backlog view</p>
            </div>

            <div className="rounded-[1.4rem] border border-border/70 bg-background/55 px-4 py-4 text-sm text-muted-foreground">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                Status groups
              </p>
              <p className="mt-3 font-mono text-2xl text-foreground">{groupedFeatures.length}</p>
              <p className="mt-1 text-xs text-muted-foreground">grouped sections with active items</p>
            </div>

            <div className="rounded-[1.4rem] border border-border/70 bg-background/55 px-4 py-4 text-sm text-muted-foreground">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                Detail open
              </p>
              <p className="mt-3 font-mono text-2xl text-foreground">{selectedFeature ? "1" : "0"}</p>
              <p className="mt-1 text-xs text-muted-foreground">selected program item in focus</p>
            </div>
          </div>
        </SurfacePanel>
      </div>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.15fr)_minmax(320px,0.85fr)] lg:items-start">
        <div className="space-y-4">
          <SectionLabel
            trailing={
              <span className="text-[10px] font-mono uppercase tracking-[0.18em] text-muted-foreground">
                grouped by status
              </span>
            }
          >
            Program ledger
          </SectionLabel>

          {filteredFeatures.length === 0 ? (
            <EmptyState
              label="No backlog items match this filter."
              detail="Change the status scope to widen the view."
            />
          ) : (
            <div className="scroll-panel space-y-3 lg:max-h-[calc(100vh-22rem)] lg:overflow-y-auto lg:pr-1">
              {groupedFeatures.map((group) => (
                <SurfacePanel key={group.status} className="space-y-3 px-3 py-3 sm:px-3.5 sm:py-3.5">
                  <SectionLabel
                    trailing={
                      <span className="text-[10px] font-mono uppercase tracking-[0.18em] text-muted-foreground">
                        {group.items.length} item{group.items.length === 1 ? "" : "s"}
                      </span>
                    }
                  >
                    {group.status}
                  </SectionLabel>

                  <div className="space-y-2">
                    {group.items.map((feature) => (
                      <button
                        key={feature.id}
                        type="button"
                        data-selected={selectedFeature?.id === feature.id}
                        className="surface-list-item"
                        onClick={() => setSelectedFeatureId(feature.id)}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <div className="flex flex-wrap items-center gap-2">
                              <Badge variant="outline" className="text-[10px] font-mono uppercase tracking-[0.18em]">
                                {feature.id}
                              </Badge>
                              <span className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                                priority {feature.priority ?? "na"}
                              </span>
                            </div>
                            <h3 className="mt-2 text-[14px] font-semibold tracking-tight text-foreground">
                              {feature.title}
                            </h3>
                            {feature.description ? (
                              <p className="mt-1 max-w-[60ch] text-[12px] leading-5 text-muted-foreground">
                                {feature.description}
                              </p>
                            ) : null}
                          </div>
                          <span
                            className={`rounded-full px-2.5 py-1 text-[10px] uppercase tracking-[0.18em] ${
                              STATUS_TONE[feature.status] === "blocked"
                                ? "bg-status-blocked/10 text-status-blocked"
                                : STATUS_TONE[feature.status] === "done"
                                  ? "bg-status-done/10 text-status-done"
                                  : STATUS_TONE[feature.status] === "active"
                                    ? "bg-status-active/10 text-status-active"
                                    : STATUS_TONE[feature.status] === "review"
                                      ? "bg-status-review/10 text-status-review"
                                      : "bg-status-pending/10 text-status-pending"
                            }`}
                          >
                            {feature.status}
                          </span>
                        </div>
                      </button>
                    ))}
                  </div>
                </SurfacePanel>
              ))}
            </div>
          )}
        </div>

        <div className="min-w-0 lg:sticky lg:top-24">{detailPanel}</div>
      </div>
    </PageFrame>
  );
}
