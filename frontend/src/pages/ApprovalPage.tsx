import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
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
} from "@/components/workspace";
import { ConfidenceBar, DiffBlock } from "@/components/agent-native";
import { fetchApprovalDetails, openApprovalStream, submitApproval } from "@/lib/api";
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
          <span className="rounded-full border border-status-blocked/30 bg-status-blocked-soft px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.14em] text-status-blocked">
            {gate.error_code}
          </span>
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
        <Badge variant={isAgent ? "outline" : "secondary"} className="text-[10px] uppercase tracking-[0.18em]">
          {entry.author}
        </Badge>
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
    return <ErrorState message={error} onRetry={reload} />;
  }

  if (!data) {
    return <LoadingState label="Loading approval review..." />;
  }

  const gateTone =
    data.gate_status === "approve" || data.gate_status === "approved"
      ? "done"
      : data.gate_status === "pending"
        ? "review"
        : "blocked";

  return (
    <PageFrame variant="review">
      <PageHeader
        eyebrow="Approval surface"
        title={`${data.gate_type.toUpperCase()} review`}
        description="Approval stays a narrow decision surface: first understand the task and phase, then read the thread, inspect gate evidence, and only then take action."
        meta={
          <>
            <StatPill label="Gate" value={data.gate_status} tone={gateTone} />
            <StatPill label="Thread" value={String(data.thread.length)} tone="muted" />
            <StatPill label="Runs" value={String(data.runs.length)} tone="active" />
            <StatPill
              label="Feed"
              value={streamState}
              tone={streamState === "Live" ? "active" : "review"}
            />
          </>
        }
      />

      <div className="space-y-5">
        <SurfacePanel className="space-y-4">
          <SectionLabel>Task framing</SectionLabel>
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
                  {data.gate_results.length} gate{data.gate_results.length === 1 ? "" : "s"}
                </span>
              }
            >
              Quality gates · evidence
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
              Latest-run changes
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
                      ${run.cost_usd.toFixed(4)}
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
                  className="bg-status-active text-white hover:bg-status-active/90"
                >
                  Approve
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => handleSubmit("request_changes")}
                  disabled={submitting}
                >
                  Request changes
                </Button>
                <Button
                  variant="destructive"
                  onClick={() => handleSubmit("reject")}
                  disabled={submitting}
                >
                  Reject
                </Button>
              </div>
            </>
          ) : (
            <div className="flex items-center gap-3 text-sm text-muted-foreground">
              <StatusDot tone={gateTone} />
              Gate already resolved as <span className="font-semibold text-foreground">{data.gate_status}</span>.
            </div>
          )}
        </SurfacePanel>

        <Button variant="ghost" size="sm" onClick={() => navigate("/board")} className="font-mono text-xs">
          &larr; Back to board
        </Button>
      </div>
    </PageFrame>
  );
}
