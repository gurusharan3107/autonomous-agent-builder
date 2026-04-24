import { useEffect, useMemo, useState } from "react";
import { Search } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Input } from "@/components/ui/input";
import {
  ErrorState,
  LoadingState,
  Meter,
  PageFrame,
  PageHeader,
  SectionLabel,
  StatPill,
  StatusDot,
  SurfacePanel,
} from "@/components/workspace";
import { Sparkline } from "@/components/agent-native";
import { useMetricsAnimations } from "@/hooks/use-metrics-animations";
import { fetchMetrics } from "@/lib/api";
import type { MetricsData } from "@/lib/types";

const RUN_STATUS_TONE: Record<string, "active" | "review" | "pending" | "done" | "blocked"> = {
  running: "active",
  success: "done",
  completed: "done",
  failed: "blocked",
  blocked: "blocked",
  pending: "pending",
};

function KPICard({
  label,
  value,
  detail,
  sparkline,
}: {
  label: string;
  value: string;
  detail: string;
  sparkline?: number[];
}) {
  return (
    <SurfacePanel data-kpi className="space-y-2 px-4 py-3 sm:px-4 sm:py-3">
      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
        {label}
      </p>
      <div>
        <p className="font-mono text-[1.55rem] tracking-tight text-foreground">{value}</p>
        <p className="mt-1 text-[10.5px] font-mono text-muted-foreground">{detail}</p>
      </div>
      {sparkline && sparkline.length > 1 ? (
        <Sparkline data={sparkline} height={24} className="opacity-75" />
      ) : null}
    </SurfacePanel>
  );
}

function CostChart({ runs }: { runs: MetricsData["runs"] }) {
  if (runs.length === 0) return null;
  const maxCost = Math.max(...runs.map((run) => run.cost_usd), 0.001);

  return (
    <SurfacePanel className="space-y-3">
      <SectionLabel
        trailing={
          <span className="text-[10px] font-mono uppercase tracking-[0.18em] text-muted-foreground">
            max ${maxCost.toFixed(4)}
          </span>
        }
      >
        Cost per run
      </SectionLabel>

      <div className="relative">
        <div className="pointer-events-none absolute inset-0 flex flex-col justify-between">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="border-t border-dashed border-border/40" />
          ))}
        </div>
        <div className="relative flex h-28 items-end gap-[4px]">
          {runs.map((run, idx) => {
            const pct = (run.cost_usd / maxCost) * 100;
            const isLast = idx === runs.length - 1;
            return (
              <div
                key={run.id}
                data-cost-bar
                className={[
                  "group relative flex-1 cursor-default rounded-t-[0.8rem] bg-foreground/12 transition-colors hover:bg-foreground/22",
                  isLast ? "breathe bg-primary/60 hover:bg-primary/70" : "",
                ].join(" ")}
                style={{ height: `${pct}%` }}
                title={`${run.agent_name}: $${run.cost_usd.toFixed(4)}`}
              >
                <div className="absolute -top-8 left-1/2 hidden -translate-x-1/2 rounded-full border border-border/70 bg-background/95 px-2 py-1 text-[10px] font-mono text-foreground shadow-sm group-hover:block">
                  ${run.cost_usd.toFixed(4)}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </SurfacePanel>
  );
}

function AgentBreakdown({ runs }: { runs: MetricsData["runs"] }) {
  const totals = useMemo(() => {
    const byAgent = new Map<string, { cost: number; runs: number }>();
    runs.forEach((run) => {
      const current = byAgent.get(run.agent_name) ?? { cost: 0, runs: 0 };
      byAgent.set(run.agent_name, {
        cost: current.cost + run.cost_usd,
        runs: current.runs + 1,
      });
    });
    return Array.from(byAgent.entries())
      .map(([agent, value]) => ({ agent, ...value }))
      .sort((a, b) => b.cost - a.cost)
      .slice(0, 4);
  }, [runs]);
  const maxCost = Math.max(...totals.map((item) => item.cost), 0.001);

  return (
    <SurfacePanel className="space-y-3">
      <SectionLabel>By agent</SectionLabel>
      <div className="space-y-3">
        {totals.map((item) => (
          <div key={item.agent} className="space-y-1.5">
            <div className="flex items-center justify-between gap-3">
              <span className="font-mono text-[12px] text-foreground">{item.agent}</span>
              <span className="font-mono text-[12px] tabular-nums text-foreground">
                ${item.cost.toFixed(4)}
              </span>
            </div>
            <Meter value={item.cost / maxCost} tone="active" showValue={false} />
            <p className="font-mono text-[10px] text-muted-foreground">{item.runs} runs</p>
          </div>
        ))}
      </div>
    </SurfacePanel>
  );
}

export default function MetricsPage() {
  const animRef = useMetricsAnimations();
  const [data, setData] = useState<MetricsData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [runFilter, setRunFilter] = useState("");

  const load = () => {
    fetchMetrics()
      .then((payload) => {
        setData(payload);
        setError(null);
      })
      .catch((e) => setError(e.message));
  };

  useEffect(() => {
    load();
    const interval = setInterval(load, 5000);
    return () => clearInterval(interval);
  }, []);

  if (error) {
    return <ErrorState message={error} onRetry={load} />;
  }

  if (!data) {
    return <LoadingState label="Loading metrics..." />;
  }

  const filteredRuns = data.runs.filter((run) => {
    const query = runFilter.trim().toLowerCase();
    if (!query) return true;
    return [run.agent_name, run.task_id, run.status].join(" ").toLowerCase().includes(query);
  });

  const costTrend = data.runs.map((r) => r.cost_usd);
  const tokenTrend = data.runs.map((r) => r.tokens_input + r.tokens_output);

  return (
    <PageFrame variant="overview">
      <PageHeader
        className="page-intro-compact"
        eyebrow="Metrics surface"
        title="Read operating signal on one evidence surface."
        description="Metrics stays chart-led and quiet: headline measures establish the frame, cost distribution reveals pattern, and the run table keeps the operational detail close at hand."
        meta={
          <>
            <StatPill label="Runs" value={String(data.total_runs)} tone="active" />
            <StatPill label="Pass rate" value={`${Math.round(data.gate_pass_rate)}%`} tone="done" />
            <StatPill label="Tokens" value={data.total_tokens.toLocaleString()} tone="muted" />
          </>
        }
      />

      <div ref={animRef} className="space-y-4">
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <KPICard
            label="Total cost"
            value={`$${data.total_cost.toFixed(4)}`}
            detail="aggregate run spend"
            sparkline={costTrend}
          />
          <KPICard
            label="Total tokens"
            value={data.total_tokens.toLocaleString()}
            detail="input + output"
            sparkline={tokenTrend}
          />
          <KPICard
            label="Agent runs"
            value={String(data.total_runs)}
            detail="all recorded executions"
          />
          <KPICard
            label="Gate pass rate"
            value={`${Math.round(data.gate_pass_rate)}%`}
            detail="quality gate success"
          />
        </div>

        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
          <CostChart runs={filteredRuns} />
          <AgentBreakdown runs={filteredRuns} />
        </div>

        <SurfacePanel className="space-y-3">
          <SectionLabel
            trailing={
              <div className="relative w-full min-w-[220px] max-w-[320px]">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground/80" />
                <Input
                  value={runFilter}
                  onChange={(event) => setRunFilter(event.target.value)}
                  placeholder="Filter by task, agent, status..."
                  className="h-9 pl-8"
                />
              </div>
            }
          >
            Recent runs
          </SectionLabel>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-[10px] uppercase tracking-[0.18em]">Agent</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-[0.18em]">Task</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-[0.18em]">Cost</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-[0.18em]">Tokens</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-[0.18em]">Turns</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-[0.18em]">Duration</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-[0.18em]">Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredRuns.map((run) => (
                  <TableRow key={run.id} className="group">
                    <TableCell className="font-mono text-[11px] text-foreground">
                      {run.agent_name}
                    </TableCell>
                    <TableCell className="font-mono text-[11px] text-muted-foreground">
                      {run.task_id.slice(0, 8)}
                    </TableCell>
                    <TableCell className="font-mono text-[11px] tabular-nums">
                      ${run.cost_usd.toFixed(4)}
                    </TableCell>
                    <TableCell className="font-mono text-[11px] tabular-nums">
                      {(run.tokens_input + run.tokens_output).toLocaleString()}
                    </TableCell>
                    <TableCell className="font-mono text-[11px] tabular-nums">
                      {run.num_turns}
                    </TableCell>
                    <TableCell className="font-mono text-[11px] tabular-nums">
                      {(run.duration_ms / 1000).toFixed(1)}s
                    </TableCell>
                    <TableCell>
                      <span className="inline-flex items-center gap-2 text-[10px] font-mono uppercase tracking-[0.18em] text-muted-foreground">
                        <StatusDot tone={RUN_STATUS_TONE[run.status] ?? "muted"} />
                        {run.status}
                      </span>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </SurfacePanel>
      </div>
    </PageFrame>
  );
}
