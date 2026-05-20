import { useEffect, useMemo, useState } from "react";
import {
  EmptyState,
  ErrorState,
  LoadingState,
  PageFrame,
  PageHeader,
  SectionLabel,
  StatPill,
  StatusPill,
  SurfacePanel,
} from "@/design-system";
import { ConfidenceBar, DiffBlock } from "@/components/agent-native";
import { runtimeCostDisplay } from "@/lib/runtime-cost";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { fetchCompare, fetchMetrics } from "@/lib/api";
import type { AgentRunItem, ComparePayload } from "@/lib/types";
import { useRuntimePreferences } from "@/hooks/use-runtime-preferences";

function formatDuration(durationMs: number) {
  const seconds = Math.round(durationMs / 1000);
  if (seconds < 60) return `${seconds}s`;
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

function ComparisonStat({
  label,
  left,
  right,
  winner,
}: {
  label: string;
  left: string;
  right: string;
  winner?: "left" | "right" | null;
}) {
  const cellClass = (win: boolean) =>
    [
      "rounded-full px-2.5 py-1 font-mono text-sm",
      win
        ? "bg-[color:var(--status-done-soft)] text-status-done font-semibold"
        : "text-foreground",
    ].join(" ");
  return (
    <div className="grid gap-2 border-b border-border/55 px-1 py-3 last:border-b-0 sm:grid-cols-[120px_minmax(0,1fr)_minmax(0,1fr)] sm:items-center">
      <p className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">{label}</p>
      <p className={cellClass(winner === "left")}>{left}</p>
      <p className={cellClass(winner === "right")}>{right}</p>
    </div>
  );
}

function SideRibbon({ side }: { side: "baseline" | "variant" }) {
  const isBaseline = side === "baseline";
  return (
    <span
      className={[
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.16em]",
        isBaseline
          ? "border-primary/30 bg-primary-soft text-primary-ink"
          : "border-status-review/30 bg-[color:var(--status-review-soft)] text-status-review",
      ].join(" ")}
    >
      {isBaseline ? "A · baseline" : "B · variant"}
    </span>
  );
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="font-mono text-[9.5px] uppercase tracking-[0.16em] text-muted-foreground">{label}</p>
      <p className="mt-1 font-mono text-[13px] tabular-nums text-foreground">{value}</p>
    </div>
  );
}

function RunSurface({ run, side }: { run: ComparePayload["left"]; side: "baseline" | "variant" }) {
  return (
    <SurfacePanel className="flex flex-col overflow-hidden p-0">
      <div className="flex items-center gap-3 border-b border-border/70 px-4 py-3">
        <SideRibbon side={side} />
        <span className="font-mono text-[11px] text-muted-foreground">{run.id.slice(0, 8)}</span>
        <StatusPill status={run.status} />
        <span className="ml-auto truncate font-mono text-[11px] text-muted-foreground">{run.agent_name}</span>
      </div>

      <div className="grid grid-cols-2 gap-3 border-b border-border/70 px-4 py-3 sm:grid-cols-4">
        <MiniStat
          label="Cost"
          value={runtimeCostDisplay(run.cost_usd, run.runtime_sdk, run.provider, run.observability)}
        />
        <MiniStat label="Duration" value={formatDuration(run.duration_ms)} />
        <MiniStat label="Turns" value={String(run.num_turns)} />
        <MiniStat label="Tokens" value={(run.tokens_input + run.tokens_output).toLocaleString()} />
      </div>

      <div className="space-y-3 px-4 py-4">
        <div>
          <SectionLabel>Run scope</SectionLabel>
          <p className="mt-2 text-sm font-medium text-foreground">{run.task_title || run.task_id}</p>
          <p className="mt-1 text-xs leading-5 text-muted-foreground">
            {run.project_name || "Project"} / {run.feature_title || "Feature"} / stop {run.stop_reason || "n/a"}
          </p>
        </div>
        <div className="grid gap-2 text-xs text-muted-foreground sm:grid-cols-2">
          <p>Gate results: <span className="text-foreground">{run.gate_results.length}</span></p>
          <p>Approvals: <span className="text-foreground">{run.approvals.length}</span></p>
        </div>
        <ConfidenceBar value={run.confidence ?? null} />
      </div>
    </SurfacePanel>
  );
}

function CompareTaskStrip({
  runs,
  leftRunId,
  rightRunId,
  compareDisplayMode,
  comparison,
  onLeftRunChange,
  onRightRunChange,
  onDisplayModeChange,
}: {
  runs: AgentRunItem[];
  leftRunId: string;
  rightRunId: string;
  compareDisplayMode: "split" | "stacked";
  comparison: ComparePayload | null;
  onLeftRunChange: (value: string) => void;
  onRightRunChange: (value: string) => void;
  onDisplayModeChange: (value: "split" | "stacked") => void;
}) {
  const taskLabel = comparison?.left.task_title || comparison?.left.task_id || "Select two runs";
  return (
    <SurfacePanel className="mb-4 px-4 py-3">
      <div className="grid gap-3 lg:grid-cols-[auto_minmax(0,1fr)_minmax(0,2fr)] lg:items-center">
        <SectionLabel>Task</SectionLabel>
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-foreground">{taskLabel}</p>
          <p className="mt-0.5 font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
            {comparison ? comparison.left.task_id : "waiting for comparison"}
          </p>
        </div>
        <div className="grid gap-2 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_150px]">
          <Select value={leftRunId} onValueChange={onLeftRunChange}>
            <SelectTrigger className="h-8 rounded-full border-border/80 bg-background/70 text-xs">
              <SelectValue placeholder="Select baseline run" />
            </SelectTrigger>
            <SelectContent>
              {runs.map((run) => (
                <SelectItem key={run.id} value={run.id}>
                  {run.agent_name} / {run.task_id.slice(0, 8)} / {run.status}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={rightRunId} onValueChange={onRightRunChange}>
            <SelectTrigger className="h-8 rounded-full border-border/80 bg-background/70 text-xs">
              <SelectValue placeholder="Select variant run" />
            </SelectTrigger>
            <SelectContent>
              {runs.map((run) => (
                <SelectItem key={run.id} value={run.id}>
                  {run.agent_name} / {run.task_id.slice(0, 8)} / {run.status}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={compareDisplayMode} onValueChange={onDisplayModeChange}>
            <SelectTrigger className="h-8 rounded-full border-border/80 bg-background/70 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="split">Split view</SelectItem>
              <SelectItem value="stacked">Stacked view</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>
    </SurfacePanel>
  );
}

function pickWinner<T>(left: T, right: T, mode: "lower" | "higher"): "left" | "right" | null {
  if (left === right) return null;
  if (mode === "lower") return left < right ? "left" : "right";
  return left > right ? "left" : "right";
}

function buildVerdict(c: ComparePayload): string | null {
  const lCost = c.left.cost_usd;
  const rCost = c.right.cost_usd;
  if (lCost === 0 && rCost === 0) return null;
  const cheaperSide: "left" | "right" | null = lCost === rCost ? null : lCost < rCost ? "left" : "right";
  const cheaper = cheaperSide === "left" ? c.left : cheaperSide === "right" ? c.right : null;
  const pricier = cheaperSide === "left" ? c.right : cheaperSide === "right" ? c.left : null;
  if (!cheaper || !pricier) return null;
  const savings = pricier.cost_usd > 0 ? ((pricier.cost_usd - cheaper.cost_usd) / pricier.cost_usd) * 100 : 0;
  const durationDelta = pricier.duration_ms - cheaper.duration_ms;
  const durationText =
    durationDelta > 2000
      ? ` and finished ${Math.round(durationDelta / 1000)}s faster`
      : durationDelta < -2000
        ? ` though it took ${Math.round(-durationDelta / 1000)}s longer`
        : "";
  const label = cheaperSide === "left" ? "Baseline" : "Variant";
  return `${label} (${cheaper.agent_name}) shipped for ${runtimeCostDisplay(cheaper.cost_usd, cheaper.runtime_sdk, cheaper.provider, cheaper.observability)} - ${savings.toFixed(0)}% cheaper${durationText}.`;
}

export default function ComparePage() {
  const { preferences, updatePreferences } = useRuntimePreferences();
  const [runs, setRuns] = useState<AgentRunItem[]>([]);
  const [leftRunId, setLeftRunId] = useState<string>("");
  const [rightRunId, setRightRunId] = useState<string>("");
  const [comparison, setComparison] = useState<ComparePayload | null>(null);
  const [loadingRuns, setLoadingRuns] = useState(true);
  const [loadingCompare, setLoadingCompare] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const loadRuns = async () => {
      setLoadingRuns(true);
      try {
        const metrics = await fetchMetrics();
        if (cancelled) return;
        const runList = metrics.runs.filter((run) => Boolean(run.id) && run.agent_name !== "agent-chat");
        setRuns(runList);
        setLeftRunId((current) => current || runList[0]?.id || "");
        setRightRunId((current) => current || runList[1]?.id || runList[0]?.id || "");
        setError(null);
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : "Failed to load runs");
        }
      } finally {
        if (!cancelled) setLoadingRuns(false);
      }
    };

    void loadRuns();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    if (!leftRunId || !rightRunId || leftRunId === rightRunId) {
      setComparison(null);
      return;
    }

    const loadComparison = async () => {
      setLoadingCompare(true);
      try {
        const payload = await fetchCompare(leftRunId, rightRunId);
        if (!cancelled) {
          setComparison(payload);
          setError(null);
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : "Failed to compare runs");
        }
      } finally {
        if (!cancelled) setLoadingCompare(false);
      }
    };

    void loadComparison();
    return () => {
      cancelled = true;
    };
  }, [leftRunId, rightRunId]);

  const leftRun = useMemo(() => runs.find((run) => run.id === leftRunId) ?? null, [runs, leftRunId]);
  const rightRun = useMemo(() => runs.find((run) => run.id === rightRunId) ?? null, [runs, rightRunId]);

  if (loadingRuns) {
    return <LoadingState label="Loading runs to compare..." />;
  }

  if (error && !comparison) {
    return <ErrorState message={error} />;
  }

  return (
    <PageFrame variant="overview" data-screen-label="Compare">
      <PageHeader
        className="page-intro-compact"
        eyebrow="Run compare"
        title="Compare two real runs before you keep one as the working baseline."
        description="This surface stays grounded in actual AgentRun records. It compares cost, duration, token usage, gate outcomes, and final status so the operator can inspect what changed between two attempts."
        meta={
          <>
            <StatPill label="Runs" value={String(runs.length)} tone="muted" />
            <StatPill label="Mode" value={preferences.compareDisplayMode} tone="active" />
            <StatPill label="Task match" value={comparison ? (comparison.same_task ? "same" : "mixed") : "n/a"} tone="review" />
          </>
        }
      />

      <CompareTaskStrip
        runs={runs}
        leftRunId={leftRunId}
        rightRunId={rightRunId}
        compareDisplayMode={preferences.compareDisplayMode}
        comparison={comparison}
        onLeftRunChange={setLeftRunId}
        onRightRunChange={setRightRunId}
        onDisplayModeChange={(value) => updatePreferences({ compareDisplayMode: value })}
      />

      {!leftRun || !rightRun ? (
        <EmptyState
          label="Not enough runs to compare yet."
          detail="Dispatch at least two runs before opening compare."
        />
      ) : loadingCompare ? (
        <LoadingState label="Comparing selected runs..." />
      ) : comparison ? (
        <div className="space-y-4">
          <div
            className={
              preferences.compareDisplayMode === "split"
                ? "grid gap-4 lg:grid-cols-2"
                : "space-y-4"
            }
          >
            <RunSurface run={comparison.left} side="baseline" />
            <RunSurface run={comparison.right} side="variant" />
          </div>

          {(() => {
            const verdict = buildVerdict(comparison);
            return verdict ? (
              <p className="display-serif rounded-[1.15rem] border border-border/65 bg-background/55 px-5 py-4 text-[15px] leading-[1.65] text-foreground/85">
                &ldquo;{verdict}&rdquo;
              </p>
            ) : null;
          })()}

          <SurfacePanel className="space-y-2">
            <SectionLabel>Delta table</SectionLabel>
            <ComparisonStat label="Task" left={comparison.left.task_title} right={comparison.right.task_title} />
            <ComparisonStat
              label="Status"
              left={comparison.left.status}
              right={comparison.right.status}
              winner={comparison.left.status === "success" || comparison.left.status === "completed" ? "left" : comparison.right.status === "success" || comparison.right.status === "completed" ? "right" : null}
            />
            <ComparisonStat
              label="Cost"
              left={runtimeCostDisplay(
                comparison.left.cost_usd,
                comparison.left.runtime_sdk,
                comparison.left.provider,
                comparison.left.observability,
              )}
              right={runtimeCostDisplay(
                comparison.right.cost_usd,
                comparison.right.runtime_sdk,
                comparison.right.provider,
                comparison.right.observability,
              )}
              winner={pickWinner(comparison.left.cost_usd, comparison.right.cost_usd, "lower")}
            />
            <ComparisonStat
              label="Duration"
              left={formatDuration(comparison.left.duration_ms)}
              right={formatDuration(comparison.right.duration_ms)}
              winner={pickWinner(comparison.left.duration_ms, comparison.right.duration_ms, "lower")}
            />
            <ComparisonStat
              label="Turns"
              left={String(comparison.left.num_turns)}
              right={String(comparison.right.num_turns)}
              winner={pickWinner(comparison.left.num_turns, comparison.right.num_turns, "lower")}
            />
            <ComparisonStat
              label="Tokens"
              left={(comparison.left.tokens_input + comparison.left.tokens_output).toLocaleString()}
              right={(comparison.right.tokens_input + comparison.right.tokens_output).toLocaleString()}
              winner={pickWinner(
                comparison.left.tokens_input + comparison.left.tokens_output,
                comparison.right.tokens_input + comparison.right.tokens_output,
                "lower",
              )}
            />
            <ComparisonStat label="Gate results" left={String(comparison.left.gate_results.length)} right={String(comparison.right.gate_results.length)} />
            <ComparisonStat label="Approvals" left={String(comparison.left.approvals.length)} right={String(comparison.right.approvals.length)} />
          </SurfacePanel>

          {(comparison.left.diff_summary || comparison.right.diff_summary) ? (
            <SurfacePanel className="space-y-3">
              <SectionLabel>Workspace diffs</SectionLabel>
              <div className="grid gap-3 lg:grid-cols-2">
                <div className="space-y-2">
                  <SideRibbon side="baseline" />
                  <DiffBlock diff={comparison.left.diff_summary ?? null} />
                </div>
                <div className="space-y-2">
                  <SideRibbon side="variant" />
                  <DiffBlock diff={comparison.right.diff_summary ?? null} />
                </div>
              </div>
            </SurfacePanel>
          ) : null}
        </div>
      ) : (
        <EmptyState
          label="Choose two different runs."
          detail="The compare view loads once both selectors point to different runs."
        />
      )}
    </PageFrame>
  );
}
