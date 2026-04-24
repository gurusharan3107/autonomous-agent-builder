import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { CornerDownLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { EditorialContent } from "@/components/EditorialContent";
import {
  EmptyState,
  LoadingState,
  PageFrame,
  SectionLabel,
  StatPill,
  SurfacePanel,
  Tabs,
  WorkspaceLane,
} from "@/components/workspace";
import {
  AgentTimeline,
  CostMeter,
  LivePulse,
  LogBlock,
  MCPChips,
  ProgressMeter,
  TodoStrip,
  type TimelineEntry,
  type TimelineLogItem,
} from "@/components/agent-native";
import { fetchShellSummary } from "@/lib/api";
import type { ShellSummary, TodoSnapshot } from "@/lib/types";
import { useAgentPageAnimations } from "@/hooks/use-agent-page-animations";
import { useRuntimePreferences } from "@/hooks/use-runtime-preferences";

interface AgentStatus {
  running: boolean;
  current_turn?: number;
  max_turns?: number;
  tokens_used?: number;
  cost_usd?: number;
  error?: string;
}

interface TimelineItem {
  id: string;
  type: string;
  status: string;
  timestamp: string;
  payload: Record<string, unknown>;
}

interface DiagnosticSummary {
  kind?: string;
  outcome?: string;
  tool_name?: string;
  input_focus?: string;
  summary?: string;
  detail?: string;
  error_message?: string;
  next_action?: string;
  raw_response?: string;
}

interface HistoryResponse {
  session_id?: string;
  model?: string;
  repo_identity: string;
  workspace_cwd: string;
  items: TimelineItem[];
  status?: AgentStatus | null;
}

interface ChatResponse {
  response: string;
  session_id?: string;
  model?: string;
  status?: AgentStatus;
}

interface ChatRespondResponse {
  ok: boolean;
  session_id: string;
  event_id: string;
}

interface SessionListItem {
  id: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  preview: string;
  workspace_cwd?: string | null;
  is_resume_candidate: boolean;
}

interface SessionListResponse {
  repo_identity: string;
  workspace_cwd: string;
  latest_resume_session_id?: string | null;
  sessions: SessionListItem[];
}

interface ChatMetaResponse {
  model: string;
  repo_identity: string;
  workspace_cwd: string;
}

interface QuestionDraft {
  selected: string[];
  customText: string;
}

interface ApprovalDraft {
  reason: string;
}

type TranscriptFilter = "thread" | "full" | "logs";
type AgentInspector = "evidence" | "sessions";

function formatTime(timestamp: string) {
  return new Date(timestamp).toLocaleTimeString();
}

function formatStructuredValue(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (!trimmed) return "";
    if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
      try {
        return JSON.stringify(JSON.parse(trimmed), null, 2);
      } catch {
        return trimmed;
      }
    }
    return trimmed;
  }

  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function truncateText(value: string, limit = 280): string {
  if (value.length <= limit) return value;
  return `${value.slice(0, limit - 3)}...`;
}

function diagnosticForItem(item: TimelineItem): DiagnosticSummary {
  const diagnostic = item.payload.diagnostic;
  if (diagnostic && typeof diagnostic === "object") {
    return diagnostic as DiagnosticSummary;
  }

  if (item.type === "specialist_status") {
    return {
      kind: "specialist_status",
      outcome: String(item.payload.phase ?? "running"),
      summary: `Documentation agent: ${String(item.payload.phase ?? "running")}`,
      detail: String(item.payload.content ?? ""),
      raw_response: String(item.payload.content ?? ""),
    };
  }

  if (item.type === "todo_snapshot") {
    const inProgress = Number(item.payload.in_progress_count ?? 0);
    const pending = Number(item.payload.pending_count ?? 0);
    const completed = Number(item.payload.completed_count ?? 0);
    return {
      kind: "todo_snapshot",
      outcome: "progress",
      summary: `Todos updated: ${inProgress} in progress, ${pending} pending, ${completed} completed`,
      detail: formatStructuredValue(item.payload.todos),
      raw_response: formatStructuredValue(item.payload.todos),
    };
  }

  const content = formatStructuredValue(item.payload.content);
  return {
    kind: item.type,
    outcome: item.type === "tool_error" ? "error" : "ok",
    tool_name: String(item.payload.tool_name ?? ""),
    input_focus: formatStructuredValue(item.payload.tool_input),
    summary: String(item.payload.tool_name ?? item.type),
    detail: truncateText(content.replace(/\s+/g, " ").trim(), 220),
    raw_response: content,
  };
}

function upsertTimelineItem(items: TimelineItem[], nextItem: TimelineItem): TimelineItem[] {
  const existingIndex = items.findIndex((item) => item.id === nextItem.id);
  const nextItems = existingIndex >= 0 ? [...items] : [...items, nextItem];
  if (existingIndex >= 0) {
    nextItems[existingIndex] = nextItem;
  }
  nextItems.sort(
    (left, right) => new Date(left.timestamp).getTime() - new Date(right.timestamp).getTime(),
  );
  return nextItems;
}

async function getResponseError(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: string };
    if (payload.detail) return payload.detail;
  } catch {
    // Ignore JSON parse failures and fall back to status text.
  }

  return response.statusText || `Request failed with status ${response.status}`;
}

export default function AgentPage() {
  const [searchParams] = useSearchParams();
  const { preferences, updatePreferences } = useRuntimePreferences();
  const [items, setItems] = useState<TimelineItem[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [modelName, setModelName] = useState<string | null>(null);
  const [repoIdentity, setRepoIdentity] = useState<string | null>(null);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const [sessionList, setSessionList] = useState<SessionListItem[]>([]);
  const [latestResumeSessionId, setLatestResumeSessionId] = useState<string | null>(null);
  const [sessionListLoaded, setSessionListLoaded] = useState(false);
  const [streamingText, setStreamingText] = useState("");
  const [questionDrafts, setQuestionDrafts] = useState<Record<string, QuestionDraft>>({});
  const [approvalDrafts, setApprovalDrafts] = useState<Record<string, ApprovalDraft>>({});
  const [submittingEventId, setSubmittingEventId] = useState<string | null>(null);
  const [transcriptFilter, setTranscriptFilter] = useState<TranscriptFilter>(preferences.transcriptFilterDefault);
  const [activeInspector, setActiveInspector] = useState<AgentInspector>(preferences.agentInspectorDefault);
  const [shellSummary, setShellSummary] = useState<ShellSummary | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const transcriptScrollRef = useRef<HTMLDivElement>(null);
  const pageRef = useAgentPageAnimations(activeInspector);
  const sessionStorageKey = useMemo(
    () => (repoIdentity ? `aab:chat_session_id:${repoIdentity}` : null),
    [repoIdentity],
  );

  const readStoredSessionId = () => {
    if (!sessionStorageKey) return null;
    return localStorage.getItem(sessionStorageKey);
  };

  const writeStoredSessionId = (nextSessionId: string | null) => {
    if (!sessionStorageKey) return;
    if (nextSessionId) {
      localStorage.setItem(sessionStorageKey, nextSessionId);
      return;
    }
    localStorage.removeItem(sessionStorageKey);
  };

  useEffect(() => {
    const transcriptScroller = transcriptScrollRef.current;
    if (!transcriptScroller) return;
    transcriptScroller.scrollTo({
      top: transcriptScroller.scrollHeight,
      behavior: "smooth",
    });
  }, [items, streamingText]);

  useEffect(() => {
    setTranscriptFilter(preferences.transcriptFilterDefault);
  }, [preferences.transcriptFilterDefault]);

  useEffect(() => {
    setActiveInspector(preferences.agentInspectorDefault);
  }, [preferences.agentInspectorDefault]);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const summary = await fetchShellSummary();
        if (!cancelled) setShellSummary(summary);
      } catch (error) {
        console.error("Failed to load shell summary:", error);
      }
    };
    void load();
    const interval = window.setInterval(() => void load(), 10000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    const loadChatMeta = async () => {
      try {
        const response = await fetch("/api/agent/chat/meta");
        if (!response.ok) {
          throw new Error("Failed to load chat metadata");
        }

        const data = (await response.json()) as ChatMetaResponse;
        if (!cancelled) {
          setModelName(data.model);
          setRepoIdentity(data.repo_identity);
        }
      } catch (error) {
        console.error("Failed to load chat metadata:", error);
      }
    };

    void loadChatMeta();

    return () => {
      cancelled = true;
    };
  }, []);

  const loadSessionList = async (preferredSessionId?: string | null) => {
    try {
      const response = await fetch("/api/agent/chat/sessions");
      if (!response.ok) {
        throw new Error("Failed to load sessions");
      }

      const data = (await response.json()) as SessionListResponse;
      setRepoIdentity(data.repo_identity);
      setSessionList(data.sessions);
      setLatestResumeSessionId(data.latest_resume_session_id ?? null);

      if (preferredSessionId) {
        const match = data.sessions.find((session) => session.id === preferredSessionId);
        if (!match) {
          writeStoredSessionId(null);
          setSessionId(null);
        }
      }
    } catch (error) {
      console.error("Failed to load session list:", error);
    } finally {
      setSessionListLoaded(true);
    }
  };

  const loadHistory = async (targetSessionId?: string | null, options?: { fresh?: boolean }) => {
    const selectedSessionId =
      targetSessionId === undefined
        ? searchParams.get("session") || readStoredSessionId()
        : targetSessionId;
    const fresh = Boolean(options?.fresh);

    setHistoryLoaded(false);

    try {
      const url = fresh
        ? "/api/agent/chat/history?fresh=1"
        : selectedSessionId
          ? `/api/agent/chat/history?session_id=${selectedSessionId}`
          : "/api/agent/chat/history";
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error(await getResponseError(response));
      }

      const data = (await response.json()) as HistoryResponse;
      setModelName(data.model ?? null);
      setRepoIdentity(data.repo_identity);
      setSessionId(data.session_id || null);
      setItems(data.items ?? []);
      setStatus(data.status ?? null);
      setStreamingText("");
      setLoading(Boolean(data.status?.running));

      writeStoredSessionId(data.session_id || null);
    } catch (error) {
      if (selectedSessionId && error instanceof Error && error.message.includes("different repo or workspace")) {
        writeStoredSessionId(null);
        await loadHistory(null);
        return;
      }
      console.error("Failed to load chat history:", error);
      setItems([]);
      setStatus(null);
    } finally {
      setHistoryLoaded(true);
    }
  };

  useEffect(() => {
    if (!sessionStorageKey) return;

    const bootstrap = async () => {
      localStorage.removeItem("chat_session_id");
      const storedSessionId = searchParams.get("session") || readStoredSessionId();
      await loadHistory(storedSessionId);
      const activeSessionId = storedSessionId ?? readStoredSessionId();
      await loadSessionList(activeSessionId);
    };

    void bootstrap();
    // Bootstrap intentionally re-runs only when the repo key or search params change.
    // loadHistory/loadSessionList/readStoredSessionId are inline closures that read
    // current state; including them would cascade re-fetches.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams, sessionStorageKey]);

  useEffect(() => {
    if (!sessionId) return;

    const stream = new EventSource(`/api/agent/chat/stream?session_id=${encodeURIComponent(sessionId)}`);

    stream.addEventListener("snapshot", (event) => {
      const message = event as MessageEvent<string>;
      const payload = JSON.parse(message.data) as HistoryResponse;
      setItems(payload.items ?? []);
      setStatus(payload.status ?? null);
      setStreamingText("");
      setLoading(Boolean(payload.status?.running));
    });

    stream.addEventListener("event", (event) => {
      const message = event as MessageEvent<string>;
      const payload = JSON.parse(message.data) as TimelineItem;

      if (payload.type === "assistant_stream_delta") {
        setStreamingText((current) => current + String(payload.payload.content ?? ""));
        setLoading(true);
        return;
      }

      if (payload.type === "run_status") {
        const nextStatus = payload.payload as unknown as AgentStatus;
        setStatus(nextStatus);
        setLoading(Boolean(nextStatus.running));
        return;
      }

      setItems((current) => upsertTimelineItem(current, payload));
      if (
        payload.type === "assistant_message" ||
        payload.type === "run_error" ||
        payload.type === "ask_user_question" ||
        payload.type === "tool_approval_request"
      ) {
        setStreamingText("");
        if (payload.type !== "assistant_message") {
          setLoading(false);
        }
      }
      void loadSessionList(sessionId);
    });

    stream.onerror = () => {
      stream.close();
    };

    return () => {
      stream.close();
    };
    // Stream is keyed to sessionId only; loadSessionList is an inline closure
    // that reads current state, by design.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  const pendingBlockingItem = useMemo(
    () =>
      [...items]
        .reverse()
        .find(
          (item) =>
            (item.type === "ask_user_question" || item.type === "tool_approval_request") &&
            !item.payload.answered,
        ) ?? null,
    [items],
  );

  const sendMessage = async () => {
    if (!input.trim() || loading || pendingBlockingItem) return;

    const prompt = input.trim();
    setInput("");
    setLoading(true);

    try {
      const response = await fetch("/api/agent/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: prompt,
          session_id: sessionId,
        }),
      });

      if (!response.ok) {
        throw new Error(await getResponseError(response));
      }

      const data = (await response.json()) as ChatResponse;
      if (data.session_id) {
        setSessionId(data.session_id);
        writeStoredSessionId(data.session_id);
        await loadHistory(data.session_id);
        void loadSessionList(data.session_id);
      }

      if (data.model) {
        setModelName(data.model);
      }

      if (data.status) {
        setStatus(data.status);
      }
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : "Unknown error";
      setItems((current) =>
        upsertTimelineItem(current, {
          id: `local-error-${Date.now()}`,
          type: "run_error",
          status: "completed",
          timestamp: new Date().toISOString(),
          payload: { content: `Error: ${message}` },
        }),
      );
      setLoading(false);
    }
  };

  const submitQuestion = async (item: TimelineItem) => {
    if (!sessionId) return;
    const draft = questionDrafts[item.id] ?? { selected: [], customText: "" };
    const customText = draft.customText.trim();
    const selectedOptions = draft.selected.filter(Boolean);
    if (!customText && selectedOptions.length === 0) return;

    setSubmittingEventId(item.id);
    try {
      const response = await fetch("/api/agent/chat/respond", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          event_id: item.id,
          selected_options: selectedOptions,
          custom_text: customText,
        }),
      });
      if (!response.ok) {
        throw new Error(await getResponseError(response));
      }
      const data = (await response.json()) as ChatRespondResponse;
      if (data.ok) {
        setQuestionDrafts((current) => {
          const next = { ...current };
          delete next[item.id];
          return next;
        });
        setLoading(true);
      }
    } catch (error) {
      console.error("Failed to submit question response:", error);
    } finally {
      setSubmittingEventId(null);
    }
  };

  const submitApproval = async (item: TimelineItem, decision: "allow" | "deny") => {
    if (!sessionId) return;
    const draft = approvalDrafts[item.id] ?? { reason: "" };

    setSubmittingEventId(item.id);
    try {
      const response = await fetch("/api/agent/chat/respond", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          event_id: item.id,
          decision,
          reason: draft.reason,
        }),
      });
      if (!response.ok) {
        throw new Error(await getResponseError(response));
      }
      const data = (await response.json()) as ChatRespondResponse;
      if (data.ok) {
        setApprovalDrafts((current) => {
          const next = { ...current };
          delete next[item.id];
          return next;
        });
        setLoading(true);
      }
    } catch (error) {
      console.error("Failed to submit tool approval response:", error);
    } finally {
      setSubmittingEventId(null);
    }
  };

  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void sendMessage();
    }
  };

  const clearSession = () => {
    writeStoredSessionId(null);
    setSessionId(null);
    setItems([]);
    setStatus(null);
    setStreamingText("");
    setInput("");
    setLoading(false);
    setQuestionDrafts({});
    setApprovalDrafts({});
    void (async () => {
      await loadHistory(null, { fresh: true });
      await loadSessionList(null);
    })();
  };

  const openSession = (nextSessionId: string) => {
    void loadHistory(nextSessionId);
  };

  const resumeLatestSession = () => {
    if (!latestResumeSessionId) return;
    openSession(latestResumeSessionId);
  };

  const recentSessions = useMemo(() => {
    if (!sessionId) return sessionList;
    return sessionList.filter((session) => session.id !== sessionId);
  }, [sessionId, sessionList]);

  const assistantMessages = items.filter((item) => item.type === "assistant_message");
  const questionCards = items.filter((item) => item.type === "ask_user_question");
  const approvalCards = items.filter((item) => item.type === "tool_approval_request");
  const builderLogItems = items.filter((item) =>
    item.type === "tool_result" || item.type === "tool_error" || item.type === "todo_snapshot",
  );
  const specialistEvents = items.filter((item) => item.type === "specialist_status");
  const latestSpecialistEvent = specialistEvents.at(-1) ?? null;

  const sessionTodoSnapshot: TodoSnapshot | null = useMemo(() => {
    if (!shellSummary || !sessionId) return null;
    return shellSummary.todo_snapshots.find((snap) => snap.session_id === sessionId) ?? null;
  }, [shellSummary, sessionId]);

  const logBlockItems: TimelineLogItem[] = useMemo(() => {
    return [...specialistEvents, ...builderLogItems]
      .sort(
        (left, right) =>
          new Date(left.timestamp).getTime() - new Date(right.timestamp).getTime(),
      )
      .map((item) => {
        const diagnostic = diagnosticForItem(item);
        const toolName = item.type === "specialist_status"
          ? `documentation-agent/${String(item.payload.phase ?? "running")}`
          : String(diagnostic.tool_name ?? item.payload.tool_name ?? item.type);
        return {
          id: item.id,
          type: item.type,
          timestamp: item.timestamp,
          tool_name: toolName,
          summary: diagnostic.summary ?? "",
          preview: diagnostic.detail ?? "",
        };
      });
  }, [specialistEvents, builderLogItems]);

  const timelineEntries: TimelineEntry[] = useMemo(() => {
    return items.map((item): TimelineEntry => {
      const ts = formatTime(item.timestamp);
      if (item.type === "user_message") {
        return {
          id: item.id,
          kind: "user",
          timestamp: ts,
          body: <span className="whitespace-pre-wrap">{String(item.payload.content ?? "")}</span>,
        };
      }
      if (item.type === "assistant_message") {
        return {
          id: item.id,
          kind: "thinking",
          timestamp: ts,
          label: "assistant",
          body: String(item.payload.content ?? ""),
        };
      }
      if (item.type === "run_error") {
        return {
          id: item.id,
          kind: "gate",
          timestamp: ts,
          label: "run error",
          status: "failed",
          body: <span className="text-status-blocked">{String(item.payload.content ?? "")}</span>,
        };
      }
      if (item.type === "tool_result" || item.type === "tool_error") {
        const diagnostic = diagnosticForItem(item);
        return {
          id: item.id,
          kind: "tool",
          timestamp: ts,
          label: String(diagnostic.tool_name ?? item.payload.tool_name ?? "tool"),
          status: item.type === "tool_error" ? "failed" : undefined,
          args: diagnostic.input_focus ?? "",
          result: (diagnostic.summary ?? diagnostic.detail ?? "").slice(0, 180),
        };
      }
      if (item.type === "specialist_status") {
        return {
          id: item.id,
          kind: "gate",
          timestamp: ts,
          label: String(item.payload.phase ?? "running"),
          status: "review_pending",
          body: String(item.payload.content ?? ""),
        };
      }
      if (item.type === "ask_user_question" || item.type === "tool_approval_request") {
        return {
          id: item.id,
          kind: "gate",
          timestamp: ts,
          label: item.type === "ask_user_question" ? "question" : "approval",
          status: "review_pending",
          body: String(item.payload.summary ?? item.payload.question ?? item.payload.tool_name ?? ""),
        };
      }
      if (item.type === "todo_snapshot") {
        const inProgress = Number(item.payload.in_progress_count ?? 0);
        const pending = Number(item.payload.pending_count ?? 0);
        const completed = Number(item.payload.completed_count ?? 0);
        return {
          id: item.id,
          kind: "tool",
          timestamp: ts,
          label: "todo snapshot",
          result: `${inProgress} active · ${pending} pending · ${completed} done`,
        };
      }
      return {
        id: item.id,
        kind: "tool",
        timestamp: ts,
        label: item.type,
        body: String(item.payload.content ?? ""),
      };
    });
  }, [items]);

  const useTimelineLayout =
    transcriptFilter === "thread" && preferences.transcriptLayout === "timeline";
  const filteredItems = useMemo(() => {
    if (transcriptFilter === "thread") {
      return items.filter((item) =>
        ["user_message", "assistant_message", "run_error", "ask_user_question", "tool_approval_request"].includes(
          item.type,
        ),
      );
    }
    if (transcriptFilter === "logs") {
      return items.filter((item) =>
        ["specialist_status", "tool_result", "tool_error", "todo_snapshot"].includes(item.type),
      );
    }
    return items;
  }, [items, transcriptFilter]);
  const currentRunPanel = (
    <SurfacePanel data-agent-stage="card" className="space-y-3">
      <SectionLabel>Current run</SectionLabel>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
        <MetricRow label="State" value={status?.running ? "Running" : "Ready"} />
        <MetricRow
          label="Cost"
          value={status?.cost_usd != null ? `$${status.cost_usd.toFixed(4)}` : "$0.0000"}
        />
        <MetricRow
          label="Tokens"
          value={status?.tokens_used != null ? status.tokens_used.toLocaleString() : "0"}
        />
        <MetricRow
          label="Turns"
          value={`${status?.current_turn ?? 0}/${status?.max_turns ?? 0}`}
        />
      </div>
    </SurfacePanel>
  );

  const evidenceInspector = (
    <SurfacePanel data-agent-inspector="true" data-agent-stage="card" className="space-y-3">
      <SectionLabel>Evidence</SectionLabel>
      <div className="grid grid-cols-2 gap-2.5">
        <div className="rounded-[1rem] border border-border/70 bg-background/55 px-3 py-3">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
            Notes
          </p>
          <p className="mt-1 font-mono text-xl text-foreground">{assistantMessages.length}</p>
        </div>
        <div className="rounded-[1rem] border border-border/70 bg-background/55 px-3 py-3">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
            Questions
          </p>
          <p className="mt-1 font-mono text-xl text-foreground">{questionCards.length}</p>
        </div>
        <div className="rounded-[1rem] border border-border/70 bg-background/55 px-3 py-3">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
            Approvals
          </p>
          <p className="mt-1 font-mono text-xl text-foreground">{approvalCards.length}</p>
        </div>
        <div className="rounded-[1rem] border border-border/70 bg-background/55 px-3 py-3">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
            Logs
          </p>
          <p className="mt-1 font-mono text-xl text-foreground">{builderLogItems.length}</p>
        </div>
      </div>
      <div className="rounded-[1rem] border border-border/70 bg-background/55 px-3 py-3 text-sm leading-6 text-muted-foreground">
        {latestSpecialistEvent ? (
          <>
            <span className="font-semibold text-foreground">Documentation agent:</span>{" "}
            {String(latestSpecialistEvent.payload.content ?? "")}
          </>
        ) : (
          "The transcript now persists interactive question and approval cards, not only flat text."
        )}
      </div>
      <div className="rounded-[1rem] border border-border/70 bg-background/55 px-3 py-3">
        <div className="flex items-center justify-between gap-3">
          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
            Builder log timeline
          </p>
          <Badge variant="outline" className="text-[10px] uppercase tracking-[0.18em]">
            {builderLogItems.length} entries
          </Badge>
        </div>

        {builderLogItems.length === 0 && specialistEvents.length === 0 ? (
          <p className="mt-4 text-sm leading-6 text-muted-foreground">
            Tool activity and documentation-agent phases will appear here when the run touches builder KB or other approved tools.
          </p>
        ) : (
          <div className="scroll-panel mt-4 max-h-[34rem] space-y-3 overflow-y-auto pr-1">
            {[...specialistEvents, ...builderLogItems]
              .sort(
                (left, right) =>
                  new Date(right.timestamp).getTime() - new Date(left.timestamp).getTime(),
              )
              .slice(0, 8)
              .map((item) => {
                const isSpecialist = item.type === "specialist_status";
                const diagnostic = diagnosticForItem(item);
                const label = isSpecialist
                  ? `documentation-agent/${String(item.payload.phase ?? "running")}`
                  : String(diagnostic.tool_name ?? item.payload.tool_name ?? "tool");
                const content = isSpecialist
                  ? String(diagnostic.detail ?? item.payload.content ?? "")
                  : truncateText(String(diagnostic.summary ?? diagnostic.detail ?? "No log content captured."), 220);

                return (
                  <div
                    key={item.id}
                    className="rounded-[1.1rem] border border-border/70 bg-background/80 px-3 py-3"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="outline" className="text-[10px] uppercase tracking-[0.18em]">
                        {isSpecialist ? "Doc agent" : item.type === "tool_error" ? "Tool error" : "Builder log"}
                      </Badge>
                      <span className="text-xs font-medium text-foreground">{label}</span>
                      <span className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">
                        {formatTime(item.timestamp)}
                      </span>
                    </div>
                    <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-6 text-muted-foreground">
                      {content || "No log content captured."}
                    </p>
                  </div>
                );
              })}
          </div>
        )}
      </div>
    </SurfacePanel>
  );

  const renderQuestionCard = (item: TimelineItem) => {
    const draft = questionDrafts[item.id] ?? { selected: [], customText: "" };
    const options = Array.isArray(item.payload.options)
      ? (item.payload.options as Array<{ label: string; description: string }>)
      : [];
    const multiSelect = Boolean(item.payload.multi_select);
    const answered = Boolean(item.payload.answered);
    const answerValue = String(item.payload.answer_value ?? "");
    const canSubmit = draft.customText.trim().length > 0 || draft.selected.length > 0;

    return (
      <div
        key={item.id}
        className="rounded-[1.6rem] border border-amber-200/70 bg-amber-50/70 px-4 py-4 text-foreground shadow-[0_12px_30px_-24px_rgba(161,98,7,0.35)]"
      >
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <Badge variant="outline" className="text-[10px] uppercase tracking-[0.18em]">
            {String(item.payload.header ?? "Question")}
          </Badge>
          <Badge variant="secondary" className="text-[10px] uppercase tracking-[0.18em]">
            Agent question
          </Badge>
          <span className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
            {formatTime(item.timestamp)}
          </span>
        </div>
        <p className="text-sm font-medium leading-6 text-foreground">
          {String(item.payload.question ?? "")}
        </p>

        <div className="mt-4 space-y-3">
          {options.map((option, index) => {
            const selected = draft.selected.includes(option.label);
            return (
              <button
                key={`${item.id}-${option.label}`}
                type="button"
                disabled={answered}
                onClick={() => {
                  setQuestionDrafts((current) => {
                    const existing = current[item.id] ?? { selected: [], customText: "" };
                    const nextSelected = multiSelect
                      ? selected
                        ? existing.selected.filter((value) => value !== option.label)
                        : [...existing.selected, option.label]
                      : [option.label];
                    return {
                      ...current,
                      [item.id]: { ...existing, selected: nextSelected, customText: "" },
                    };
                  });
                }}
                className={[
                  "w-full rounded-[1.2rem] border px-4 py-3 text-left transition-colors",
                  selected
                    ? "border-amber-600 bg-amber-100/90"
                    : "border-border/70 bg-background/80 hover:bg-background",
                  answered ? "cursor-default opacity-80" : "",
                ].join(" ")}
              >
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-foreground">{option.label}</span>
                  {index === 0 ? (
                    <Badge variant="secondary" className="text-[10px] uppercase tracking-[0.18em]">
                      Recommended
                    </Badge>
                  ) : null}
                </div>
                <p className="mt-1 text-sm leading-6 text-muted-foreground">{option.description}</p>
              </button>
            );
          })}

          {!answered ? (
            <div className="rounded-[1.2rem] border border-dashed border-border/80 bg-background/60 px-4 py-3">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                Other
              </p>
              <Textarea
                value={draft.customText}
                onChange={(event) =>
                  setQuestionDrafts((current) => ({
                    ...current,
                    [item.id]: {
                      selected: [],
                      customText: event.target.value,
                    },
                  }))
                }
                placeholder="Type a custom answer instead of the options above."
                className="mt-2 min-h-[88px] resize-none border-0 bg-transparent px-0 shadow-none focus-visible:ring-0"
              />
            </div>
          ) : null}
        </div>

        {answered ? (
          <div className="mt-4 rounded-[1.1rem] border border-amber-300/60 bg-background/80 px-3 py-3 text-sm">
            <span className="font-semibold text-foreground">Answer:</span> {answerValue}
          </div>
        ) : (
          <div className="mt-4 flex justify-end">
            <Button
              onClick={() => void submitQuestion(item)}
              disabled={!canSubmit || submittingEventId === item.id}
            >
              Submit answer
            </Button>
          </div>
        )}
      </div>
    );
  };

  const renderApprovalCard = (item: TimelineItem) => {
    const draft = approvalDrafts[item.id] ?? { reason: "" };
    const answered = Boolean(item.payload.answered);
    const decision = String(item.payload.decision ?? "");
    const reason = String(item.payload.reason ?? "");

    return (
      <div
        key={item.id}
        className="rounded-[1.6rem] border border-rose-200/70 bg-rose-50/65 px-4 py-4 text-foreground shadow-[0_12px_30px_-24px_rgba(190,24,93,0.32)]"
      >
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <Badge variant="outline" className="text-[10px] uppercase tracking-[0.18em]">
            Approval
          </Badge>
          <Badge variant="secondary" className="text-[10px] uppercase tracking-[0.18em]">
            {String(item.payload.tool_name ?? "Tool")}
          </Badge>
          <span className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
            {formatTime(item.timestamp)}
          </span>
        </div>
        <p className="text-sm font-semibold leading-6 text-foreground">
          {String(item.payload.summary ?? item.payload.tool_name ?? "Tool request")}
        </p>
        <p className="mt-1 text-sm leading-6 text-muted-foreground">
          {String(item.payload.description ?? "")}
        </p>
        <pre className="mt-4 overflow-x-auto rounded-[1.1rem] border border-border/70 bg-background/85 p-3 text-[12px] leading-6 text-foreground/80">
          {JSON.stringify(item.payload.tool_input ?? {}, null, 2)}
        </pre>

        {answered ? (
          <div className="mt-4 rounded-[1.1rem] border border-rose-300/60 bg-background/80 px-3 py-3 text-sm">
            <span className="font-semibold text-foreground">Decision:</span> {decision || "allow"}
            {reason ? (
              <>
                <span className="mx-2 text-muted-foreground">·</span>
                <span>{reason}</span>
              </>
            ) : null}
          </div>
        ) : (
          <>
            <Textarea
              value={draft.reason}
              onChange={(event) =>
                setApprovalDrafts((current) => ({
                  ...current,
                  [item.id]: { reason: event.target.value },
                }))
              }
              placeholder="Optional reason or guidance for the agent."
              className="mt-4 min-h-[88px] resize-none border border-border/70 bg-background/80 shadow-none focus-visible:ring-0"
            />
            <div className="mt-4 flex justify-end gap-2">
              <Button
                variant="outline"
                onClick={() => void submitApproval(item, "deny")}
                disabled={submittingEventId === item.id}
              >
                Deny
              </Button>
              <Button onClick={() => void submitApproval(item, "allow")} disabled={submittingEventId === item.id}>
                Approve
              </Button>
            </div>
          </>
        )}
      </div>
    );
  };

  const renderSpecialistStatusCard = (item: TimelineItem) => {
    const phase = String(item.payload.phase ?? "running");
    const content = String(item.payload.content ?? "");

    return (
      <div
        key={item.id}
        className="flex justify-start"
      >
        <div className="max-w-[88%] rounded-[1.6rem] border border-sky-200/80 bg-sky-50/80 px-4 py-4 text-foreground shadow-[0_12px_30px_-24px_rgba(2,132,199,0.35)]">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <Badge variant="outline" className="text-[10px] uppercase tracking-[0.18em]">
              Documentation agent
            </Badge>
            <Badge variant="secondary" className="text-[10px] uppercase tracking-[0.18em]">
              {phase}
            </Badge>
            <span className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
              {formatTime(item.timestamp)}
            </span>
          </div>
          <p className="whitespace-pre-wrap text-sm leading-6 text-foreground/85">{content}</p>
        </div>
      </div>
    );
  };

  const renderToolLogCard = (item: TimelineItem) => {
    const diagnostic = diagnosticForItem(item);
    const toolName = String(diagnostic.tool_name ?? item.payload.tool_name ?? "tool");
    const toolInput = formatStructuredValue(item.payload.tool_input);
    const content = String(diagnostic.raw_response ?? formatStructuredValue(item.payload.content));
    const isError = item.type === "tool_error";
    const preview = String(diagnostic.detail ?? truncateText(content.replace(/\s+/g, " ").trim(), 220));

    return (
      <div key={item.id} className="flex justify-start">
        <div
          className={[
            "max-w-[88%] rounded-[1.6rem] border px-4 py-4 text-foreground shadow-[0_12px_30px_-24px_rgba(15,23,42,0.35)]",
            isError ? "border-rose-200/80 bg-rose-50/80" : "border-border/75 bg-slate-50/75",
          ].join(" ")}
        >
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <Badge variant="outline" className="text-[10px] uppercase tracking-[0.18em]">
              {isError ? "Tool error" : "Builder log"}
            </Badge>
            <span className="text-sm font-semibold text-foreground">{toolName}</span>
            {diagnostic.outcome ? (
              <Badge variant="secondary" className="text-[10px] uppercase tracking-[0.18em]">
                {diagnostic.outcome}
              </Badge>
            ) : null}
            <span className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
              {formatTime(item.timestamp)}
            </span>
          </div>

          {diagnostic.summary ? <p className="text-sm font-semibold leading-6 text-foreground">{diagnostic.summary}</p> : null}
          {preview ? <p className="text-sm leading-6 text-muted-foreground">{preview}</p> : null}
          {diagnostic.input_focus ? (
            <div className="mt-3 rounded-[1.1rem] border border-border/60 bg-background/80 px-3 py-3 text-xs leading-6 text-muted-foreground">
              <span className="font-semibold text-foreground">Focus:</span> {diagnostic.input_focus}
            </div>
          ) : null}
          {diagnostic.next_action ? (
            <div className="mt-3 rounded-[1.1rem] border border-dashed border-border/70 bg-background/55 px-3 py-3 text-xs leading-6 text-muted-foreground">
              <span className="font-semibold text-foreground">Next useful step:</span> {diagnostic.next_action}
            </div>
          ) : null}

          {content || toolInput ? (
            <details className="mt-3 rounded-[1.1rem] border border-dashed border-border/70 bg-background/55 px-3 py-3">
              <summary className="cursor-pointer text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                Expand raw log
              </summary>
              {content ? (
                <pre className="mt-3 overflow-x-auto whitespace-pre-wrap break-words rounded-[1rem] border border-border/60 bg-background/80 px-3 py-3 text-xs leading-6 text-muted-foreground">
                  {content}
                </pre>
              ) : null}
              {toolInput ? (
                <div className="mt-3">
                  <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
                    Tool input
                  </p>
                  <pre className="mt-2 overflow-x-auto whitespace-pre-wrap break-words text-xs leading-6 text-muted-foreground">
                    {toolInput}
                  </pre>
                </div>
              ) : null}
            </details>
          ) : null}
        </div>
      </div>
    );
  };

  const transcriptPanel = (
    <SurfacePanel data-agent-stage="section" className="space-y-4 rounded-[1.35rem] px-3.5 py-3.5 sm:px-4 sm:py-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <SectionLabel>Thread</SectionLabel>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            Live transcript and inline decisions stay in the main lane.
          </p>
        </div>
        <Tabs<TranscriptFilter>
          value={transcriptFilter}
          onChange={(next) => {
            setTranscriptFilter(next);
            updatePreferences({ transcriptFilterDefault: next });
          }}
          items={[
            { value: "thread", label: "Thread" },
            { value: "logs", label: "Raw log" },
            { value: "full", label: "Full trace" },
          ]}
        />
      </div>

      {!historyLoaded ? (
        <LoadingState label="Loading agent transcript..." />
      ) : filteredItems.length === 0 && !streamingText ? (
        <EmptyState
          label={transcriptFilter === "logs" ? "No raw builder log yet" : "No active transcript"}
          detail={
            transcriptFilter === "logs"
              ? "Tool results, tool errors, and documentation-agent phases will appear here when a run uses those surfaces."
              : "Start a conversation. Interactive questions and approvals will appear inline in the thread."
          }
        />
      ) : transcriptFilter === "logs" ? (
        <div ref={transcriptScrollRef} className="scroll-panel max-h-[calc(100vh-20rem)] overflow-y-auto pr-1">
          <LogBlock items={logBlockItems} emptyLabel="No log events for this session yet." maxHeight={560} />
        </div>
      ) : useTimelineLayout ? (
        <div ref={transcriptScrollRef} className="scroll-panel max-h-[calc(100vh-20rem)] overflow-y-auto pr-1">
          <AgentTimeline entries={timelineEntries} />
        </div>
      ) : (
        <div
          ref={transcriptScrollRef}
          className="scroll-panel max-h-[calc(100vh-20rem)] space-y-3 overflow-y-auto pr-1"
        >
          {filteredItems.map((item) => {
            if (item.type === "user_message") {
              return (
                <div key={item.id} className="flex justify-end">
                  <div className="max-w-[88%] rounded-[1.6rem] border border-foreground/10 bg-foreground px-4 py-4 text-background">
                    <div className="mb-3 flex items-center gap-2">
                      <Badge variant="secondary" className="text-[10px] uppercase tracking-[0.18em] text-foreground">
                        Operator
                      </Badge>
                      <span className="text-[10px] uppercase tracking-[0.18em] text-background/70">
                        {formatTime(item.timestamp)}
                      </span>
                    </div>
                    <p className="whitespace-pre-wrap text-sm leading-6">
                      {String(item.payload.content ?? "")}
                    </p>
                  </div>
                </div>
              );
            }

            if (item.type === "assistant_message" || item.type === "run_error") {
              return (
                <div key={item.id} className="flex justify-start">
                  <div className="max-w-[88%] rounded-[1.6rem] border border-border/75 bg-background/75 px-4 py-4 text-foreground shadow-[0_12px_30px_-24px_rgba(15,23,42,0.55)]">
                    <div className="mb-3 flex items-center gap-2">
                      <Badge variant="outline" className="text-[10px] uppercase tracking-[0.18em]">
                        {item.type === "run_error" ? "Agent error" : "Agent"}
                      </Badge>
                      <span className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                        {formatTime(item.timestamp)}
                      </span>
                    </div>
                    <EditorialContent
                      content={String(item.payload.content ?? "")}
                      className="text-sm"
                    />
                  </div>
                </div>
              );
            }

            if (item.type === "specialist_status") {
              return renderSpecialistStatusCard(item);
            }

            if (item.type === "tool_result" || item.type === "tool_error" || item.type === "todo_snapshot") {
              return renderToolLogCard(item);
            }

            if (item.type === "ask_user_question") {
              return renderQuestionCard(item);
            }

            if (item.type === "tool_approval_request") {
              return renderApprovalCard(item);
            }

            return null;
          })}

          {streamingText ? (
            <div className="flex justify-start">
              <div className="max-w-[88%] rounded-[1.6rem] border border-border/75 bg-background/75 px-4 py-4 text-foreground shadow-[0_12px_30px_-24px_rgba(15,23,42,0.55)]">
                <div className="mb-3 flex items-center gap-2">
                  <Badge variant="outline" className="text-[10px] uppercase tracking-[0.18em]">
                    Agent
                  </Badge>
                  <span className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                    Streaming
                  </span>
                </div>
                <EditorialContent content={streamingText} className="text-sm" />
              </div>
            </div>
          ) : null}

          {loading && !streamingText ? (
            <div className="flex justify-start">
              <div className="rounded-[1.6rem] border border-border/75 bg-background/75 px-4 py-4">
                <div className="inline-flex gap-1">
                  {[0, 1, 2].map((i) => (
                    <div
                      key={i}
                      className="h-2 w-2 rounded-full bg-muted-foreground/30 animate-pulse"
                      style={{ animationDelay: `${i * 150}ms` }}
                    />
                  ))}
                </div>
              </div>
            </div>
          ) : null}
          <div ref={messagesEndRef} />
        </div>
      )}

      <div className="mt-5 border-t border-border/70 pt-4">
        <div className="rounded-[1.5rem] border border-border/80 bg-background/70 p-3">
          <Textarea
            id="agent-composer"
            name="agent_composer"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              pendingBlockingItem
                ? "Answer the pending card before sending another instruction."
                : "Type the next instruction. Shift+Enter adds a newline."
            }
            className="min-h-[110px] resize-none border-0 bg-transparent shadow-none focus-visible:ring-0"
            disabled={loading || Boolean(pendingBlockingItem)}
          />
          <div className="mt-3 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
              <CornerDownLeft className="h-3.5 w-3.5" />
              {pendingBlockingItem
                ? "A pending agent card is blocking the run."
                : "Enter sends. Shift+Enter keeps writing."}
            </div>
            <Button onClick={() => void sendMessage()} disabled={!input.trim() || loading || Boolean(pendingBlockingItem)}>
              Send
            </Button>
          </div>
        </div>
      </div>
    </SurfacePanel>
  );

  const sessionsInspector = (
    <SurfacePanel data-agent-inspector="true" data-agent-stage="card" className="space-y-3">
      <div className="rounded-[1rem] border border-border/70 bg-background/55 px-3 py-3">
        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
          Previous sessions
        </p>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          Reset starts a new active thread. Resume only restores sessions saved for this repo workspace.
        </p>
        <div className="mt-4">
          <Button
            variant="outline"
            onClick={resumeLatestSession}
            disabled={!latestResumeSessionId}
            className="w-full rounded-full"
          >
            Resume latest repo session
          </Button>
        </div>
      </div>

      <div className="scroll-panel max-h-[34rem] space-y-2 overflow-y-auto pr-1">
        {!sessionListLoaded ? (
          <LoadingState label="Loading sessions..." />
        ) : recentSessions.length === 0 ? (
          <p className="rounded-[1.4rem] border border-border/70 bg-background/55 px-4 py-4 text-sm text-muted-foreground">
            No prior sessions yet.
          </p>
        ) : (
          recentSessions.map((session) => {
            const isActiveSession = session.id === sessionId;
            return (
              <button
                key={session.id}
                type="button"
                onClick={() => openSession(session.id)}
                className={[
                  "w-full rounded-[1.1rem] border px-3 py-3 text-left transition-colors",
                  isActiveSession
                    ? "border-foreground/15 bg-foreground text-background"
                    : "border-border/75 bg-background/70 hover:bg-background/90",
                ].join(" ")}
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{session.preview || "Session"}</p>
                    <p
                      className={[
                        "mt-1 text-[11px] uppercase tracking-[0.18em]",
                        isActiveSession ? "text-background/70" : "text-muted-foreground",
                      ].join(" ")}
                    >
                      {new Date(session.updated_at).toLocaleString()}
                    </p>
                    {session.is_resume_candidate ? (
                      <p
                        className={[
                          "mt-2 text-[11px] uppercase tracking-[0.18em]",
                          isActiveSession ? "text-background/70" : "text-muted-foreground",
                        ].join(" ")}
                      >
                        Latest repo resume
                      </p>
                    ) : null}
                  </div>
                  <Badge variant={isActiveSession ? "secondary" : "outline"}>{session.message_count}</Badge>
                </div>
              </button>
            );
          })
        )}
      </div>
    </SurfacePanel>
  );

  return (
    <PageFrame variant="explorer" className="max-w-[1500px]">
      <div ref={pageRef}>
        <div data-agent-stage="section" className="mb-3 flex flex-wrap items-center justify-between gap-3 rounded-[1.35rem] border border-border/70 bg-card/72 px-3 py-2.5 sm:px-4">
          <div className="min-w-0">
            <p className="page-eyebrow">Embedded agent</p>
            <h1 className="truncate font-[family:var(--font-heading)] text-[1.55rem] font-normal leading-tight tracking-[-0.035em] text-foreground sm:text-[1.85rem]">
              Live operator thread
            </h1>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <StatPill compact label="State" value={status?.running ? "live" : "ready"} tone={status?.running ? "active" : "muted"} />
            <StatPill compact label="Session" value={sessionId ? sessionId.slice(0, 8) : "new"} />
            <Button variant="outline" size="sm" className="h-8 rounded-full px-3" onClick={resumeLatestSession} disabled={!latestResumeSessionId}>
              Resume
            </Button>
            <Button size="sm" className="h-8 rounded-full px-3" onClick={clearSession}>
              New thread
            </Button>
          </div>
        </div>

        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_300px] lg:items-start">
          <WorkspaceLane className="min-w-0">
            {transcriptPanel}

            <div className="space-y-3 lg:hidden">
              {currentRunPanel}
              <div className="grid grid-cols-2 gap-2">
                {[
                  { id: "evidence", label: "Evidence" },
                  { id: "sessions", label: "Sessions" },
                ].map((option) => (
                  <Button
                    key={option.id}
                    variant={activeInspector === option.id ? "default" : "outline"}
                    size="sm"
                    className="h-8 rounded-full px-3 text-[12px]"
                    onClick={() => {
                      const next = option.id as AgentInspector;
                      setActiveInspector(next);
                      updatePreferences({ agentInspectorDefault: next });
                    }}
                  >
                    {option.label}
                  </Button>
                ))}
              </div>
              {activeInspector === "evidence" ? evidenceInspector : sessionsInspector}
            </div>
          </WorkspaceLane>

          <aside className="hidden min-w-0 lg:block">
            <div className="sticky top-20 space-y-3">
              <SurfacePanel
                data-agent-stage="card"
                className={[
                  "space-y-3 rounded-[1.25rem] px-3.5 py-3.5",
                  status?.running ? "ambient-scan" : "",
                ].join(" ")}
              >
                <div className="relative flex items-center justify-between gap-3">
                  <SectionLabel>Run frame</SectionLabel>
                  <LivePulse
                    running={Boolean(status?.running)}
                    label={shellSummary?.running_label ?? (status?.running ? "agent · live" : "agent · idle")}
                  />
                </div>
                <div className="relative space-y-2">
                  <MetricRow label="Model" value={modelName ?? "loading"} mono />
                  <ProgressMeter
                    current={status?.current_turn ?? 0}
                    max={status?.max_turns ?? 0}
                  />
                </div>
                <CostMeter
                  value={status?.cost_usd ?? 0}
                  label="Session cost"
                />
                <div className="relative flex items-center justify-between gap-3 text-[12.5px]">
                  <span className="text-muted-foreground">Tokens</span>
                  <span className="font-mono tabular-nums">
                    {status?.tokens_used != null ? status.tokens_used.toLocaleString() : "0"}
                  </span>
                </div>
                <div className="relative rounded-[1rem] border border-border/70 bg-background/55 px-3 py-3 text-sm leading-6 text-muted-foreground">
                  {pendingBlockingItem
                    ? "A pending card is blocking the next send. Respond inline in the thread."
                    : "No blocking approval is holding the thread right now."}
                </div>
                {sessionTodoSnapshot ? (
                  <div className="relative">
                    <TodoStrip snapshot={sessionTodoSnapshot} />
                  </div>
                ) : null}
                {shellSummary ? (
                  <div className="relative">
                    <MCPChips
                      servers={shellSummary.mcp_servers}
                      tools={shellSummary.mcp_tools}
                      permissionMode={shellSummary.permission_mode}
                    />
                  </div>
                ) : null}
                <div className="grid grid-cols-2 gap-2">
                  {[
                    { id: "evidence", label: "Evidence" },
                    { id: "sessions", label: "Sessions" },
                  ].map((option) => (
                    <Button
                      key={option.id}
                      variant={activeInspector === option.id ? "default" : "outline"}
                      size="sm"
                      className="h-8 rounded-full px-3 text-[12px]"
                      onClick={() => {
                        const next = option.id as AgentInspector;
                        setActiveInspector(next);
                        updatePreferences({ agentInspectorDefault: next });
                      }}
                    >
                      {option.label}
                    </Button>
                  ))}
                </div>
              </SurfacePanel>

              {activeInspector === "evidence" ? evidenceInspector : sessionsInspector}
            </div>
          </aside>
        </div>
      </div>
    </PageFrame>
  );
}

function MetricRow({
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
      <span className={mono ? "font-mono text-[11px] text-foreground" : "text-foreground"}>
        {value}
      </span>
    </div>
  );
}
