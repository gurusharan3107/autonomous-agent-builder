import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Separator } from "@/components/ui/separator";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { fetchApprovalDetails, submitApproval } from "@/lib/api";
import type { ApprovalDetails, ApprovalDecision } from "@/lib/types";

const PHASES = ["Plan", "Design", "Implement", "Gates", "PR", "Build", "Done"];
const STATUS_TO_STEP: Record<string, number> = {
  planning: 0, design_review: 0, design: 1, implementation: 2,
  quality_gates: 3, pr_creation: 4, review_pending: 4, build_verify: 5, done: 6,
};

const GATE_STATUS_COLOR: Record<string, string> = {
  pass: "bg-status-done",
  fail: "bg-status-blocked",
  warn: "bg-status-review",
  timeout: "bg-status-review",
  error: "bg-status-blocked",
  pending: "bg-status-pending",
};

function PhaseStepper({ status }: { status: string }) {
  const current = STATUS_TO_STEP[status] ?? 0;
  return (
    <div className="flex items-center gap-0 overflow-x-auto">
      {PHASES.map((step, i) => (
        <div key={step} className="flex items-center">
          <div className="flex items-center gap-1.5 px-2.5 py-1.5">
            <div className="relative">
              <div
                className={`h-2.5 w-2.5 rounded-full transition-all duration-300 ${
                  i < current
                    ? "bg-status-active"
                    : i === current
                    ? "bg-status-active ring-[3px] ring-status-active/25"
                    : "bg-muted-foreground/20"
                }`}
              />
              {i === current && (
                <div className="absolute inset-0 h-2.5 w-2.5 rounded-full bg-status-active animate-ping opacity-40" />
              )}
            </div>
            <span
              className={`text-[10px] font-semibold uppercase tracking-wider whitespace-nowrap ${
                i < current
                  ? "text-status-active"
                  : i === current
                  ? "text-foreground"
                  : "text-muted-foreground/50"
              }`}
            >
              {step}
            </span>
          </div>
          {i < PHASES.length - 1 && (
            <div
              className={`h-px w-5 transition-colors duration-300 ${
                i < current ? "bg-status-active" : "bg-border"
              }`}
            />
          )}
        </div>
      ))}
    </div>
  );
}

function ThreadEntry({ entry }: { entry: ApprovalDetails["thread"][number] }) {
  const isAgent = entry.role === "agent";
  return (
    <div
      className={`rounded-lg p-3.5 space-y-1.5 border ${
        isAgent
          ? "bg-muted/30 border-border/50"
          : "bg-status-pending/5 border-status-pending/20"
      }`}
    >
      <div className="flex items-center gap-2">
        <div className={`h-1.5 w-1.5 rounded-full ${isAgent ? "bg-primary" : "bg-status-pending"}`} />
        <Badge variant={isAgent ? "default" : "secondary"} className="text-[10px] font-mono">
          {entry.author}
        </Badge>
        <span className="text-[10px] text-muted-foreground font-mono tabular-nums">
          {new Date(entry.timestamp).toLocaleString()}
        </span>
      </div>
      <p className="text-sm whitespace-pre-wrap leading-relaxed pl-3.5">{entry.content}</p>
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

  useEffect(() => {
    if (!gateId) return;
    const load = () =>
      fetchApprovalDetails(gateId)
        .then(setData)
        .catch((e) => setError(e.message));
    load();
    const interval = setInterval(load, 3000);
    return () => clearInterval(interval);
  }, [gateId]);

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
      const updated = await fetchApprovalDetails(gateId);
      setData(updated);
      setComment("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to submit");
    } finally {
      setSubmitting(false);
    }
  };

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
        <p className="text-sm text-muted-foreground">Loading...</p>
      </div>
    );
  }

  const gateStatusColor =
    data.gate_status === "pending"
      ? "bg-status-review text-foreground"
      : data.gate_status === "approved"
      ? "bg-status-done/15 text-status-done border border-status-done/30"
      : "bg-status-blocked/15 text-status-blocked border border-status-blocked/30";

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      {/* Header */}
      <div>
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2.5">
              <h1 className="text-2xl font-bold tracking-tight">
                {data.gate_type.toUpperCase()} Review
              </h1>
              <span className={`inline-flex items-center rounded-md px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${gateStatusColor}`}>
                {data.gate_status}
              </span>
            </div>
            <p className="text-[11px] text-muted-foreground mt-1.5 font-mono">
              {data.task_title} &middot; {data.feature_title} &middot; {data.project_name}
            </p>
          </div>
        </div>
      </div>

      <Separator />

      {/* Phase Stepper */}
      <Card>
        <CardContent className="py-3.5">
          <PhaseStepper status={data.task_status} />
        </CardContent>
      </Card>

      {/* Chat Thread */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-semibold uppercase tracking-wider">Activity</CardTitle>
            <span className="text-[10px] text-muted-foreground font-mono">
              {data.thread.length} entr{data.thread.length === 1 ? "y" : "ies"}
            </span>
          </div>
        </CardHeader>
        <CardContent className="space-y-2.5 max-h-96 overflow-y-auto">
          {data.thread.length > 0 ? (
            data.thread.map((entry, i) => (
              <ThreadEntry key={i} entry={entry} />
            ))
          ) : (
            <div className="py-8 text-center text-sm text-muted-foreground rounded-lg bg-muted/30">
              No activity yet
            </div>
          )}
        </CardContent>
      </Card>

      {/* Gate Results */}
      {data.gate_results.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-semibold uppercase tracking-wider">Quality Gates</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-[10px] uppercase tracking-wider">Gate</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider">Status</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider">Findings</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider">Time</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.gate_results.map((g) => (
                  <TableRow key={g.id}>
                    <TableCell className="text-[11px] font-medium">{g.gate_name}</TableCell>
                    <TableCell>
                      <span className="inline-flex items-center gap-1.5">
                        <span className={`h-1.5 w-1.5 rounded-full ${GATE_STATUS_COLOR[g.status] ?? "bg-muted-foreground"}`} />
                        <span className="text-[10px] font-mono uppercase tracking-wider">{g.status}</span>
                      </span>
                    </TableCell>
                    <TableCell className="font-mono text-[11px] tabular-nums">{g.findings_count}</TableCell>
                    <TableCell className="font-mono text-[11px] tabular-nums">{g.elapsed_ms}ms</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {/* Agent Runs */}
      {data.runs.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-semibold uppercase tracking-wider">Agent Runs</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-[10px] uppercase tracking-wider">Agent</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider">Cost</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider">Tokens</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider">Turns</TableHead>
                  <TableHead className="text-[10px] uppercase tracking-wider">Duration</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.runs.map((r) => (
                  <TableRow key={r.id}>
                    <TableCell>
                      <Badge variant="outline" className="text-[10px] font-mono">{r.agent_name}</Badge>
                    </TableCell>
                    <TableCell className="font-mono text-[11px] tabular-nums">${r.cost_usd.toFixed(4)}</TableCell>
                    <TableCell className="font-mono text-[11px] tabular-nums">
                      {(r.tokens_input + r.tokens_output).toLocaleString()}
                    </TableCell>
                    <TableCell className="font-mono text-[11px] tabular-nums">{r.num_turns}</TableCell>
                    <TableCell className="font-mono text-[11px] tabular-nums">{(r.duration_ms / 1000).toFixed(1)}s</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {/* Actions */}
      {data.gate_status === "pending" ? (
        <Card className="border-status-review/30 bg-status-review/5">
          <CardContent className="pt-6 space-y-4">
            <Textarea
              placeholder="Add comment or feedback..."
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              rows={3}
              className="bg-background"
            />
            <div className="flex gap-3">
              <Button
                onClick={() => handleSubmit("approve")}
                disabled={submitting}
                className="flex-1 bg-status-active hover:bg-status-active/90 text-white"
              >
                Approve
              </Button>
              <Button
                variant="secondary"
                onClick={() => handleSubmit("request_changes")}
                disabled={submitting}
              >
                Request Changes
              </Button>
              <Button
                variant="destructive"
                onClick={() => handleSubmit("reject")}
                disabled={submitting}
              >
                Reject
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : (
        <Card className="border-status-done/20">
          <CardContent className="py-6 text-center">
            <div className="flex items-center justify-center gap-2">
              <div className={`h-2 w-2 rounded-full ${data.gate_status === "approved" ? "bg-status-done" : "bg-status-blocked"}`} />
              <p className="text-sm font-semibold uppercase tracking-wider">
                Gate {data.gate_status}
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      <Button variant="ghost" size="sm" onClick={() => navigate("/")} className="font-mono text-xs">
        &larr; Back to Board
      </Button>
    </div>
  );
}
