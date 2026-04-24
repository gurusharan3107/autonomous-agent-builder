import { useEffect, useMemo, useState } from "react";
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
}: {
  label: string;
  left: string;
  right: string;
}) {
  return (
    <div className="grid gap-2 rounded-[1rem] border border-border/70 bg-background/55 p-4 sm:grid-cols-[120px_minmax(0,1fr)_minmax(0,1fr)] sm:items-center">
      <p className="text-[11px] uppercase tracking-[0.16em] text-muted-foreground">{label}</p>
      <p className="font-mono text-sm text-foreground">{left}</p>
      <p className="font-mono text-sm text-foreground">{right}</p>
    </div>
  );
}

function RunSurface({ run }: { run: ComparePayload["left"] }) {
  return (
    <div className="space-y-3 rounded-[1.15rem] border border-border/70 bg-background/60 p-4">
      <div>
        <p className="text-sm font-medium text-foreground">{run.agent_name}</p>
        <p className="text-xs text-muted-foreground">
          {run.project_name || "Project"} / {run.feature_title || "Feature"} / {run.task_title || run.task_id}
        </p>
      </div>
      <div className="grid gap-2 text-sm text-muted-foreground">
        <p>Status: <span className="text-foreground">{run.status}</span></p>
        <p>Turns: <span className="text-foreground">{run.num_turns}</span></p>
        <p>Cost: <span className="text-foreground">${run.cost_usd.toFixed(4)}</span></p>
        <p>Tokens: <span className="text-foreground">{(run.tokens_input + run.tokens_output).toLocaleString()}</span></p>
        <p>Duration: <span className="text-foreground">{formatDuration(run.duration_ms)}</span></p>
        <p>Stop reason: <span className="text-foreground">{run.stop_reason || "n/a"}</span></p>
      </div>
    </div>
  );
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
            <RunSurface run={comparison.left} />
            <RunSurface run={comparison.right} />
          </div>

          <SurfacePanel className="space-y-3">
            <SectionLabel>Delta table</SectionLabel>
            <ComparisonStat label="Task" left={comparison.left.task_title} right={comparison.right.task_title} />
            <ComparisonStat label="Status" left={comparison.left.status} right={comparison.right.status} />
            <ComparisonStat label="Cost" left={`$${comparison.left.cost_usd.toFixed(4)}`} right={`$${comparison.right.cost_usd.toFixed(4)}`} />
            <ComparisonStat label="Duration" left={formatDuration(comparison.left.duration_ms)} right={formatDuration(comparison.right.duration_ms)} />
            <ComparisonStat label="Turns" left={String(comparison.left.num_turns)} right={String(comparison.right.num_turns)} />
            <ComparisonStat
              label="Tokens"
              left={(comparison.left.tokens_input + comparison.left.tokens_output).toLocaleString()}
              right={(comparison.right.tokens_input + comparison.right.tokens_output).toLocaleString()}
            />
            <ComparisonStat label="Gate results" left={String(comparison.left.gate_results.length)} right={String(comparison.right.gate_results.length)} />
            <ComparisonStat label="Approvals" left={String(comparison.left.approvals.length)} right={String(comparison.right.approvals.length)} />
          </SurfacePanel>
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
