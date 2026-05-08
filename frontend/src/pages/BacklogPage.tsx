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
  priority?: number | string;
  item_type?: string;
  type?: string;
  tags?: string[];
  severity?: string;
  source?: string;
  evidence?: string;
  acceptance_criteria?: string[];
  dependencies?: string[];
}

type BoardState = "backlog" | "sprint backlog" | "queued" | "in-progress" | "needs review" | "shipped" | "blocked" | "cancelled";

const STATE_TONE: Record<BoardState, "active" | "review" | "pending" | "done" | "blocked"> = {
  backlog: "pending",
  "sprint backlog": "pending",
  queued: "pending",
  "in-progress": "active",
  "needs review": "review",
  shipped: "done",
  blocked: "blocked",
  cancelled: "blocked",
};

const STATE_ORDER: BoardState[] = [
  "backlog",
  "sprint backlog",
  "queued",
  "in-progress",
  "needs review",
  "shipped",
  "blocked",
  "cancelled",
];

function boardState(status: string): BoardState {
  switch (status) {
    case "backlog":
    case "pending":
    case "planning":
      return "backlog";
    case "sprint_backlog":
      return "sprint backlog";
    case "queued":
      return "queued";
    case "implementation":
    case "in_progress":
    case "pr_creation":
    case "build_verify":
      return "in-progress";
    case "design":
    case "quality_gates":
    case "review":
    case "design_review":
    case "review_pending":
      return "needs review";
    case "done":
      return "shipped";
    case "cancelled":
      return "cancelled";
    case "blocked":
    case "capability_limit":
    case "failed":
      return "blocked";
    default:
      return "queued";
  }
}

export default function BacklogPage() {
  const [features, setFeatures] = useState<FeatureItem[]>([]);
  const [projectName, setProjectName] = useState("");
  const [stats, setStats] = useState({ total: 0, done: 0, pending: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [stateFilter, setStateFilter] = useState<string>("all");
  const [typeFilter, setTypeFilter] = useState<string>("all");
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

  const itemType = (feature: FeatureItem) => feature.item_type || feature.type || "feature";
  const itemTags = (feature: FeatureItem) => feature.tags || [];
  const typeOptions = Array.from(new Set(features.map(itemType))).sort();
  const filteredFeatures = features.filter((feature) => {
    if (stateFilter !== "all" && boardState(feature.status) !== stateFilter) return false;
    if (typeFilter !== "all" && itemType(feature) !== typeFilter) return false;
    return true;
  });

  const selectedFeature =
    filteredFeatures.find((feature) => feature.id === selectedFeatureId) ??
    filteredFeatures[0] ??
    null;

  const groupedFeatures = STATE_ORDER.map((state) => ({
    state,
    items: filteredFeatures.filter((feature) => boardState(feature.status) === state),
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
            {boardState(selectedFeature.status)}
          </Badge>
          <Badge className="text-[10px] uppercase tracking-[0.18em]" variant="outline">
            {itemType(selectedFeature)}
          </Badge>
          {selectedFeature.severity ? (
            <Badge className="text-[10px] uppercase tracking-[0.18em]" variant="destructive">
              {selectedFeature.severity}
            </Badge>
          ) : null}
        </div>
        <div>
          <h2 className="text-[1.65rem] font-semibold tracking-tight text-foreground">
            {selectedFeature.title}
          </h2>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            Priority {selectedFeature.priority ?? "unassigned"} · source {selectedFeature.source || "manual"}
          </p>
        </div>
      </div>

      {itemTags(selectedFeature).length ? (
        <div className="space-y-3">
          <SectionLabel>Tags</SectionLabel>
          <div className="flex flex-wrap gap-1.5">
            {itemTags(selectedFeature).map((tag) => (
              <Badge key={tag} variant="outline" className="text-[10px] uppercase tracking-[0.16em]">
                {tag}
              </Badge>
            ))}
          </div>
        </div>
      ) : null}

      <div className="space-y-3">
        <SectionLabel>Summary</SectionLabel>
        <EditorialContent content={selectedFeature.description || "No description available."} />
      </div>

      {selectedFeature.evidence ? (
        <div className="space-y-3">
          <SectionLabel>Evidence</SectionLabel>
          <EditorialContent content={selectedFeature.evidence} />
        </div>
      ) : null}

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
            <StatPill label="Shipped" value={String(stats.done)} tone="done" />
            <StatPill label="Backlog" value={String(stats.pending)} tone="pending" />
          </>
        }
      />

      <div className="mb-4 grid gap-4 lg:grid-cols-[minmax(0,1fr)]">
        <SurfacePanel className="flex flex-col gap-3 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-4 sm:py-3">
          <SectionLabel>Program controls</SectionLabel>

          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <Select value={stateFilter} onValueChange={setStateFilter}>
              <SelectTrigger className="h-10 rounded-full border-border/80 bg-background/70 sm:w-[180px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All states</SelectItem>
                {STATE_ORDER.map((state) => (
                  <SelectItem key={state} value={state}>
                    {state}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={typeFilter} onValueChange={setTypeFilter}>
              <SelectTrigger className="h-10 rounded-full border-border/80 bg-background/70 sm:w-[180px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All types</SelectItem>
                {typeOptions.map((type) => (
                  <SelectItem key={type} value={type}>
                    {type}
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
                grouped by state
              </span>
            }
          >
            Program ledger
          </SectionLabel>

          {filteredFeatures.length === 0 ? (
            <EmptyState
              label="No backlog items match this filter."
              detail="Change the state scope to widen the view."
            />
          ) : (
            <div className="scroll-panel space-y-3 lg:max-h-[calc(100vh-22rem)] lg:overflow-y-auto lg:pr-1">
              {groupedFeatures.map((group) => (
                <SurfacePanel key={group.state} className="space-y-3 px-3 py-3 sm:px-3.5 sm:py-3.5">
                  <SectionLabel
                    trailing={
                      <span className="text-[10px] font-mono uppercase tracking-[0.18em] text-muted-foreground">
                        {group.items.length} item{group.items.length === 1 ? "" : "s"}
                      </span>
                    }
                  >
                    {group.state}
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
                              <Badge variant="secondary" className="text-[10px] uppercase tracking-[0.18em]">
                                {itemType(feature)}
                              </Badge>
                              {feature.severity ? (
                                <Badge variant="destructive" className="text-[10px] uppercase tracking-[0.18em]">
                                  {feature.severity}
                                </Badge>
                              ) : null}
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
                            {itemTags(feature).length ? (
                              <div className="mt-2 flex flex-wrap gap-1.5">
                                {itemTags(feature).map((tag) => (
                                  <span
                                    key={`${feature.id}-${tag}`}
                                    className="rounded-full border border-border/70 px-2 py-0.5 text-[9px] uppercase tracking-[0.14em] text-muted-foreground"
                                  >
                                    {tag}
                                  </span>
                                ))}
                              </div>
                            ) : null}
                          </div>
                          <span
                            className={`rounded-full px-2.5 py-1 text-[10px] uppercase tracking-[0.18em] ${
                              STATE_TONE[boardState(feature.status)] === "blocked"
                                ? "bg-status-blocked/10 text-status-blocked"
                                : STATE_TONE[boardState(feature.status)] === "done"
                                  ? "bg-status-done/10 text-status-done"
                                  : STATE_TONE[boardState(feature.status)] === "active"
                                    ? "bg-status-active/10 text-status-active"
                                    : STATE_TONE[boardState(feature.status)] === "review"
                                      ? "bg-status-review/10 text-status-review"
                                      : "bg-status-pending/10 text-status-pending"
                            }`}
                          >
                            {boardState(feature.status)}
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
