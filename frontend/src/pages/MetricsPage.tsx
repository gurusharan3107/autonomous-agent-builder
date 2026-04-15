import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useMetricsAnimations } from "@/hooks/use-metrics-animations";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Separator } from "@/components/ui/separator";
import { fetchMetrics } from "@/lib/api";
import type { MetricsData } from "@/lib/types";

const KPI_LABELS = ["Total Cost", "Total Tokens", "Agent Runs", "Gate Pass Rate"] as const;

function KPICard({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <Card data-kpi className="group hover:shadow-md transition-shadow">
      <CardHeader className="pb-1">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          {label}
        </p>
      </CardHeader>
      <CardContent>
        <p className="text-3xl font-bold tracking-tight font-mono tabular-nums">{value}</p>
        <p className="text-[11px] text-muted-foreground mt-1.5 font-mono">{detail}</p>
      </CardContent>
    </Card>
  );
}

function CostChart({ runs }: { runs: MetricsData["runs"] }) {
  if (runs.length === 0) return null;
  const maxCost = Math.max(...runs.map((r) => r.cost_usd), 0.001);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-sm font-semibold uppercase tracking-wider">
          Cost per Run
        </CardTitle>
        <span className="text-[10px] text-muted-foreground font-mono">
          max ${maxCost.toFixed(4)}
        </span>
      </CardHeader>
      <CardContent>
        <div className="relative">
          {/* Horizontal grid lines */}
          <div className="absolute inset-0 flex flex-col justify-between pointer-events-none">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="border-t border-dashed border-border/40" />
            ))}
          </div>
          <div className="flex items-end gap-[3px] h-32 relative">
            {runs.map((run) => {
              const pct = (run.cost_usd / maxCost) * 100;
              return (
                <div
                  key={run.id}
                  data-cost-bar
                  className="flex-1 rounded-t bg-primary/15 hover:bg-primary/35 transition-all duration-200 min-w-[4px] relative group cursor-default"
                  style={{ height: `${pct}%` }}
                  title={`${run.agent_name}: $${run.cost_usd.toFixed(4)}`}
                >
                  <div className="absolute -top-7 left-1/2 -translate-x-1/2 hidden group-hover:block text-[9px] bg-popover border rounded px-1.5 py-0.5 whitespace-nowrap shadow-md font-mono z-10">
                    <strong>{run.agent_name}</strong>: ${run.cost_usd.toFixed(4)}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function StatusDot({ status }: { status: string }) {
  const color =
    status === "completed"
      ? "bg-status-done"
      : status === "running"
      ? "bg-status-active"
      : "bg-status-blocked";

  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`h-1.5 w-1.5 rounded-full ${color}`} />
      <span className="text-[10px] font-mono uppercase tracking-wider">{status}</span>
    </span>
  );
}

export default function MetricsPage() {
  const animRef = useMetricsAnimations();
  const [data, setData] = useState<MetricsData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchMetrics()
      .then(setData)
      .catch((e) => setError(e.message));
  }, []);

  if (error) {
    return (
      <div className="py-20 text-center">
        <div className="inline-flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3">
          <div className="h-2 w-2 rounded-full bg-destructive" />
          <p className="text-destructive text-sm font-medium">{error}</p>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="py-20 text-center space-y-3">
        <div className="inline-flex gap-1">
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className="h-2 w-2 rounded-full bg-muted-foreground/30 animate-pulse"
              style={{ animationDelay: `${i * 150}ms` }}
            />
          ))}
        </div>
        <p className="text-sm text-muted-foreground">Loading metrics...</p>
      </div>
    );
  }

  const completedRuns = data.runs.filter((r) => r.status === "completed").length;

  const kpiValues = [
    { value: `$${data.total_cost.toFixed(4)}`, detail: `across ${data.total_runs} run${data.total_runs !== 1 ? "s" : ""}` },
    { value: data.total_tokens.toLocaleString(), detail: "input + output" },
    { value: String(data.total_runs), detail: `${completedRuns} completed` },
    { value: `${data.gate_pass_rate.toFixed(0)}%`, detail: data.total_runs === 0 ? "no gates yet" : "quality gates" },
  ];

  return (
    <div ref={animRef} className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Metrics</h1>
        <p className="text-xs text-muted-foreground mt-1 font-mono tabular-nums">
          {data.total_runs} run{data.total_runs !== 1 ? "s" : ""} &middot; ${data.total_cost.toFixed(4)} total spend
        </p>
      </div>
      <Separator />

      {/* KPI Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {KPI_LABELS.map((label, i) => (
          <KPICard
            key={label}
            label={label}
            value={kpiValues[i].value}
            detail={kpiValues[i].detail}
          />
        ))}
      </div>

      {/* Cost Chart */}
      <CostChart runs={data.runs} />

      {/* Runs Table */}
      {data.runs.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-semibold uppercase tracking-wider">
              Recent Runs
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="text-[10px] uppercase tracking-wider">Agent</TableHead>
                    <TableHead className="text-[10px] uppercase tracking-wider">Task</TableHead>
                    <TableHead className="text-[10px] uppercase tracking-wider">Cost</TableHead>
                    <TableHead className="text-[10px] uppercase tracking-wider">Tokens</TableHead>
                    <TableHead className="text-[10px] uppercase tracking-wider">Turns</TableHead>
                    <TableHead className="text-[10px] uppercase tracking-wider">Duration</TableHead>
                    <TableHead className="text-[10px] uppercase tracking-wider">Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.runs.map((run) => (
                    <TableRow key={run.id} className="group">
                      <TableCell>
                        <Badge variant="outline" className="text-[10px] font-mono">
                          {run.agent_name}
                        </Badge>
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
                        <StatusDot status={run.status} />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
