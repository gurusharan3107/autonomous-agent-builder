import { useEffect, useState, type ReactNode } from "react";
import { Button } from "@/design-system";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { EditorialContent } from "@/components/EditorialContent";
import {
  Code,
  EmptyState,
  ErrorState,
  LoadingState,
  PageFrame,
  PageHeader,
  SectionLabel,
  StatusDot,
  StatusPill,
  StatPill,
  SurfacePanel,
} from "@/design-system";

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

const STATE_LABELS: Record<BoardState, string> = {
  backlog: "ideas",
  "sprint backlog": "ready",
  queued: "queued",
  "in-progress": "in progress",
  "needs review": "needs review",
  shipped: "shipped",
  blocked: "blocked",
  cancelled: "cancelled",
};

function BacklogCode({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "danger";
}) {
  return (
    <Code
      className={[
        "text-[10px] uppercase tracking-[0.18em]",
        tone === "danger" ? "border-status-failed/35 bg-status-failed-soft text-status-failed" : "",
      ].join(" ")}
    >
      {children}
    </Code>
  );
}

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

function itemTypeLabel(value: string) {
  // Show the item's real type. Relabeling `feature` as "improvement" (IMP-015)
  // misled operators into thinking a brand-new feature was an improvement to
  // existing work, and compounded IMP-016 mis-routing.
  if (value === "bug") return "fix";
  return value.replace(/_/g, " ");
}

function itemDisplayId(value: string) {
  return value.replace(/^feature-/i, "item-");
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
  const [cancelling, setCancelling] = useState(false);

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
      setError(error instanceof Error ? error.message : "Failed to load planned improvements");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const cancelItem = async (itemId: string) => {
    setCancelling(true);
    try {
      const response = await fetch(`/api/backlog/items/${itemId}/cancel`, {
        method: "POST",
      });
      if (!response.ok) {
        const detail = await response.json().catch(() => null);
        const message =
          detail && typeof detail.detail === "object" && detail.detail?.message
            ? detail.detail.message
            : "Failed to cancel item";
        throw new Error(message);
      }
      await load();
      setError(null);
    } catch (error: unknown) {
      setError(error instanceof Error ? error.message : "Failed to cancel item");
    } finally {
      setCancelling(false);
    }
  };

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
  const activeCount = features.filter((feature) =>
    ["implementation", "planning", "design", "quality_gates", "in_progress", "build_verify", "pr_creation"].includes(
      feature.status,
    ),
  ).length;

  if (error) {
    return <ErrorState message={error} onRetry={load} />;
  }

  if (loading) {
    return <LoadingState label="Loading planned improvements..." />;
  }

  const detailPanel = selectedFeature ? (
    <SurfacePanel className="scroll-panel space-y-4 lg:max-h-[calc(100vh-12rem)] lg:overflow-y-auto">
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <BacklogCode>{itemDisplayId(selectedFeature.id)}</BacklogCode>
          <StatusPill status={STATE_TONE[boardState(selectedFeature.status)]} />
          <BacklogCode>{itemTypeLabel(itemType(selectedFeature))}</BacklogCode>
          {selectedFeature.severity ? (
            <BacklogCode tone="danger">{selectedFeature.severity}</BacklogCode>
          ) : null}
          {!["shipped", "cancelled"].includes(boardState(selectedFeature.status)) ? (
            <Button
              variant="destructive"
              disabled={cancelling}
              onClick={() => void cancelItem(selectedFeature.id)}
              className="ml-auto h-7 rounded-full px-3 text-xs"
            >
              {cancelling ? "Cancelling…" : "Cancel item"}
            </Button>
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
              <BacklogCode key={tag}>{tag}</BacklogCode>
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
        <SectionLabel>Success checks</SectionLabel>
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
            label="No success checks recorded."
            detail="This improvement does not yet have explicit checks in the current dashboard response."
          />
        )}
      </div>

      <div className="space-y-3">
        <SectionLabel>Prerequisites</SectionLabel>
        {selectedFeature.dependencies?.length ? (
          <div className="flex flex-wrap gap-1.5">
            {selectedFeature.dependencies.map((dependency) => (
              <BacklogCode key={dependency}>{dependency}</BacklogCode>
            ))}
          </div>
        ) : (
          <EmptyState
            label="No prerequisites listed."
            detail="This item can currently be read as independent work."
          />
        )}
      </div>
    </SurfacePanel>
  ) : (
    <EmptyState
      label="Select an improvement to inspect."
      detail="Choose an item to open its current detail and success checks."
      className="h-full"
    />
  );

  return (
    <PageFrame variant="overview" data-screen-label="Backlog">
      <PageHeader
        className="page-intro-compact"
        eyebrow="Planned improvements"
        title={projectName || "Improvement list"}
        description="Review requested improvements, see what is ready or shipped, and inspect the selected item's detail without leaving the Builder workspace."
        meta={
          <>
            <StatPill label="Total" value={String(stats.total)} tone="muted" />
            <StatPill label="Active" value={String(activeCount)} tone="active" />
            <StatPill label="Queued" value={String(stats.pending)} tone="pending" />
            <StatPill label="Done" value={String(stats.done)} tone="done" />
          </>
        }
      />

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_420px] lg:items-start">
        <SurfacePanel className="overflow-hidden p-0">
          <div className="flex flex-col gap-3 border-b border-border/70 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
            <SectionLabel
              trailing={
                <span className="text-[10px] font-mono uppercase tracking-[0.18em] text-muted-foreground">
                  {filteredFeatures.length} item{filteredFeatures.length === 1 ? "" : "s"}
                </span>
              }
            >
              Work list
            </SectionLabel>

            <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
              <Select value={stateFilter} onValueChange={setStateFilter}>
                <SelectTrigger className="h-8 rounded-full border-border/80 bg-background/70 text-xs sm:w-[150px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All states</SelectItem>
                  {STATE_ORDER.map((state) => (
                    <SelectItem key={state} value={state}>
                      {STATE_LABELS[state]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select value={typeFilter} onValueChange={setTypeFilter}>
                <SelectTrigger className="h-8 rounded-full border-border/80 bg-background/70 text-xs sm:w-[140px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All types</SelectItem>
                  {typeOptions.map((type) => (
                    <SelectItem key={type} value={type}>
                      {itemTypeLabel(type)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              <Button variant="outline" onClick={load} className="h-8 rounded-full px-3 text-xs">
                Refresh
              </Button>
            </div>
          </div>

          {filteredFeatures.length === 0 ? (
            <EmptyState
              label="No planned improvements match this filter."
              detail="Change the state scope to widen the view."
              className="m-4"
            />
          ) : (
            <div className="scroll-panel divide-y divide-border/60 lg:max-h-[calc(100vh-15rem)] lg:overflow-y-auto">
              {groupedFeatures.map((group) => (
                <div key={group.state} className="py-2">
                  <div className="flex items-center gap-2 px-4 py-2">
                    <StatusDot tone={STATE_TONE[group.state]} pulse={STATE_TONE[group.state] === "active"} className="h-1.5 w-1.5" />
                    <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                      {STATE_LABELS[group.state]}
                    </span>
                    <span className="font-mono text-[10px] text-muted-foreground/70">· {group.items.length}</span>
                  </div>
                  <div>
                    {group.items.map((feature) => (
                      <button
                        key={feature.id}
                        type="button"
                        data-selected={selectedFeature?.id === feature.id}
                        className="grid w-full grid-cols-[3.8rem_minmax(0,1fr)_auto] items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-background/65 data-[selected=true]:bg-primary-soft"
                        onClick={() => setSelectedFeatureId(feature.id)}
                      >
                        <span className="font-mono text-[10px] text-muted-foreground tabular-nums">{itemDisplayId(feature.id)}</span>
                        <span className="min-w-0">
                          <span className="block truncate text-[13.5px] font-medium tracking-normal text-foreground">
                            {feature.title}
                          </span>
                          <span className="mt-0.5 block font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                            Priority {feature.priority ?? "na"} · {itemTypeLabel(itemType(feature))}
                          </span>
                        </span>
                        <StatusPill status={feature.status} className="shrink-0" />
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </SurfacePanel>

        <div className="min-w-0 lg:sticky lg:top-24">{detailPanel}</div>
      </div>
    </PageFrame>
  );
}
