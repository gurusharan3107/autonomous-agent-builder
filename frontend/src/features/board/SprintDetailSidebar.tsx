import { Gauge, Terminal, X } from "lucide-react";
import { Button, SectionLabel } from "@/design-system";
import type { CurrentSprintSummary, SprintPlanSummary, TaskBoardItem } from "@/lib/types";
import {
  BUILD_AGENT_NAMES,
  IMPLEMENTATION_AGENT_NAMES,
  REVIEW_AGENT_NAMES,
  detailRecord,
  formatDuration,
  gateResultsForTasks,
  isVerificationRun,
  latestStageRun,
  splitCurrentVerificationRuns,
  stageRuns,
  stringList,
  stringValue,
  type SprintStage,
} from "./board-model";
import { DetailRow, GateEvidenceCard, RunEvidenceCard } from "./board-detail-shared";

type SprintOptimizationInsight = {
  status: string;
  recommendation: string;
  action: string;
  benefit: string;
  proof: string;
  commands: Array<{ command: string; result: string; summary: string }>;
};

function firstRegexMatch(text: string, pattern: RegExp): string {
  return text.match(pattern)?.[1]?.trim() ?? "";
}

function parseOptimizationJson(summary: string): Record<string, unknown> {
  const fenced = summary.match(/```json\s*([\s\S]*?)```/)?.[1];
  const start = summary.indexOf("{");
  const end = summary.lastIndexOf("}");
  const raw = fenced || (start >= 0 && end > start ? summary.slice(start, end + 1) : "");
  if (!raw.trim().startsWith("{")) return {};
  try {
    return JSON.parse(raw) as Record<string, unknown>;
  } catch {
    return {};
  }
}

function sprintOptimizationInsight(sprint?: CurrentSprintSummary | null): SprintOptimizationInsight | null {
  const evidence = detailRecord(sprint?.verification_evidence);
  const optimization = detailRecord(evidence.optimization_agent);
  const summary = stringValue(optimization.summary);
  const structured = parseOptimizationJson(summary);
  const status =
    stringValue(structured.status) ||
    firstRegexMatch(summary, /"status"\s*:\s*"([^"]+)/) ||
    stringValue(optimization.status);
  if (!status) return null;

  const recommendation =
    stringValue(optimization.selected_recommendation) ||
    stringValue(structured.selected_recommendation) ||
    firstRegexMatch(summary, /"selected_recommendation"\s*:\s*"([^"]+)/) ||
    stringValue(optimization.reason, "post_ship_optimization");
  const whySelected =
    stringValue(structured.why_selected) ||
    firstRegexMatch(summary, /"why_selected"\s*:\s*"([^"]+)/) ||
    summary;
  const nextAction =
    stringValue(structured.next_action) ||
    firstRegexMatch(summary, /"next_action"\s*:\s*"([^"]+)/);
  const estimatedSavings =
    firstRegexMatch(whySelected, /estimated\s+([0-9,]+)\s+(?:non-cached\+output\s+)?token/i) ||
    firstRegexMatch(summary, /estimated\s+([0-9,]+)\s+(?:non-cached\+output\s+)?token/i);
  const firstCommand = Array.isArray(structured.commands)
    ? stringValue(detailRecord(structured.commands[0]).command)
    : firstRegexMatch(summary, /"command"\s*:\s*"([^"]+)"/);
  const rawCommands = Array.isArray(optimization.commands)
    ? optimization.commands
    : Array.isArray(structured.commands)
      ? structured.commands
      : [];
  const structuredCommands = rawCommands.length > 0
    ? rawCommands
        .map((item) => {
          const record = detailRecord(item);
          return {
            command: stringValue(record.command),
            result: stringValue(record.result, "not_run"),
            summary: stringValue(record.summary),
          };
        })
        .filter((item) => item.command)
    : [];
  const regexCommand = firstRegexMatch(summary, /"command"\s*:\s*"([^"]+)/);
  const regexResult = firstRegexMatch(summary, /"result"\s*:\s*"([^"]+)/);
  const commands = structuredCommands.length > 0
    ? structuredCommands
    : regexCommand
      ? [{ command: regexCommand, result: stringValue(regexResult, status), summary: "" }]
      : [];
  const generatedAppSkip = stringValue(optimization.reason) === "generated_app_workspace";

  return {
    status,
    recommendation,
    action:
      nextAction ||
      (status === "skipped"
        ? stringValue(optimization.summary, "No model optimization action was needed for this sprint.")
        : status === "blocked"
          ? "Optimization needs the builder source workspace."
          : stringValue(optimization.summary, "Optimization evidence captured for the next delivery-system improvement.")),
    benefit: stringValue(optimization.benefit) || (estimatedSavings
      ? `Expected saving: about ${estimatedSavings} tokens by replacing repeatable model work with a deterministic script.`
      : generatedAppSkip
        ? "Expected saving: avoids spending post-ship optimization tokens inside generated app workspaces."
        : "Expected benefit: keeps the next optimization action visible from shipped sprint telemetry."),
    proof: stringValue(firstCommand, stringValue(optimization.agent_name, "telemetry")),
    commands,
  };
}

export function SprintDetailSidebar({
  stage,
  plan,
  currentSprint,
  activeTasks,
  sprintTasks,
  onClose,
}: {
  stage: SprintStage | null;
  plan?: SprintPlanSummary | null;
  currentSprint?: CurrentSprintSummary | null;
  activeTasks: TaskBoardItem[];
  sprintTasks: TaskBoardItem[];
  onClose: () => void;
}) {
  if (!stage || (!plan && !currentSprint)) return null;
  const implementationTasks = sprintTasks.length > 0 ? sprintTasks : activeTasks;
  const designDetails = detailRecord(plan?.design_details);
  const sharedConcerns = stringList(designDetails.shared_concerns);
  const gateResults = gateResultsForTasks(implementationTasks);
  const implementationRuns = stageRuns(implementationTasks, IMPLEMENTATION_AGENT_NAMES);
  const reviewRuns = stageRuns(implementationTasks, REVIEW_AGENT_NAMES);
  const buildRuns = stageRuns(implementationTasks, BUILD_AGENT_NAMES);
  const title =
    stage === "plan"
      ? "Sprint plan"
      : stage === "design"
        ? "Sprint design"
        : stage === "implementation"
          ? "Sprint implementation"
          : stage === "verify"
            ? "Sprint gates"
            : stage === "pr_review"
              ? "Sprint review"
              : stage === "build"
                ? "Sprint build"
                : "Sprint shipped";
  const subtitle =
    stage === "plan"
      ? `${plan?.batch_count ?? 0} planned batch${(plan?.batch_count ?? 0) === 1 ? "" : "es"}`
      : stage === "design"
        ? `${sharedConcerns.length} shared concern${sharedConcerns.length === 1 ? "" : "s"}`
        : stage === "implementation"
          ? `${implementationRuns.length} implementation run${implementationRuns.length === 1 ? "" : "s"}`
          : stage === "verify"
            ? `${gateResults.length} gate result${gateResults.length === 1 ? "" : "s"}`
            : stage === "pr_review"
              ? `${reviewRuns.length} review/evidence run${reviewRuns.length === 1 ? "" : "s"}`
              : stage === "build"
                ? `${buildRuns.length} build or acceptance run${buildRuns.length === 1 ? "" : "s"}`
                : `${currentSprint?.verification_status ?? "pending"} verification`;
  const includedItems = currentSprint?.included_items ?? [];
  const optimization = sprintOptimizationInsight(currentSprint);
  const phaseStatus = currentSprint?.phase_statuses?.[stage] ?? currentSprint?.active_phase ?? "pending";
  const runtimeSummary = `${plan?.model || currentSprint?.model || "runtime selected"} / ${plan?.effort || currentSprint?.effort || "medium"}`;
  const executionSummary =
    plan?.batch_count && plan.batch_count > 0
      ? `${plan.batch_count} batch${plan.batch_count === 1 ? "" : "es"} · ${plan.sequential_count ?? 0} sequential · ${plan.parallel_count ?? 0} parallel`
      : plan?.strategy || plan?.mode || "sprint";
  const summaryRows =
    stage === "plan"
      ? [
          { label: "Status", value: phaseStatus },
          { label: "Planner", value: runtimeSummary },
          { label: "Plan shape", value: executionSummary },
          { label: "Context", value: stringValue(plan?.context_strategy, "bounded sprint context") },
        ]
      : stage === "design"
        ? [
            { label: "Status", value: phaseStatus },
            { label: "Designer", value: runtimeSummary },
            { label: "Output", value: `${sharedConcerns.length} shared concern${sharedConcerns.length === 1 ? "" : "s"}` },
            { label: "Scope", value: stringValue(plan?.strategy, "single sprint design") },
          ]
        : stage === "implementation"
          ? [
              { label: "Status", value: phaseStatus },
              { label: "Agent", value: "code-gen" },
              { label: "Runs", value: `${implementationRuns.length}` },
              { label: "Tasks", value: `${implementationTasks.length}` },
            ]
          : stage === "verify"
            ? [
                { label: "Status", value: phaseStatus },
                { label: "Owner", value: "quality gates" },
                { label: "Gate results", value: `${gateResults.length}` },
                { label: "Failures", value: `${gateResults.filter(({ gate }) => !["pass", "warn"].includes(gate.status)).length}` },
              ]
            : stage === "pr_review"
              ? [
                  { label: "Status", value: phaseStatus },
                  { label: "Owner", value: reviewRuns.some(({ run }) => run.agent_name === "pr-creator") ? "pr-creator" : "evidence-collector" },
                  { label: "Runs", value: `${reviewRuns.length}` },
                  { label: "Approval", value: implementationTasks.some((task) => task.pending_approval_count > 0) ? "pending" : "not required" },
                ]
              : stage === "build"
                ? [
                    { label: "Status", value: phaseStatus },
                    { label: "Owner", value: buildRuns.some(({ run }) => run.agent_name === "feature-verifier") ? "feature-verifier" : "build-verifier" },
                    { label: "Runs", value: `${buildRuns.length}` },
                    { label: "Verification", value: currentSprint?.verification_status ?? "pending" },
                  ]
                : [
                    { label: "Status", value: phaseStatus },
                    { label: "Verification", value: currentSprint?.verification_status ?? "pending" },
                    { label: "Tasks shipped", value: `${implementationTasks.filter((task) => task.status === "done").length}` },
                    { label: "Optimization", value: optimization?.recommendation ?? "not recorded" },
                  ];
  const verificationRuns = sprintTasks.flatMap((task) =>
    (task.agent_runs ?? [])
      .filter(isVerificationRun)
      .map((run) => ({ task, run })),
  );
  const verificationSplit = splitCurrentVerificationRuns(verificationRuns.map(({ run }) => run));
  const failedRepairRuns = verificationSplit.history.filter((run) => run.status !== "completed").length;

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-foreground/12 backdrop-blur-[2px]">
      <button
        type="button"
        aria-label="Close sprint details"
        className="absolute inset-0 cursor-default"
        onClick={onClose}
      />
      <aside className="relative h-full w-full max-w-[520px] overflow-y-auto border-l border-border bg-background px-5 py-5 shadow-[var(--shadow-lg)]">
        <div className="mb-5 flex items-start justify-between gap-4">
          <div className="min-w-0 space-y-2">
            <div className="font-mono text-[10.5px] uppercase tracking-[0.16em] text-muted-foreground">
              {currentSprint?.label ?? `Sprint ${plan?.sprint_number ?? 1}`} · {stage}
            </div>
            <h2 className="text-[20px] font-medium leading-tight text-foreground">{title}</h2>
            <p className="text-[12.5px] leading-6 text-muted-foreground">{subtitle}</p>
          </div>
          <Button type="button" variant="ghost" size="icon-sm" onClick={onClose} aria-label="Close">
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="space-y-5">
          <section>
            <SectionLabel>Summary</SectionLabel>
            <div className="mt-3 rounded-xl border border-border/65 px-3">
              {summaryRows.map((row) => (
                <DetailRow key={row.label} label={row.label} value={row.value} />
              ))}
            </div>
          </section>

          {stage === "plan" ? (
            <section>
              <SectionLabel>Planning output</SectionLabel>
              <div className="mt-3 rounded-xl border border-border/65 px-3">
                <DetailRow label="Strategy" value={stringValue(plan?.strategy, "shared sprint plan")} />
                <DetailRow label="Context" value={stringValue(plan?.context_strategy, "bounded sprint context")} />
                <DetailRow label="Outcomes" value={`${includedItems.length}`} />
              </div>
            </section>
          ) : null}

          {stage === "verify" ? (
            <section>
              <SectionLabel>Gate evidence</SectionLabel>
              <div className="mt-3 space-y-2">
                {gateResults.length > 0 ? (
                  gateResults.map(({ task, gate }) => (
                    <GateEvidenceCard key={`${task.id}-${gate.id}`} task={task} gate={gate} />
                  ))
                ) : (
                  <p className="rounded-xl border border-border/65 px-3 py-3 text-[12px] leading-6 text-muted-foreground">
                    No per-gate result rows are recorded for this sprint yet. The phase remains pending until quality gates persist pass, warn, fail, or error evidence.
                  </p>
                )}
              </div>
            </section>
          ) : null}

          {stage === "pr_review" ? (
            <section>
              <SectionLabel>Review evidence</SectionLabel>
              <div className="mt-3 space-y-2">
                {reviewRuns.length > 0 ? (
                  reviewRuns.map(({ task, run }) => (
                    <RunEvidenceCard key={`${task.id}-${run.id}`} task={task} run={run} />
                  ))
                ) : (
                  <p className="rounded-xl border border-border/65 px-3 py-3 text-[12px] leading-6 text-muted-foreground">
                    No review or evidence-collector run is recorded for this sprint yet. Local app flows should record change evidence; remote flows should open a sprint PR approval.
                  </p>
                )}
              </div>
            </section>
          ) : null}

          {stage === "shipped" && optimization ? (
            <section>
              <SectionLabel>Optimization</SectionLabel>
              <div className="mt-3 rounded-xl border border-status-done/35 bg-status-done/8 px-3 py-3">
                <div className="mb-2 flex items-center gap-2">
                  <Gauge className="h-4 w-4 text-status-done" />
                  <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-foreground">
                    {optimization.status} · {optimization.recommendation}
                  </span>
                </div>
                <div className="rounded-lg border border-border/55 px-3">
                  <DetailRow label="Action" value={optimization.action} />
                  <DetailRow label="Benefit" value={optimization.benefit} />
                  <DetailRow label="Proof" value={optimization.proof} />
                </div>
                <div className="mt-3">
                  <SectionLabel>Command timeline</SectionLabel>
                  {optimization.commands.length > 0 ? (
                    <ol className="mt-2 space-y-2">
                      {optimization.commands.map((item, index) => (
                        <li
                          key={`${item.command}-${index}`}
                          className="grid grid-cols-[18px_1fr] gap-3 rounded-lg border border-border/55 bg-background/70 px-3 py-2.5"
                        >
                          <div className="pt-0.5 text-muted-foreground">
                            <Terminal className="h-4 w-4" />
                          </div>
                          <div className="min-w-0">
                            <div className="font-mono text-[10.5px] uppercase tracking-[0.12em] text-muted-foreground">
                              step {index + 1} · {item.result}
                            </div>
                            <p className="mt-1 break-words font-mono text-[12px] leading-5 text-foreground">
                              {item.command}
                            </p>
                            {item.summary ? (
                              <p className="mt-1 text-[12px] leading-5 text-muted-foreground">
                                {item.summary}
                              </p>
                            ) : null}
                          </div>
                        </li>
                      ))}
                    </ol>
                  ) : (
                    <p className="mt-2 rounded-lg border border-border/55 bg-background/70 px-3 py-2.5 text-[12px] leading-5 text-muted-foreground">
                      No per-command optimization events were persisted for this run.
                    </p>
                  )}
                  <p className="mt-2 text-[11px] leading-5 text-muted-foreground">
                    Builder logs analysis reports OTEL reachable, with hook/tool span timeline not yet captured in builder-local events.
                  </p>
                </div>
              </div>
            </section>
          ) : null}

          {stage === "build" ? (
            <section>
              <SectionLabel>Build and acceptance evidence</SectionLabel>
              {buildRuns.length > 0 ? (
                <div className="mt-3 space-y-2">
                  {buildRuns.map(({ task, run }) => (
                    <RunEvidenceCard key={`${task.id}-${run.id}`} task={task} run={run} />
                  ))}
                </div>
              ) : (
                <p className="mt-3 rounded-xl border border-border/65 px-3 py-3 text-[12px] leading-6 text-muted-foreground">
                  No build-verifier or feature-acceptance evidence has been recorded for this sprint yet.
                </p>
              )}
              {verificationSplit.history.length > 0 ? (
                <p className="mt-3 rounded-xl border border-border/65 bg-muted/24 px-3 py-3 text-[12px] leading-6 text-muted-foreground">
                  Repair history: {verificationSplit.history.length} earlier verifier/acceptance run{verificationSplit.history.length === 1 ? "" : "s"} were superseded by the current evidence{failedRepairRuns > 0 ? `, including ${failedRepairRuns} resolved failed check${failedRepairRuns === 1 ? "" : "s"}` : ""}.
                </p>
              ) : null}
            </section>
          ) : null}

          {stage === "implementation" ? (
            <section>
              <SectionLabel>Implementation tasks</SectionLabel>
              <div className="mt-3 space-y-2">
                {implementationTasks.length > 0 ? (
                  implementationTasks.map((task) => {
                    const run = latestStageRun(task, IMPLEMENTATION_AGENT_NAMES);
                    return (
                      <div key={task.id} className="rounded-xl border border-border/65 px-3 py-3">
                        <div className="flex items-center justify-between gap-3">
                          <span className="min-w-0 truncate text-[13px] font-medium text-foreground">
                            {task.title}
                          </span>
                          <span className="shrink-0 font-mono text-[10.5px] uppercase tracking-[0.12em] text-muted-foreground">
                            {task.status}
                          </span>
                        </div>
                        <div className="mt-2 font-mono text-[11px] text-muted-foreground">
                          {run?.agent_name || "code-gen"} · {run?.runtime_sdk || task.runtime_sdk || currentSprint?.runtime_sdk || "runtime selected"}
                          {run?.duration_ms ? ` · ${formatDuration(run.duration_ms)}` : ""}
                        </div>
                      </div>
                    );
                  })
                ) : (
                  <p className="rounded-xl border border-border/65 px-3 py-3 text-[12px] leading-6 text-muted-foreground">
                    No implementation task evidence has been recorded for this sprint yet.
                  </p>
                )}
              </div>
            </section>
          ) : null}

          {stage === "shipped" ? (
            <section>
              <SectionLabel>Shipping outcome</SectionLabel>
              <div className="mt-3 rounded-xl border border-border/65 px-3">
                <DetailRow label="Shipped tasks" value={`${implementationTasks.filter((task) => task.status === "done").length}`} />
                <DetailRow label="Verification" value={currentSprint?.verification_status ?? "pending"} />
                <DetailRow label="Blocked tasks" value={`${implementationTasks.filter((task) => task.status === "blocked" || task.status === "failed").length}`} />
              </div>
            </section>
          ) : null}

          {(stage === "plan" || stage === "design" || stage === "shipped") && includedItems.length > 0 ? (
            <section>
              <SectionLabel>Included outcomes</SectionLabel>
              <div className="mt-3 space-y-2">
                {includedItems.map((item) => (
                  <div key={item.id} className="rounded-xl border border-border/65 px-3 py-2">
                    <div className="text-[12px] font-medium text-foreground">{item.title}</div>
                    <div className="mt-1 font-mono text-[10.5px] uppercase tracking-[0.12em] text-muted-foreground">
                      {item.status}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          ) : null}

          {stage === "design" && sharedConcerns.length > 0 ? (
            <section>
              <SectionLabel>Shared concerns</SectionLabel>
              <ul className="mt-3 space-y-2">
                {sharedConcerns.map((item) => (
                  <li key={item} className="rounded-xl border border-border/65 px-3 py-2 text-[12px] leading-5 text-muted-foreground">
                    {item}
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          {(stage === "plan" || stage === "design") && (plan?.batches ?? []).length > 0 ? (
            <section>
              <SectionLabel>{stage === "plan" ? "Planned batches" : "Designed batches"}</SectionLabel>
              <div className="mt-3 space-y-2">
                {(plan?.batches ?? []).map((batch) => (
                  <div key={batch.id} className="grid grid-cols-[86px_1fr_auto] items-center gap-3 border-b border-border/55 py-2 text-[12px]">
                    <span className="font-mono text-[11px] text-muted-foreground">{batch.id}</span>
                    <span className="min-w-0 truncate text-foreground">{batch.title}</span>
                    <span className="font-mono text-[11px] text-muted-foreground">
                      {batch.model || plan?.model} / {batch.effort || plan?.effort}
                    </span>
                  </div>
                ))}
              </div>
            </section>
          ) : null}
        </div>
      </aside>
    </div>
  );
}
