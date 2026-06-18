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
import { Input } from "@/design-system";
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
} from "@/design-system";
import { Sparkline } from "@/components/agent-native";
import { estimatedCostDisplay } from "@/lib/runtime-cost";
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
  const maxCost = Math.max(...runs.map((run) => run.estimated_cost_usd), 0.000001);

  return (
    <SurfacePanel className="space-y-3">
      <SectionLabel
        trailing={
          <span className="text-[10px] font-mono uppercase tracking-[0.18em] text-muted-foreground">
            max {estimatedCostDisplay(maxCost)}
          </span>
        }
      >
        Estimated cost per run
      </SectionLabel>

      <div className="relative">
        <div className="pointer-events-none absolute inset-0 flex flex-col justify-between">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="border-t border-dashed border-border/40" />
          ))}
        </div>
        <div className="relative flex h-28 items-end gap-[4px]">
          {runs.map((run, idx) => {
            const pct = Math.max((run.estimated_cost_usd / maxCost) * 100, 4);
            const isLast = idx === runs.length - 1;
            const costLabel = estimatedCostDisplay(run.estimated_cost_usd);
            return (
              <div
                key={run.id}
                data-cost-bar
                className={[
                  "group relative flex-1 cursor-default rounded-t-[0.8rem] bg-foreground/12 transition-colors hover:bg-foreground/22",
                  isLast ? "breathe bg-primary/60 hover:bg-primary/70" : "",
                ].join(" ")}
                style={{ height: `${pct}%` }}
                title={`${run.agent_name}: ${costLabel} (${run.model || run.pricing_model || "unknown model"}, ${run.effort || "default"} effort)`}
              >
                <div className="absolute -top-8 left-1/2 hidden -translate-x-1/2 rounded-full border border-border/70 bg-background/95 px-2 py-1 text-[10px] font-mono text-foreground shadow-sm group-hover:block">
                  {costLabel}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </SurfacePanel>
  );
}

function EfficiencyPanel({ data }: { data: MetricsData }) {
  const summary = data.optimization_summary;
  if (!summary) return null;
  const benchmark = summary.benchmark;
  const topDriver = summary.top_cost_drivers[0];
  const flags = summary.avoidable_cost_flags.slice(0, 3);
  const isHighRework = summary.rework_share >= 0.25;
  const benchmarkLabel = isHighRework
    ? "inefficient (rework)"
    : benchmark.status === "within_target"
      ? "within target"
      : benchmark.status === "under_target"
        ? "under target"
        : "over target";

  return (
    <SurfacePanel className="space-y-4 px-4 py-4">
      <SectionLabel
        trailing={
          <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
            raw-token score
          </span>
        }
      >
        Efficiency
      </SectionLabel>
      {summary.active_runs_note ? (
        <p
          className="rounded-[0.85rem] border border-status-review/35 bg-[color:var(--status-review-soft)] px-3 py-2 text-[12px] leading-5 text-foreground"
          aria-live="polite"
        >
          {summary.active_runs_note}
        </p>
      ) : null}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
            Raw tokens
          </p>
          <p className="mt-1 font-mono text-lg text-foreground">
            {summary.raw_token_total.toLocaleString()}
          </p>
        </div>
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
            Non-cached + output
          </p>
          <p className="mt-1 font-mono text-lg text-foreground">
            {summary.noncached_plus_output_tokens.toLocaleString()}
          </p>
        </div>
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
            Ceremony
          </p>
          <p className="mt-1 font-mono text-lg text-foreground">
            {summary.phase_ceremony_tokens.toLocaleString()}
          </p>
        </div>
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
            Rework
          </p>
          <p className="mt-1 font-mono text-lg text-foreground">
            {Math.round(summary.rework_share * 100)}%
            {data.gate_pass_rate !== undefined
              ? ` / ${Math.round(data.gate_pass_rate)}% gates passed`
              : ""}
          </p>
        </div>
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
            Benchmark
          </p>
          <p className="mt-1 font-mono text-lg text-foreground">{benchmarkLabel}</p>
        </div>
      </div>
      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(220px,320px)]">
        <div className="space-y-2">
          <p className="font-mono text-[11px] text-muted-foreground">
            Target band {benchmark.target_min_raw_tokens.toLocaleString()}-
            {benchmark.target_max_raw_tokens.toLocaleString()} raw tokens.
            {topDriver
              ? ` Top driver: ${topDriver.agent_name} at ${topDriver.raw_tokens.toLocaleString()}.`
              : ""}
          </p>
          <p className="font-mono text-[11px] text-muted-foreground">
            Next: {summary.recommended_next_change || "maintain_current_flow"}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {flags.length > 0 ? (
            flags.map((flag) => (
              <span
                key={flag.flag}
                className="rounded-full border border-border bg-muted/40 px-2.5 py-1 font-mono text-[10px] text-muted-foreground"
              >
                {flag.flag} x{flag.count}
              </span>
            ))
          ) : (
            <span className="rounded-full border border-border bg-muted/40 px-2.5 py-1 font-mono text-[10px] text-muted-foreground">
              no avoidable flags
            </span>
          )}
        </div>
      </div>
    </SurfacePanel>
  );
}

function AgentBreakdown({ runs }: { runs: MetricsData["runs"] }) {
  const totals = useMemo(() => {
    const byAgent = new Map<string, { cost: number; credits: number; runs: number }>();
    runs.forEach((run) => {
      const current = byAgent.get(run.agent_name) ?? { cost: 0, credits: 0, runs: 0 };
      byAgent.set(run.agent_name, {
        cost: current.cost + run.estimated_cost_usd,
        credits: current.credits + Number(run.estimated_codex_credits ?? 0),
        runs: current.runs + 1,
      });
    });
    return Array.from(byAgent.entries())
      .map(([agent, value]) => ({ agent, ...value }))
      .sort((a, b) => b.cost - a.cost)
      .slice(0, 4);
  }, [runs]);
  const maxCost = Math.max(...totals.map((item) => item.cost), 0.000001);

  return (
    <SurfacePanel className="space-y-3">
      <SectionLabel>By agent</SectionLabel>
      <div className="space-y-3">
        {totals.map((item) => (
          <div key={item.agent} className="space-y-1.5">
            <div className="flex items-center justify-between gap-3">
              <span className="font-mono text-[12px] text-foreground">{item.agent}</span>
              <span className="font-mono text-[12px] tabular-nums text-foreground">
                {estimatedCostDisplay(item.cost)}
              </span>
            </div>
            <Meter value={item.cost / maxCost} tone="active" showValue={false} />
            <p className="font-mono text-[10px] text-muted-foreground">
              {item.runs} runs
              {item.credits > 0 ? ` / ${item.credits.toFixed(3)} credits` : ""}
            </p>
          </div>
        ))}
      </div>
    </SurfacePanel>
  );
}

function RuntimeHistory({ runs }: { runs: MetricsData["runs"] }) {
  const rows = useMemo(() => {
    const byRuntime = new Map<string, { runtime: string; runs: number; tokens: number; cost: number; credits: number }>();
    runs.forEach((run) => {
      const runtime = run.runtime_sdk || "unknown";
      const current = byRuntime.get(runtime) ?? { runtime, runs: 0, tokens: 0, cost: 0, credits: 0 };
      byRuntime.set(runtime, {
        runtime,
        runs: current.runs + 1,
        tokens: current.tokens + run.tokens_input + run.tokens_output,
        cost: current.cost + run.estimated_cost_usd,
        credits: current.credits + Number(run.estimated_codex_credits ?? 0),
      });
    });
    return Array.from(byRuntime.values()).sort((a, b) => b.runs - a.runs);
  }, [runs]);

  if (rows.length === 0) return null;

  return (
    <SurfacePanel className="space-y-3">
      <SectionLabel>Runtime history</SectionLabel>
      <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
        {rows.map((row) => (
          <div key={row.runtime} className="rounded-[0.75rem] border border-border/65 px-3 py-3">
            <div className="flex items-center justify-between gap-3">
              <span className="font-mono text-[12px] text-foreground">{row.runtime}</span>
              <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
                {row.runs} runs
              </span>
            </div>
            <p className="mt-2 font-mono text-[11px] text-muted-foreground">
              {row.tokens.toLocaleString()} tokens / {estimatedCostDisplay(row.cost)}
              {row.credits > 0 ? ` / ${row.credits.toFixed(3)} credits` : ""}
            </p>
          </div>
        ))}
      </div>
    </SurfacePanel>
  );
}

function percent(value: number | undefined | null) {
  const ratio = Number(value ?? 0);
  if (!Number.isFinite(ratio)) return "0%";
  return `${Math.round(ratio * 100)}%`;
}

function VoiceLedgerPanel({ ledger }: { ledger: MetricsData["voice_ledger"] }) {
  const totals = ledger?.totals ?? {};
  const responses = Number(totals.responses ?? 0);
  const totalTokens = Number(totals.total_tokens ?? 0);
  const delegatedMessages = Number(totals.delegated_messages ?? 0);
  const preparedActions = Number(totals.prepared_actions ?? 0);
  const toolCalls = Number(totals.tool_calls ?? 0);
  const waitEvents = Number(totals.wait_events ?? 0);
  const hasEvidence =
    responses > 0 || delegatedMessages > 0 || preparedActions > 0 || toolCalls > 0 || waitEvents > 0;

  return (
    <SurfacePanel className="space-y-4">
      <SectionLabel>Voice cost ledger</SectionLabel>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-[0.75rem] border border-border/65 px-3 py-3">
          <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
            Realtime responses
          </p>
          <p className="mt-1 font-mono text-[1.35rem] text-foreground">{responses}</p>
          <p className="font-mono text-[10px] text-muted-foreground">
            {totalTokens.toLocaleString()} tokens captured
          </p>
        </div>
        <div className="rounded-[0.75rem] border border-border/65 px-3 py-3">
          <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
            Delegation ratio
          </p>
          <p className="mt-1 font-mono text-[1.35rem] text-foreground">
            {percent(totals.delegation_ratio)}
          </p>
          <p className="font-mono text-[10px] text-muted-foreground">
            {delegatedMessages} voice messages delegated
          </p>
        </div>
        <div className="rounded-[0.75rem] border border-border/65 px-3 py-3">
          <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
            Prepared actions
          </p>
          <p className="mt-1 font-mono text-[1.35rem] text-foreground">{preparedActions}</p>
          <p className="font-mono text-[10px] text-muted-foreground">
            {Number(totals.confirmed_actions ?? 0)} confirmed by voice
          </p>
        </div>
        <div className="rounded-[0.75rem] border border-border/65 px-3 py-3">
          <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
            Tool calls
          </p>
          <p className="mt-1 font-mono text-[1.35rem] text-foreground">{toolCalls}</p>
          <p className="font-mono text-[10px] text-muted-foreground">
            {Number(totals.tool_outputs ?? 0)} sideband outputs
          </p>
        </div>
        <div className="rounded-[0.75rem] border border-border/65 px-3 py-3">
          <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
            Wait events
          </p>
          <p className="mt-1 font-mono text-[1.35rem] text-foreground">{waitEvents}</p>
          <p className="font-mono text-[10px] text-muted-foreground">
            silence or background audio
          </p>
        </div>
      </div>
      <div className="rounded-[0.75rem] border border-dashed border-border/65 px-3 py-3 font-mono text-[10px] text-muted-foreground">
        {hasEvidence
          ? `${totals.cost_source ?? "usage_without_realtime_rate_card"}; Realtime rate card not estimated locally.`
          : "No Realtime voice usage has been recorded in this Builder DB yet."}
      </div>
    </SurfacePanel>
  );
}

function ContextBudgetPanel({ summary }: { summary: MetricsData["context_budget"] }) {
  const total = Number(summary?.total_estimated_tokens ?? 0);
  const latest = summary?.latest ?? {};
  const topComponents = summary?.top_components ?? [];
  return (
    <SurfacePanel className="space-y-4">
      <SectionLabel>Context budget</SectionLabel>
      <div className="grid gap-3 md:grid-cols-3">
        <div className="rounded-[0.75rem] border border-border/65 px-3 py-3">
          <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
            Handoff events
          </p>
          <p className="mt-1 font-mono text-[1.35rem] text-foreground">{Number(summary?.event_count ?? 0)}</p>
          <p className="font-mono text-[10px] text-muted-foreground">
            {total.toLocaleString()} estimated tokens
          </p>
        </div>
        <div className="rounded-[0.75rem] border border-border/65 px-3 py-3">
          <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
            Latest lane
          </p>
          <p className="mt-1 font-mono text-[1.35rem] text-foreground">{latest.lane ?? "none"}</p>
          <p className="font-mono text-[10px] text-muted-foreground">{latest.stage ?? "no event"}</p>
        </div>
        <div className="rounded-[0.75rem] border border-border/65 px-3 py-3">
          <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-muted-foreground">
            Signal value
          </p>
          <p className="mt-1 font-mono text-[1.35rem] text-foreground">{latest.signal_category ?? "unknown"}</p>
          <p className="font-mono text-[10px] text-muted-foreground">local component ledger</p>
        </div>
      </div>
      <div className="rounded-[0.75rem] border border-dashed border-border/65 px-3 py-3 font-mono text-[10px] text-muted-foreground">
        {topComponents.length
          ? topComponents.slice(0, 5).map((item) => `${item.name}:${item.estimated_tokens}`).join(" · ")
          : "No context component estimates have been recorded yet."}
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
    return [run.agent_name, run.task_id, run.status, run.model, run.effort]
      .join(" ")
      .toLowerCase()
      .includes(query);
  });

  const costTrend = data.runs.map((r) => r.estimated_cost_usd);
  const tokenTrend = data.runs.map((r) => r.tokens_input + r.tokens_output);

  return (
    <PageFrame variant="overview" data-screen-label="Metrics">
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
            label="Estimated cost"
            value={estimatedCostDisplay(data.total_estimated_cost_usd)}
            detail={
              data.total_estimated_codex_credits
                ? `${data.total_estimated_codex_credits.toFixed(3)} Codex credits`
                : "token rate estimate"
            }
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

        <RuntimeHistory runs={filteredRuns} />

        <VoiceLedgerPanel ledger={data.voice_ledger} />

        <ContextBudgetPanel summary={data.context_budget} />

        <EfficiencyPanel data={data} />

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
                  <TableHead className="text-[10px] uppercase tracking-[0.18em]">Runtime</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-[0.18em]">Model</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-[0.18em]">Effort</TableHead>
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
                      {run.runtime_sdk || "-"}
                    </TableCell>
                    <TableCell className="font-mono text-[11px] tabular-nums">
                      {run.model || run.pricing_model || "-"}
                    </TableCell>
                    <TableCell className="font-mono text-[11px] tabular-nums">
                      {run.effort || "default"}
                    </TableCell>
                    <TableCell className="font-mono text-[11px] tabular-nums">
                      <div>{estimatedCostDisplay(run.estimated_cost_usd)}</div>
                      {run.estimated_codex_credits ? (
                        <div className="text-[9px] text-muted-foreground">
                          {run.estimated_codex_credits.toFixed(3)} credits
                        </div>
                      ) : null}
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
