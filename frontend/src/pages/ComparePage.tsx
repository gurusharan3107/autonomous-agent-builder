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
} from "@/components/workspace";
import { ConfidenceBar, DiffBlock } from "@/components/agent-native";
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
    <div className="grid gap-2 rounded-[1rem] border border-border/70 bg-background/55 p-4 sm:grid-cols-[120px_minmax(0,1fr)_minmax(0,1fr)] sm:items-center">
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

function RunSurface({ run, side }: { run: ComparePayload["left"]; side: "baseline" | "variant" }) {
  return (
    <div className="space-y-3 rounded-[1.15rem] border border-border/70 bg-background/60 p-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-sm font-medium text-foreground">{run.agent_name}</p>
          <p className="text-xs text-muted-foreground">
            {run.project_name || "Project"} / {run.feature_title || "Feature"} / {run.task_title || run.task_id}
          </p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <SideRibbon side={side} />
          <StatusPill status={run.status} />
        </div>
      </div>
      <div className="grid gap-2 text-sm text-muted-foreground">
        <p>Turns: <span className="text-foreground">{run.num_turns}</span></p>
        <p>Cost: <span className="text-foreground">${run.cost_usd.toFixed(4)}</span></p>
        <p>Tokens: <span className="text-foreground">{(run.tokens_input + run.tokens_output).toLocaleString()}</span></p>
        <p>Duration: <span className="text-foreground">{formatDuration(run.duration_ms)}</span></p>
        <p>Stop reason: <span className="text-foreground">{run.stop_reason || "n/a"}</span></p>
      </div>
      <ConfidenceBar value={run.confidence ?? null} />
    </div>
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
  return `${label} (${cheaper.agent_name}) shipped for $${cheaper.cost_usd.toFixed(4)} — ${savings.toFixed(0)}% cheaper${durationText}.`;
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
    <PageFrame variant="overview">
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

      <SurfacePanel className="mb-4">
        <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] md:items-center">
          <Select value={leftRunId} onValueChange={setLeftRunId}>
            <SelectTrigger className="h-10 rounded-full border-border/80 bg-background/70">
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
          <Select value={rightRunId} onValueChange={setRightRunId}>
            <SelectTrigger className="h-10 rounded-full border-border/80 bg-background/70">
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
          <Select
            value={preferences.compareDisplayMode}
            onValueChange={(value: "split" | "stacked") => updatePreferences({ compareDisplayMode: value })}
          >
            <SelectTrigger className="h-10 rounded-full border-border/80 bg-background/70 md:w-[170px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="split">Split view</SelectItem>
              <SelectItem value="stacked">Stacked view</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </SurfacePanel>

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

          <SurfacePanel className="space-y-3">
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
              left={`$${comparison.left.cost_usd.toFixed(4)}`}
              right={`$${comparison.right.cost_usd.toFixed(4)}`}
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
