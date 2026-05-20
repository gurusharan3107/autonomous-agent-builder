import type { TaskAgentRunSummary, TaskBoardItem, TaskGateResultSummary } from "@/lib/types";
import {
  evidenceSummary,
  formatCompactNumber,
  formatDuration,
  runDiffText,
  runTokenTotal,
} from "./board-model";

export function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-border/55 py-2 text-[12px]">
      <span className="text-muted-foreground">{label}</span>
      <span className="min-w-0 truncate text-right font-mono text-foreground">{value}</span>
    </div>
  );
}

export function RunEvidenceCard({ task, run }: { task: TaskBoardItem; run: TaskAgentRunSummary }) {
  const diffText = runDiffText(run);
  return (
    <div className="rounded-xl border border-border/65 px-3 py-3">
      <div className="flex items-center justify-between gap-3">
        <span className="min-w-0 truncate text-[13px] font-medium text-foreground">
          {task.title}
        </span>
        <span className="shrink-0 font-mono text-[10.5px] uppercase tracking-[0.12em] text-muted-foreground">
          {run.status}
        </span>
      </div>
      <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 font-mono text-[11px] text-muted-foreground">
        <span>{run.agent_name}</span>
        <span>{run.runtime_sdk || run.provider || "runtime"}</span>
        <span>{run.num_turns || 0} turns</span>
        <span>{formatCompactNumber(runTokenTotal(run))} tokens</span>
        <span>{run.status === "running" ? "running" : formatDuration(run.duration_ms)}</span>
      </div>
      {diffText ? (
        <p className="mt-2 text-[12px] leading-5 text-muted-foreground">{diffText}</p>
      ) : null}
    </div>
  );
}

export function GateEvidenceCard({
  task,
  gate,
}: {
  task: TaskBoardItem;
  gate: TaskGateResultSummary;
}) {
  const summary = evidenceSummary(gate.evidence);
  return (
    <div className="rounded-xl border border-border/65 px-3 py-3">
      <div className="flex items-center justify-between gap-3">
        <span className="min-w-0 truncate text-[13px] font-medium text-foreground">
          {gate.gate_name}
        </span>
        <span className="shrink-0 font-mono text-[10.5px] uppercase tracking-[0.12em] text-muted-foreground">
          {gate.status}
        </span>
      </div>
      <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 font-mono text-[11px] text-muted-foreground">
        <span>{task.title}</span>
        <span>{gate.findings_count} finding{gate.findings_count === 1 ? "" : "s"}</span>
        <span>{formatDuration(gate.elapsed_ms)}</span>
        {gate.error_code ? <span>{gate.error_code}</span> : null}
      </div>
      {summary ? (
        <p className="mt-2 text-[12px] leading-5 text-muted-foreground">{summary}</p>
      ) : null}
    </div>
  );
}
