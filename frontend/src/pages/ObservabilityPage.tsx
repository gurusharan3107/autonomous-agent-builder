import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { Activity, AlertTriangle, Cpu, Gauge, RefreshCw } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  ErrorState,
  LoadingState,
  PageFrame,
  PageHeader,
  SectionLabel,
  StatusDot,
  SurfacePanel,
  Tabs,
} from "@/components/workspace";
import { fetchObservability } from "@/lib/api";
import { estimatedCostDisplay } from "@/lib/runtime-cost";
import type {
  DeterministicScriptCandidate,
  ObservabilityData,
  PhaseRuntimeDecision,
  RuntimeCapability,
  RuntimeAggregateRow,
  TelemetryHealthArea,
} from "@/lib/types";

const SEVERITY_TONE: Record<string, "active" | "review" | "pending" | "done" | "blocked"> = {
  high: "blocked",
  medium: "review",
  low: "pending",
  info: "done",
};

type RecommendationTab =
  | "all"
  | "rules"
  | "rejected";

type RuntimeDetailTab =
  | "optimization"
  | "phase"
  | "capability";

type UnifiedRecommendation = {
  id: string;
  severity: string;
  title: string;
  detail: string;
  code?: string;
  trigger?: string;
  lifecycleStatus?: string;
  decisionReason?: string;
  evidenceDetail?: string;
};

function compactNumber(value: number | undefined | null) {
  return Intl.NumberFormat("en", {
    notation: Number(value ?? 0) >= 10000 ? "compact" : "standard",
  }).format(Number(value ?? 0));
}

function cacheReuseDisplay(value: number | undefined | null) {
  const ratio = Number(value ?? 0);
  if (!Number.isFinite(ratio) || ratio <= 0) return "0x";
  return `${ratio.toFixed(ratio >= 10 ? 1 : 2)}x`;
}

function duration(ms: number | undefined | null) {
  const seconds = Math.round(Number(ms ?? 0) / 1000);
  if (seconds <= 0) return "0s";
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remaining = seconds % 60;
  return remaining ? `${minutes}m ${remaining}s` : `${minutes}m`;
}

function providerLabel(value: string | undefined | null) {
  return value === "codex_subscription" ? "Codex auth" : value || "default";
}

function collectorLabel(value: unknown) {
  switch (String(value ?? "unknown")) {
    case "reachable":
      return "reachable";
    case "configured_unreachable":
      return "unreachable";
    case "configured_not_checked":
      return "not checked";
    case "invalid_endpoint":
      return "invalid";
    case "missing":
      return "missing";
    default:
      return "unknown";
  }
}

function healthTone(status: string | undefined): "active" | "review" | "pending" | "done" | "blocked" {
  if (status === "ok") return "done";
  if (status === "blocked" || status === "missing") return "blocked";
  if (status === "degraded") return "review";
  return "pending";
}

function titleFromCode(code: string) {
  return code
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function deterministicRecommendations(data: ObservabilityData) {
  return (
    data.deterministic_recommendations ||
    data.observability_coverage.deterministic_recommendations ||
    []
  );
}

function resolvedRecommendations(data: ObservabilityData) {
  return (
    data.resolved_recommendations ||
    data.observability_coverage.resolved_recommendations ||
    []
  );
}

function recommendationEvidenceDetail(item: {
  evidence?: Record<string, unknown>;
  lifecycle_status?: string;
}) {
  const evidence = item.evidence || {};
  const estimated = Number(evidence.estimated_savings_tokens ?? 0);
  if (estimated > 0) {
    return `estimated savings ${compactNumber(estimated)} tokens`;
  }
  const unresolved = Number(evidence.unresolved ?? 0);
  if (unresolved > 0) {
    return `${unresolved} unresolved approval gate${unresolved === 1 ? "" : "s"}`;
  }
  if (item.lifecycle_status === "open") {
    return "needs optimization-agent decision";
  }
  return "";
}

function unifiedRecommendations(data: ObservabilityData): UnifiedRecommendation[] {
  const rules = deterministicRecommendations(data);
  const ruleDetails = new Set(rules.map((item) => item.recommendation));
  const summaryRows = data.recommendations
    .filter((item) => !ruleDetails.has(item.detail))
    .map((item) => ({
      id: `summary:${item.code}`,
      severity: item.severity,
      title: item.title,
      detail: item.detail,
      code: item.code,
      evidenceDetail: "",
    }));
  const ruleRows = rules.map((item) => ({
    id: `rule:${item.code}`,
    severity: item.severity,
    title: titleFromCode(item.code),
    detail: item.recommendation,
    code: item.code,
    trigger: item.trigger,
    lifecycleStatus: item.lifecycle_status,
    decisionReason: item.decision_reason,
    evidenceDetail: recommendationEvidenceDetail(item),
  }));
  return [...summaryRows, ...ruleRows];
}

function healthPillLabel(area: TelemetryHealthArea | undefined) {
  const status = area?.status || "unknown";
  const collectorStatus =
    area?.collector && "status" in area.collector ? area.collector.status : undefined;
  const collector =
    area?.collector_status || collectorStatus ? collectorLabel(area?.collector_status || collectorStatus) : "";
  const signals = area?.emitted_signals || area?.signals || {};
  const enabledSignals = Object.entries(signals)
    .filter(([, enabled]) => Boolean(enabled))
    .map(([name]) => name);

  if (status !== "ok") {
    return area?.reason || collector || status;
  }
  if (collector) return collector;
  if (enabledSignals.length) return enabledSignals.join(", ");
  return "ok";
}

function RuntimeHeaderPills({ data }: { data: ObservabilityData }) {
  const health = data.observability_coverage.telemetry_health;

  return (
    <>
      {[
        ["claude", health?.claude_native],
        ["codex", health?.codex_native],
        ["builder", health?.builder_product],
      ].map(([label, area]) => {
        const status = typeof area === "object" ? area.status : undefined;
        return (
          <span
            key={label as string}
            className="inline-flex h-9 items-center gap-2 rounded-full border border-border/65 bg-background/70 px-3"
          >
            <StatusDot tone={healthTone(status)} />
            <span className="font-mono text-[11px] text-foreground">
              {label as string} {healthPillLabel(area as TelemetryHealthArea | undefined)}
            </span>
          </span>
        );
      })}
    </>
  );
}

function Kpi({
  label,
  value,
  detail,
  icon,
}: {
  label: string;
  value: string;
  detail: string;
  icon: ReactNode;
}) {
  return (
    <SurfacePanel className="space-y-3 px-4 py-3">
      <div className="flex items-center justify-between gap-3">
        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
          {label}
        </p>
        <div className="text-muted-foreground">{icon}</div>
      </div>
      <div>
        <p className="font-mono text-[1.45rem] text-foreground">{value}</p>
        <p className="mt-1 text-[11px] text-muted-foreground">{detail}</p>
      </div>
    </SurfacePanel>
  );
}

function RecommendationCard({ item }: { item: UnifiedRecommendation }) {
  return (
    <div className="space-y-2 rounded-[0.75rem] border border-border/65 px-4 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="inline-flex items-center gap-1 rounded-full border border-border bg-muted/40 px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
          <StatusDot tone={SEVERITY_TONE[item.severity] ?? "muted"} />
          {item.severity}
        </span>
        {item.lifecycleStatus ? (
          <span className="inline-flex items-center rounded-full border border-border bg-background/70 px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
            {item.lifecycleStatus.replaceAll("_", " ")}
          </span>
        ) : null}
        <p className="font-medium text-foreground">{item.title}</p>
      </div>
      <p className="text-sm leading-6 text-muted-foreground">{item.detail}</p>
      {item.decisionReason ? (
        <p className="text-[12px] leading-5 text-foreground/80">{item.decisionReason}</p>
      ) : null}
      {item.evidenceDetail ? (
        <p className="font-mono text-[11px] text-muted-foreground">{item.evidenceDetail}</p>
      ) : null}
      {item.code || item.trigger ? (
        <div className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-[11px] text-muted-foreground">
          {item.code ? <span>code {item.code}</span> : null}
          {item.trigger ? <span>trigger {item.trigger}</span> : null}
        </div>
      ) : null}
    </div>
  );
}

function CapabilityMatrix({ capabilities }: { capabilities: RuntimeCapability[] }) {
  const nativeItems = capabilities.filter((item) => item.native);
  const fallbackItems = capabilities.filter((item) => !item.native);

  return (
    <div className="space-y-3">
      <SectionLabel>Runtime capability summary</SectionLabel>
      <p className="text-sm text-muted-foreground">
        Show what the selected runtime handles natively and where the builder still needs
        deterministic fallback support.
      </p>
      <div className="flex flex-wrap gap-2 font-mono text-[11px] text-muted-foreground">
        <span className="rounded-full border border-border/65 px-2.5 py-1">
          native {nativeItems.length}
        </span>
        <span className="rounded-full border border-border/65 px-2.5 py-1">
          fallback {fallbackItems.length}
        </span>
      </div>
      <div className="grid gap-3 lg:grid-cols-2">
        <div className="space-y-2">
          <SectionLabel>Native capability</SectionLabel>
          {nativeItems.length ? (
            <div className="grid gap-2">
              {nativeItems.map((item) => (
                <div key={item.id} className="rounded-[0.75rem] border border-border/65 p-3">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-sm font-medium text-foreground">{item.label}</p>
                    <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-status-shipped">
                      native
                    </span>
                  </div>
                  <p className="mt-2 text-[12px] leading-5 text-muted-foreground">
                    {item.native_signal}
                  </p>
                </div>
              ))}
            </div>
          ) : (
            <p className="rounded-[0.75rem] border border-dashed border-border/70 p-3 text-sm text-muted-foreground">
              No native runtime capability has been detected for this runtime.
            </p>
          )}
        </div>
        <div className="space-y-2">
          <SectionLabel>Runtime fallback</SectionLabel>
          {fallbackItems.length ? (
            <div className="grid gap-2">
              {fallbackItems.map((item) => (
                <div key={item.id} className="rounded-[0.75rem] border border-border/65 p-3">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-sm font-medium text-foreground">{item.label}</p>
                    <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                      fallback
                    </span>
                  </div>
                  <p className="mt-2 text-[12px] leading-5 text-muted-foreground">
                    {item.fallback}
                  </p>
                  {item.diagnostic_gap ? (
                    <p className="mt-2 text-[12px] leading-5 text-status-review">
                      Gap: {item.diagnostic_gap}
                    </p>
                  ) : null}
                </div>
              ))}
            </div>
          ) : (
            <p className="rounded-[0.75rem] border border-dashed border-border/70 p-3 text-sm text-muted-foreground">
              No fallback support is required for the current runtime.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

function PhaseDecisionTable({ rows }: { rows: PhaseRuntimeDecision[] }) {
  if (rows.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No phase-level runtime decisions have been recorded yet.
      </p>
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Phase</TableHead>
          <TableHead>Model / effort</TableHead>
          <TableHead>Tool route</TableHead>
          <TableHead>Subagents</TableHead>
          <TableHead>Reason</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row) => (
          <TableRow key={row.phase}>
            <TableCell className="font-mono">{row.phase}</TableCell>
            <TableCell>{row.model_effort}</TableCell>
            <TableCell>{row.tool_route}</TableCell>
            <TableCell>{row.subagent_policy}</TableCell>
            <TableCell>{row.reason_code}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function ScriptCandidates({ rows }: { rows: DeterministicScriptCandidate[] }) {
  return (
    <div className="space-y-3">
      {rows.map((item) => (
        <div key={item.code} className="rounded-[0.75rem] border border-border/65 p-3">
          <div className="flex items-center justify-between gap-3">
            <p className="font-mono text-[12px] text-foreground">{item.code}</p>
            <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
              {item.severity}
            </span>
          </div>
          <p className="mt-2 text-sm text-muted-foreground">{item.recommendation}</p>
          <p className="mt-1 text-[12px] text-muted-foreground">Trigger: {item.trigger}</p>
          {item.estimated_savings_tokens ? (
            <p className="mt-1 font-mono text-[11px] text-muted-foreground">
              saves about {item.estimated_savings_tokens.toLocaleString()} tokens /{" "}
              {item.estimated_savings_basis || "estimated repeat work"}
            </p>
          ) : null}
        </div>
      ))}
      {rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No repeated deterministic operation has crossed the recommendation threshold.
        </p>
      ) : null}
    </div>
  );
}

function OptimizationDecisionPanel({ data }: { data: ObservabilityData }) {
  const decision = data.optimization_decision;
  if (!decision) return null;
  return (
    <div className="space-y-3">
      <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
        {decision.cli_surface}
      </p>
      <div className="grid gap-3">
        <div className="rounded-[0.75rem] border border-border/65 p-3">
          <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
            Next action
          </p>
          <p className="mt-2 font-mono text-[12px] text-foreground">{decision.next_action}</p>
          <p className="mt-1 text-[11px] leading-5 text-muted-foreground">
            {decision.reason}
          </p>
        </div>
        <div className="rounded-[0.75rem] border border-border/65 p-3">
          <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
            Target area
          </p>
          <p className="mt-2 font-mono text-[12px] text-foreground">{decision.target_area}</p>
          <p className="mt-1 text-[11px] leading-5 text-muted-foreground">
            {decision.model_effort_action}
          </p>
        </div>
        <div className="rounded-[0.75rem] border border-border/65 p-3">
          <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
            Deterministic savings
          </p>
          <p className="mt-2 font-mono text-[12px] text-foreground">
            {decision.estimated_script_savings_tokens.toLocaleString()} tokens
          </p>
          <p className="mt-1 text-[11px] leading-5 text-muted-foreground">
            {decision.subagent_action}
          </p>
        </div>
      </div>
    </div>
  );
}

function RecommendationsPanel({
  data,
  activeTab,
  onTabChange,
}: {
  data: ObservabilityData;
  activeTab: RecommendationTab;
  onTabChange: (next: RecommendationTab) => void;
}) {
  const allRecommendations = unifiedRecommendations(data);
  const ruleRecommendations = deterministicRecommendations(data).map((item) => ({
    id: `rule:${item.code}`,
    severity: item.severity,
    title: titleFromCode(item.code),
    detail: item.recommendation,
    code: item.code,
    trigger: item.trigger,
    lifecycleStatus: item.lifecycle_status,
    decisionReason: item.decision_reason,
    evidenceDetail: recommendationEvidenceDetail(item),
  }));
  const rejectedRecommendations = resolvedRecommendations(data)
    .filter((item) =>
      ["rejected", "deferred", "not_applicable"].includes(String(item.lifecycle_status || "")),
    )
    .map((item) => ({
      id: `resolved:${item.code}:${item.lifecycle_status || "resolved"}`,
      severity: item.severity,
      title: titleFromCode(item.code),
      detail: item.recommendation,
      code: item.code,
      trigger: item.trigger,
      lifecycleStatus: item.lifecycle_status,
      decisionReason: item.decision_reason,
      evidenceDetail: recommendationEvidenceDetail(item),
    }));

  return (
    <SurfacePanel className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <SectionLabel>Recommendations</SectionLabel>
        <Tabs<RecommendationTab>
          value={activeTab}
          onChange={onTabChange}
          items={[
            { value: "all", label: "All" },
            { value: "rules", label: "Rules" },
            { value: "rejected", label: "Rejected" },
          ]}
        />
      </div>
      <p className="text-sm text-muted-foreground">
        Keep only recommendation candidates and recommendation decisions here. Runtime policy
        and optimization evidence live in dedicated sections below.
      </p>
      {activeTab === "all" ? (
        <div className="space-y-3">
          {allRecommendations.map((item) => (
            <RecommendationCard key={item.id} item={item} />
          ))}
        </div>
      ) : null}
      {activeTab === "rules" ? (
        <div className="space-y-3">
          {ruleRecommendations.length ? (
            ruleRecommendations.map((item) => (
              <RecommendationCard key={item.id} item={item} />
            ))
          ) : (
            <p className="rounded-[0.75rem] border border-dashed border-border/65 p-4 text-sm text-muted-foreground">
              No deterministic rule has crossed the recommendation threshold.
            </p>
          )}
        </div>
      ) : null}
      {activeTab === "rejected" ? (
        <div className="space-y-3">
          {rejectedRecommendations.length ? (
            rejectedRecommendations.map((item) => (
              <RecommendationCard key={item.id} item={item} />
            ))
          ) : (
            <p className="rounded-[0.75rem] border border-dashed border-border/65 p-4 text-sm text-muted-foreground">
              No recommendation has been rejected, deferred, or marked not applicable yet.
            </p>
          )}
        </div>
      ) : null}
    </SurfacePanel>
  );
}

function RuntimeDetailPanel({
  data,
  activeTab,
  onTabChange,
}: {
  data: ObservabilityData;
  activeTab: RuntimeDetailTab;
  onTabChange: (next: RuntimeDetailTab) => void;
}) {
  const capabilities = data.runtime_capability_matrix?.capabilities ?? [];
  const scriptCandidates = data.deterministic_script_candidates ?? [];

  return (
    <SurfacePanel className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <SectionLabel>Runtime decisions</SectionLabel>
        <Tabs<RuntimeDetailTab>
          value={activeTab}
          onChange={onTabChange}
          items={[
            { value: "optimization", label: "Optimization" },
            { value: "phase", label: "Phase" },
            { value: "capability", label: "Runtime capability" },
          ]}
        />
      </div>
      {activeTab === "optimization" ? (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(280px,0.75fr)]">
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">
              The optimization agent should evaluate this after preflight evidence has been
              collected.
            </p>
            <OptimizationDecisionPanel data={data} />
          </div>
          {scriptCandidates.length ? (
            <div className="space-y-3">
              <SectionLabel>Script candidates</SectionLabel>
              <ScriptCandidates rows={scriptCandidates} />
            </div>
          ) : (
            <div className="rounded-[1.1rem] border border-dashed border-border/70 bg-background/55 p-4">
              <p className="text-sm text-muted-foreground">
                No deterministic script candidate currently needs operator attention.
              </p>
            </div>
          )}
        </div>
      ) : null}
      {activeTab === "phase" ? <PhaseDecisionTable rows={data.phase_runtime_decisions ?? []} /> : null}
      {activeTab === "capability" ? <CapabilityMatrix capabilities={capabilities} /> : null}
    </SurfacePanel>
  );
}

function AgentTable({ rows }: { rows: RuntimeAggregateRow[] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Agent</TableHead>
          <TableHead>Runs</TableHead>
          <TableHead>Tokens</TableHead>
          <TableHead>Cached</TableHead>
          <TableHead>Cost</TableHead>
          <TableHead>Duration</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row) => (
          <TableRow key={row.agent_name ?? "unknown"}>
            <TableCell className="font-mono">{row.agent_name ?? "unknown"}</TableCell>
            <TableCell>{row.runs}</TableCell>
            <TableCell>{compactNumber(row.input_tokens + row.output_tokens)}</TableCell>
            <TableCell>{compactNumber(row.cached_tokens)}</TableCell>
            <TableCell>{estimatedCostDisplay(row.estimated_cost_usd)}</TableCell>
            <TableCell>{duration(row.duration_ms)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function ModelEffortTable({ rows }: { rows: RuntimeAggregateRow[] }) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Model</TableHead>
          <TableHead>Effort</TableHead>
          <TableHead>Runs</TableHead>
          <TableHead>Cost</TableHead>
          <TableHead>Tokens</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row) => (
          <TableRow key={`${row.model ?? "unknown"}:${row.effort ?? "default"}`}>
            <TableCell className="font-mono">{row.model ?? "unknown"}</TableCell>
            <TableCell className="font-mono">{row.effort || "default"}</TableCell>
            <TableCell>{row.runs}</TableCell>
            <TableCell>{estimatedCostDisplay(row.estimated_cost_usd)}</TableCell>
            <TableCell>{compactNumber(row.input_tokens + row.output_tokens)}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}

function RuntimeHistoryPanel({ rows }: { rows: RuntimeAggregateRow[] }) {
  if (rows.length === 0) return null;

  return (
    <SurfacePanel className="space-y-3">
      <SectionLabel>Runtime telemetry history</SectionLabel>
      <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
        {rows.map((row) => (
          <div
            key={`${row.runtime_sdk ?? "unknown"}:${row.provider ?? "default"}`}
            className="rounded-[0.75rem] border border-border/65 px-3 py-3"
          >
            <div className="flex items-center justify-between gap-3">
              <span className="font-mono text-[12px] text-foreground">
                {row.runtime_sdk || "unknown"}
              </span>
              <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
                {row.runs} runs
              </span>
            </div>
            <p className="mt-1 text-[11px] text-muted-foreground">
              {providerLabel(row.provider)} / {compactNumber(row.input_tokens + row.output_tokens)} tokens
            </p>
            <p className="mt-2 font-mono text-[11px] text-muted-foreground">
              {estimatedCostDisplay(row.estimated_cost_usd)}
              {row.estimated_codex_credits
                ? ` / ${Number(row.estimated_codex_credits).toFixed(3)} Codex credits`
                : ""}
            </p>
          </div>
        ))}
      </div>
    </SurfacePanel>
  );
}

export default function ObservabilityPage() {
  const [data, setData] = useState<ObservabilityData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [recommendationTab, setRecommendationTab] =
    useState<RecommendationTab>("all");
  const [runtimeDetailTab, setRuntimeDetailTab] =
    useState<RuntimeDetailTab>("optimization");

  const load = () => {
    fetchObservability()
      .then((payload) => {
        setData(payload);
        setError(null);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    const interval = setInterval(load, 5000);
    return () => clearInterval(interval);
  }, []);

  if (loading) return <LoadingState label="Loading observability evidence..." />;
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!data) return <ErrorState message="No observability data returned." onRetry={load} />;

  const coverage = data.observability_coverage;
  const aggregates = data.runtime_aggregates;
  const totals = aggregates.totals;
  const tools = aggregates.tool_observability;
  const isCodex = data.runtime.selected_runtime_sdk === "codex_sdk";
  const runtimeRows = aggregates.by_runtime ?? [];
  const hasCodexHistory = runtimeRows.some((row) => row.runtime_sdk === "codex_sdk");

  return (
    <PageFrame variant="overview">
      <PageHeader
        className="page-intro-compact"
        eyebrow="Runtime observability"
        title="Know whether the selected SDK can explain the run."
        description="Observability checks the diagnostic evidence behind failures, token waste, routing choices, provider limits, and tool behavior."
        aside={<RuntimeHeaderPills data={data} />}
      />

      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <Kpi
            label="Runtime"
            value={data.runtime.selected_runtime_sdk}
            detail={`${providerLabel(data.runtime.provider)} / ${data.runtime.model || "model unset"}`}
            icon={<Cpu className="h-4 w-4" />}
          />
          <Kpi
            label="Missing signals"
            value={String(coverage.missing_signals.length)}
            detail={coverage.missing_signals.length ? "diagnostic gaps" : "coverage complete"}
            icon={<AlertTriangle className="h-4 w-4" />}
          />
          <Kpi
            label="Estimated cost"
            value={estimatedCostDisplay(totals.estimated_cost_usd)}
            detail={
              totals.estimated_codex_credits
                ? `${Number(totals.estimated_codex_credits).toFixed(3)} Codex credits`
                : "token rate estimate"
            }
            icon={<Gauge className="h-4 w-4" />}
          />
          <Kpi
            label="Tool events"
            value={String(tools.agent_run_event_count)}
            detail={tools.missing_tool_events ? "missing event evidence" : "event evidence stored"}
            icon={<Activity className="h-4 w-4" />}
          />
        </div>

        {isCodex || hasCodexHistory ? (
          <SurfacePanel className="space-y-3">
            <SectionLabel>Codex optimization evidence</SectionLabel>
            <div className="grid gap-3 md:grid-cols-3">
              <Kpi
                label="Raw tokens"
                value={compactNumber(data.optimization_summary?.raw_token_total)}
                detail="primary score"
                icon={<RefreshCw className="h-4 w-4" />}
              />
              <Kpi
                label="Cache reuse"
                value={cacheReuseDisplay(data.optimization_summary?.cache_ratio)}
                detail="cached input vs fresh input"
                icon={<Gauge className="h-4 w-4" />}
              />
              <Kpi
                label="Avoidable"
                value={compactNumber(data.optimization_summary?.avoidable_token_estimate)}
                detail="estimated avoidable tokens"
                icon={<AlertTriangle className="h-4 w-4" />}
              />
            </div>
          </SurfacePanel>
        ) : null}

        <RuntimeHistoryPanel rows={runtimeRows} />

        <RecommendationsPanel
          data={data}
          activeTab={recommendationTab}
          onTabChange={setRecommendationTab}
        />

        <RuntimeDetailPanel
          data={data}
          activeTab={runtimeDetailTab}
          onTabChange={setRuntimeDetailTab}
        />

        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_390px]">
          <SurfacePanel className="space-y-3">
            <SectionLabel>Agent breakdown</SectionLabel>
            <AgentTable rows={aggregates.by_agent} />
          </SurfacePanel>
          <SurfacePanel className="space-y-3">
            <SectionLabel>Tool behavior</SectionLabel>
            <div className="space-y-3">
              {tools.tool_counts.slice(0, 6).map((tool) => (
                <div key={tool.tool_name} className="flex items-center justify-between gap-3">
                  <span className="font-mono text-[12px] text-foreground">{tool.tool_name}</span>
                  <span className="font-mono text-[12px] text-muted-foreground">
                    {tool.calls} calls
                  </span>
                </div>
              ))}
              {tools.tool_counts.length === 0 ? (
                <p className="text-sm text-muted-foreground">No tool events recorded yet.</p>
              ) : null}
            </div>
          </SurfacePanel>
        </div>

        <SurfacePanel className="space-y-3">
          <SectionLabel>Model and effort breakdown</SectionLabel>
          <ModelEffortTable rows={aggregates.by_model_effort} />
        </SurfacePanel>
      </div>
    </PageFrame>
  );
}
