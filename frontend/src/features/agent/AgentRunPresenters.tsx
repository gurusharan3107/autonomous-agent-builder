import { StatusDot } from "@/design-system";

const AGENT_STAGE_STEPS = ["Plan", "Design", "Implement", "Gates", "Review", "Build", "Done"];

export function AgentStageStepper({ current }: { current: number }) {
  const clamped = Math.max(0, Math.min(current, AGENT_STAGE_STEPS.length - 1));
  return (
    <div className="flex min-w-0 flex-wrap items-center gap-y-2">
      {AGENT_STAGE_STEPS.map((step, index) => {
        const isDone = index < clamped;
        const isCurrent = index === clamped;
        const tone = isDone ? "done" : isCurrent ? "active" : "muted";
        return (
          <div key={step} className="flex items-center">
            <div className="flex items-center gap-1.5">
              <StatusDot tone={tone} pulse={isCurrent && clamped < AGENT_STAGE_STEPS.length - 1} />
              <span className="font-mono text-[10px] uppercase text-muted-foreground">
                {step}
              </span>
            </div>
            {index < AGENT_STAGE_STEPS.length - 1 ? (
              <span className={isDone ? "mx-2 h-px w-4 bg-status-done" : "mx-2 h-px w-4 bg-border"} />
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

export function MetricRow({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-3 text-[12.5px]">
      <span className="text-muted-foreground">{label}</span>
      <span className={mono ? "font-mono text-[11px] tabular-nums text-foreground" : "text-foreground"}>
        {value}
      </span>
    </div>
  );
}

export function TokenMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 text-[12px]">
      <span className="min-w-0 text-muted-foreground">{label}</span>
      <span className="font-mono text-[11px] tabular-nums text-foreground">{value}</span>
    </div>
  );
}
