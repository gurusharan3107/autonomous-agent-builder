import { useEffect, useState, type ReactNode } from "react";
import { ArrowLeft, CheckCircle2, ExternalLink, MessageSquareWarning, XCircle } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";
import { Button, Code } from "@/design-system";
import { Textarea } from "@/components/ui/textarea";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { EditorialContent } from "@/components/EditorialContent";
import {
  ErrorState,
  LoadingState,
  PageFrame,
  PageHeader,
  PhaseStepper,
  SectionLabel,
  StatPill,
  StatusDot,
  StatusPill,
  SurfacePanel,
} from "@/design-system";
import { ConfidenceBar, DiffBlock } from "@/components/agent-native";
import { fetchApprovalDetails, openApprovalStream, submitApproval } from "@/lib/api";
import { runtimeCostDisplay } from "@/lib/runtime-cost";
import type { ApprovalDecision, ApprovalDetails, GateResultItem } from "@/lib/types";

function GateEvidenceView({ gate }: { gate: GateResultItem }) {
  const failed = gate.status === "fail" || gate.status === "error" || gate.status === "timeout";
  const unremediated = failed && !gate.remediation_attempted;
  const hasEvidence = gate.evidence && Object.keys(gate.evidence as object).length > 0;

  return (
    <div
      className={[
        "space-y-3 rounded-[1.1rem] border border-border/70 bg-background/55 px-4 py-3",
        unremediated ? "hatch" : "",
      ].join(" ")}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-[11px] text-foreground/80">{gate.gate_name}</span>
        <StatusPill status={gate.status} />
        <span className="font-mono text-[10.5px] text-muted-foreground">
          {gate.elapsed_ms}ms · {gate.findings_count} findings
        </span>
        {gate.analysis_depth ? (
          <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
            depth · {gate.analysis_depth}
          </span>
        ) : null}
        {gate.error_code ? (
          <Code className="border-status-blocked/30 bg-status-blocked-soft text-[10px] uppercase tracking-[0.14em] text-status-blocked">
            {gate.error_code}
          </Code>
        ) : null}
      </div>
      <div className="flex flex-wrap gap-2 text-[10.5px] font-mono uppercase tracking-[0.16em]">
        <span className="inline-flex items-center gap-1.5 text-muted-foreground">
          <StatusDot tone={gate.remediation_attempted ? "review" : "muted"} className="h-1.5 w-1.5" />
          remediation {gate.remediation_attempted ? "attempted" : "none"}
        </span>
        {gate.remediation_attempted ? (
          <span className="inline-flex items-center gap-1.5 text-muted-foreground">
            <StatusDot
              tone={gate.remediation_succeeded ? "done" : "blocked"}
              className="h-1.5 w-1.5"
            />
            {gate.remediation_succeeded ? "succeeded" : "failed"}
          </span>
        ) : null}
        {gate.timeout ? (
          <span className="inline-flex items-center gap-1.5 text-status-review">
            <StatusDot tone="review" className="h-1.5 w-1.5" />
            timed out
          </span>
        ) : null}
      </div>
      {hasEvidence ? (
        <details className="rounded-[0.7rem] border border-dashed border-border/60 bg-background/60 px-3 py-2">
          <summary className="cursor-pointer font-mono text-[10.5px] uppercase tracking-[0.16em] text-muted-foreground">
            Evidence payload
          </summary>
          <pre className="mt-2 max-h-[280px] overflow-auto whitespace-pre-wrap break-words font-mono text-[11px] leading-5 text-foreground/80">
            {JSON.stringify(gate.evidence, null, 2)}
          </pre>
        </details>
      ) : null}
    </div>
  );
}

function ApprovalFallbackFrame({
  children,
  streamState,
}: {
  children: ReactNode;
  streamState: "Connecting" | "Live" | "Reconnecting";
}) {
  const navigate = useNavigate();

  return (
    <PageFrame variant="review" data-screen-label="Approval">
      <PageHeader
        eyebrow="Decision needed"
        title="Review the proposed work"
        description="Read the available evidence, then choose the next action when a live decision is available."
        meta={
          <>
            <StatPill label="Decision" value="pending" tone="review" />
            <StatPill
              label="Feed"
              value={streamState}
              tone={streamState === "Live" ? "active" : "review"}
            />
          </>
        }
      />

      <SurfacePanel className="space-y-4">
        {children}
        <Button variant="ghost" size="sm" onClick={() => navigate("/board")} className="font-mono text-xs">
          <ArrowLeft className="h-3.5 w-3.5" />
          Back to board
        </Button>
      </SurfacePanel>
    </PageFrame>
  );
}

function ThreadEntry({ entry }: { entry: ApprovalDetails["thread"][number] }) {
  const isAgent = entry.role === "agent";

  return (
    <div
      className={[
        "rounded-[1.45rem] border px-4 py-4",
        isAgent
          ? "border-border/75 bg-background/72"
          : "border-status-pending/25 bg-status-pending/6",
      ].join(" ")}
    >
      <div className="mb-3 flex items-center gap-2">
        <StatusDot tone={isAgent ? "active" : "pending"} />
        <Code className="text-[10px] uppercase tracking-[0.18em]">
          {entry.author}
        </Code>
        <span className="text-[10px] font-mono uppercase tracking-[0.18em] text-muted-foreground">
          {new Date(entry.timestamp).toLocaleString()}
        </span>
      </div>
      <EditorialContent content={entry.content} className="text-sm" />
    </div>
  );
}

export default function ApprovalPage() {
  const { gateId } = useParams<{ gateId: string }>();
  const navigate = useNavigate();
  const [data, setData] = useState<ApprovalDetails | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [comment, setComment] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [streamState, setStreamState] = useState<"Connecting" | "Live" | "Reconnecting">("Connecting");
  const [streamKey, setStreamKey] = useState(0);

  useEffect(() => {
    if (!gateId) return;

    let active = true;
    let receivedSnapshot = false;

    const loadFallback = () =>
      fetchApprovalDetails(gateId)
        .then((payload) => {
          receivedSnapshot = true;
          setData(payload);
          setError(null);
          setStreamState("Live");
        })
        .catch((e) => setError(e.message));

    setStreamState("Connecting");
    const stream = openApprovalStream(gateId, (payload) => {
      if (!active) return;
      receivedSnapshot = true;
      setData(payload);
      setError(null);
      setStreamState("Live");
    });

    stream.onerror = () => {
      if (!active) return;
      setStreamState(receivedSnapshot ? "Reconnecting" : "Connecting");
      if (!receivedSnapshot) {
        loadFallback();
      }
    };

    return () => {
      active = false;
      stream.close();
    };
  }, [gateId, streamKey]);

  const reload = async () => {
    setError(null);
    setData(null);
    setStreamKey((value) => value + 1);
  };

  const handleSubmit = async (decision: ApprovalDecision) => {
    if (!gateId) return;
    setSubmitting(true);

    try {
      await submitApproval(gateId, {
        approver_email: "developer@accenture.com",
        decision,
        comment,
        reason: comment,
      });

      setComment("");
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to submit");
    } finally {
      setSubmitting(false);
    }
  };

  if (error) {
    return (
      <ApprovalFallbackFrame streamState={streamState}>
        <ErrorState message={error} onRetry={reload} />
      </ApprovalFallbackFrame>
    );
  }

  if (!data) {
    return (
      <ApprovalFallbackFrame streamState={streamState}>
        <LoadingState label="Loading approval review..." />
      </ApprovalFallbackFrame>
    );
  }

  const gateTone =
    data.gate_status === "approve" || data.gate_status === "approved"
      ? "done"
      : data.gate_status === "pending"
        ? "review"
        : "blocked";

  return (
    <PageFrame variant="review" data-screen-label="Approval">
      <PageHeader
        eyebrow="Decision needed"
        title="Review the proposed work"
        description="Read the work summary, review the evidence, and choose whether Builder should continue, revise, or stop."
        meta={
          <>
            <StatPill label="Decision" value={data.gate_status} tone={gateTone} />
            <StatPill label="Messages" value={String(data.thread.length)} tone="muted" />
            <StatPill label="Work records" value={String(data.runs.length)} tone="active" />
            <StatPill
              label="Feed"
              value={streamState}
              tone={streamState === "Live" ? "active" : "review"}
            />
          </>
        }
      />

      <div className="space-y-5">
        {data.gate_type === "sprint_pr" ? (
          <SurfacePanel className="space-y-3 border-accent/30 bg-accent/10">
            <SectionLabel>Work review</SectionLabel>
            <div className="space-y-2">
              <h2 className="text-xl font-semibold tracking-tight text-foreground">
                {data.sprint_label || data.task_title || "Proposed work"}
              </h2>
              <p className="text-sm leading-6 text-muted-foreground">
                {data.project_name}
              </p>
            </div>
            {data.sprint_pr_url ? (
              <Button asChild variant="secondary" size="sm" className="w-fit">
                <a href={data.sprint_pr_url} target="_blank" rel="noreferrer">
                  <ExternalLink className="h-3.5 w-3.5" />
                  Open pull request
                </a>
              </Button>
            ) : null}
            {data.sprint_changes_summary ? (
              <pre className="whitespace-pre-wrap rounded-[1.1rem] border border-border/70 bg-background/85 p-3 text-[12px] leading-6 text-foreground/80">
                {data.sprint_changes_summary}
              </pre>
            ) : null}
          </SurfacePanel>
        ) : (
          <SurfacePanel className="space-y-4">
            <SectionLabel>Work summary</SectionLabel>
            <div className="space-y-2">
              <h2 className="text-xl font-semibold tracking-tight text-foreground">
                {data.task_title}
              </h2>
              <p className="text-sm leading-6 text-muted-foreground">
                {data.feature_title} · {data.project_name}
              </p>
            </div>
            <PhaseStepper status={data.task_status} />
          </SurfacePanel>
        )}

        <SurfacePanel className="space-y-4">
          <SectionLabel
            trailing={
              <span className="text-[10px] font-mono uppercase tracking-[0.18em] text-muted-foreground">
                {data.thread.length} entr{data.thread.length === 1 ? "y" : "ies"}
              </span>
            }
          >
            Conversation and review thread
          </SectionLabel>

          {data.thread.length > 0 ? (
            <div className="space-y-3">
              {data.thread.map((entry, index) => (
                <ThreadEntry key={`${entry.timestamp}-${index}`} entry={entry} />
              ))}
            </div>
          ) : (
            <div className="rounded-[1.4rem] border border-dashed border-border bg-muted/18 px-4 py-6 text-sm text-muted-foreground">
              No activity yet.
            </div>
          )}
        </SurfacePanel>

        {data.gate_results.length > 0 ? (
          <SurfacePanel className="space-y-3">
            <SectionLabel
              trailing={
                <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                  {data.gate_results.length} check{data.gate_results.length === 1 ? "" : "s"}
                </span>
              }
            >
              Quality checks
            </SectionLabel>
            <div className="space-y-2">
              {data.gate_results.map((gate) => (
                <GateEvidenceView key={gate.id} gate={gate} />
              ))}
            </div>
          </SurfacePanel>
        ) : null}

        {data.runs.length > 0 && data.runs[0].diff_summary ? (
          <SurfacePanel className="space-y-3">
            <SectionLabel
              trailing={<ConfidenceBar value={data.runs[0].confidence ?? null} />}
            >
              Latest changes
            </SectionLabel>
            <DiffBlock diff={data.runs[0].diff_summary} />
          </SurfacePanel>
        ) : null}

        {data.runs.length > 0 ? (
          <SurfacePanel className="space-y-4">
            <SectionLabel>Agent runs</SectionLabel>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-[10px] uppercase tracking-[0.18em]">Agent</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-[0.18em]">Cost</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-[0.18em]">Runtime</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-[0.18em]">Tokens</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-[0.18em]">Turns</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-[0.18em]">Duration</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.runs.map((run) => (
                  <TableRow key={run.id}>
                    <TableCell className="font-mono text-[11px]">{run.agent_name}</TableCell>
                    <TableCell className="font-mono text-[11px] tabular-nums">
                      {runtimeCostDisplay(run.cost_usd, run.runtime_sdk, run.provider, run.observability)}
                    </TableCell>
                    <TableCell className="font-mono text-[11px] tabular-nums">
                      {run.runtime_sdk || "-"}
                    </TableCell>
                    <TableCell className="font-mono text-[11px] tabular-nums">
                      {(run.tokens_input + run.tokens_output).toLocaleString()}
                    </TableCell>
                    <TableCell className="font-mono text-[11px] tabular-nums">{run.num_turns}</TableCell>
                    <TableCell className="font-mono text-[11px] tabular-nums">
                      {(run.duration_ms / 1000).toFixed(1)}s
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </SurfacePanel>
        ) : null}

        <SurfacePanel className={data.gate_status === "pending" ? "space-y-4 border-status-review/30 bg-status-review/6" : "space-y-4"}>
          <SectionLabel>Decision</SectionLabel>
          {data.gate_status === "pending" ? (
            <>
              <Textarea
                id="approval-comment"
                name="approval_comment"
                placeholder="Add review feedback or decision notes..."
                value={comment}
                onChange={(event) => setComment(event.target.value)}
                rows={4}
                className="rounded-[1.4rem] border-border/80 bg-background/70"
              />
              <div className="flex flex-wrap gap-3">
                <Button
                  onClick={() => handleSubmit("approve")}
                  disabled={submitting}
                >
                  <CheckCircle2 className="h-4 w-4" />
                  Approve
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => handleSubmit("request_changes")}
                  disabled={submitting}
                >
                  <MessageSquareWarning className="h-4 w-4" />
                  Request changes
                </Button>
                <Button
                  variant="danger"
                  onClick={() => handleSubmit("reject")}
                  disabled={submitting}
                >
                  <XCircle className="h-4 w-4" />
                  Reject
                </Button>
              </div>
            </>
          ) : (
            <div className="flex items-center gap-3 text-sm text-muted-foreground">
              <StatusDot tone={gateTone} />
              Decision already resolved as <span className="font-semibold text-foreground">{data.gate_status}</span>.
            </div>
          )}
        </SurfacePanel>

        <Button variant="ghost" size="sm" onClick={() => navigate("/board")} className="font-mono text-xs">
          <ArrowLeft className="h-3.5 w-3.5" />
          Back to board
        </Button>
      </div>
    </PageFrame>
  );
}
