import { Link } from "react-router-dom";
import { ArrowRight, X } from "lucide-react";
import { Button, SectionLabel } from "@/design-system";
import type { TaskAgentRunSummary, TaskBoardItem } from "@/lib/types";
import {
  compactClientText,
  formatDuration,
  isPhaseLevelRun,
  latestRun,
  stringValue,
} from "./board-model";
import { DetailRow } from "./board-detail-shared";

export function TaskDetailSidebar({
  task,
  onClose,
}: {
  task: TaskBoardItem | null;
  onClose: () => void;
}) {
  if (!task) return null;
  return <TaskDetailContent key={task.id} task={task} onClose={onClose} />;
}

function TaskDetailContent({
  task,
  onClose,
}: {
  task: TaskBoardItem;
  onClose: () => void;
}) {
  const sprint = task.sprint_execution ?? {};
  const acceptance = task.acceptance_criteria ?? [];
  const dependencies = task.dependencies ?? [];
  const agentRuns = task.agent_runs ?? [];
  const taskRuns = agentRuns.filter((run) => !isPhaseLevelRun(run));
  const phaseRuns = agentRuns.filter((run) => isPhaseLevelRun(run));
  const traceRun = [...taskRuns].reverse().find((run) => run.status === "running") ?? latestRun(taskRuns);
  const traceSessionId = traceRun ? stringValue(traceRun.session_id) : "";
  const traceHref = traceRun
    ? `/?mode=trace&task=${encodeURIComponent(task.id)}&run=${encodeURIComponent(traceRun.id)}${
        traceSessionId ? `&session=${encodeURIComponent(traceSessionId)}` : ""
      }`
    : "";
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-foreground/12 backdrop-blur-[2px]">
      <button
        type="button"
        aria-label="Close task details"
        className="absolute inset-0 cursor-default"
        onClick={onClose}
      />
      <aside className="relative h-full w-full max-w-[460px] overflow-y-auto border-l border-border bg-background px-5 py-5 shadow-[var(--shadow-lg)]">
        <div className="mb-5 flex items-start justify-between gap-4">
          <div className="min-w-0 space-y-2">
            <div className="flex flex-wrap items-center gap-2 font-mono text-[10.5px] uppercase tracking-[0.16em] text-muted-foreground">
              <span>{task.id.slice(0, 8)}</span>
              <span>{task.feature_item_type}</span>
              <span>{task.status}</span>
            </div>
            <h2 className="text-[20px] font-medium leading-tight text-foreground">{task.title}</h2>
            <p className="text-[12.5px] leading-6 text-muted-foreground">
              {task.description || task.feature_description || task.feature_title}
            </p>
          </div>
          <Button type="button" variant="ghost" size="icon-sm" onClick={onClose} aria-label="Close">
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="space-y-5">
          <section>
            <SectionLabel>Work item</SectionLabel>
            <div className="mt-3 rounded-xl border border-border/65 px-3">
              <DetailRow label="Feature" value={task.feature_title || task.feature_id} />
              <DetailRow label="Step" value={task.phase} />
              <DetailRow label="Status" value={task.status} />
            </div>
          </section>

          {traceRun ? (
            <section>
              <SectionLabel>Evidence handoff</SectionLabel>
              <p className="mt-1 text-[12px] leading-5 text-muted-foreground">
                Full work history, decisions, cost, tokens, runtime metadata, and diff evidence are inspected from the evidence trace.
              </p>
              <Button asChild variant="outline" size="sm" className="mt-3 rounded-full">
                <Link to={traceHref}>
                  Open evidence trace
                  <ArrowRight className="h-3.5 w-3.5" />
                </Link>
              </Button>
            </section>
          ) : (
            <p className="rounded-xl border border-border/65 px-3 py-3 text-[12px] leading-6 text-muted-foreground">
              No task-owned run evidence is recorded yet. Dispatch or recover the task to produce Agent Run trace evidence.
            </p>
          )}

          {phaseRuns.length > 0 ? (
            <section>
              <SectionLabel>Phase runs</SectionLabel>
              <ul className="mt-3 space-y-2">
                {phaseRuns.map((run) => (
                  <PhaseRunRow key={run.id} task={task} run={run} />
                ))}
              </ul>
            </section>
          ) : null}

          <section>
            <SectionLabel>Sprint handoff</SectionLabel>
            <div className="mt-3 rounded-xl border border-border/65 px-3">
              <DetailRow label="Batch" value={stringValue(sprint.batch_id, "unassigned")} />
              <DetailRow label="Execution" value={stringValue(sprint.execution_mode, "sequential")} />
              <DetailRow label="Parallel group" value={stringValue(sprint.parallel_group, "none")} />
              <DetailRow label="Plan" value={stringValue(sprint.plan_id, "shared sprint plan")} />
              <DetailRow label="Design" value={stringValue(sprint.design_id, "shared sprint design")} />
            </div>
            {stringValue(sprint.implementation_brief) ? (
              <p className="mt-3 rounded-xl border border-border/65 bg-muted/28 px-3 py-3 text-[12px] leading-6 text-muted-foreground">
                {compactClientText(stringValue(sprint.implementation_brief), 420)}
              </p>
            ) : null}
            {stringValue(sprint.file_ownership_hint) ? (
              <p className="mt-2 font-mono text-[11px] text-muted-foreground">
                {stringValue(sprint.file_ownership_hint)}
              </p>
            ) : null}
          </section>

          {acceptance.length > 0 ? (
            <section>
              <SectionLabel>Acceptance</SectionLabel>
              <ul className="mt-3 space-y-2">
                {acceptance.map((item) => (
                  <li key={item} className="rounded-xl border border-border/65 px-3 py-2 text-[12px] leading-5 text-muted-foreground">
                    {item}
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          {dependencies.length > 0 ? (
            <section>
              <SectionLabel>Prerequisites</SectionLabel>
              <div className="mt-3 flex flex-wrap gap-2">
                {dependencies.map((item) => (
                  <span key={item} className="rounded-full border border-border/65 px-2.5 py-1 font-mono text-[11px] text-muted-foreground">
                    {item}
                  </span>
                ))}
              </div>
            </section>
          ) : null}

          {task.approval_gate_id ? (
            <Button asChild className="w-full rounded-full">
              <Link to={`/approvals/${task.approval_gate_id}`}>
                Review approval
                <ArrowRight className="h-4 w-4" />
              </Link>
            </Button>
          ) : null}
        </div>
      </aside>
    </div>
  );
}

function PhaseRunRow({ task, run }: { task: TaskBoardItem; run: TaskAgentRunSummary }) {
  const sessionId = stringValue(run.session_id);
  const href = `/?mode=trace&task=${encodeURIComponent(task.id)}&run=${encodeURIComponent(run.id)}${
    sessionId ? `&session=${encodeURIComponent(sessionId)}` : ""
  }`;
  const duration = run.status === "running" ? "running" : formatDuration(run.duration_ms);
  const startedAt = run.started_at ? new Date(run.started_at).toLocaleTimeString() : "";
  return (
    <li>
      <Link
        to={href}
        className="flex items-center justify-between gap-3 rounded-xl border border-border/65 px-3 py-2.5 text-[12px] transition-colors hover:bg-muted/40"
      >
        <div className="min-w-0 space-y-0.5">
          <span className="block truncate font-mono font-medium text-foreground">
            {run.agent_name}
          </span>
          <span className="block font-mono text-[11px] text-muted-foreground">
            {startedAt ? `${startedAt} · ` : ""}{duration}
          </span>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <span className="font-mono text-[10.5px] uppercase tracking-[0.12em] text-muted-foreground">
            {run.status}
          </span>
          <ArrowRight className="h-3.5 w-3.5 text-muted-foreground" />
        </div>
      </Link>
    </li>
  );
}
