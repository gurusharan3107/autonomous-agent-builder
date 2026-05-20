import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Button } from "@/design-system";
import {
  PageFrame,
  PageHeader,
  StatusPill,
  SurfacePanel,
  Tabs,
  WorkspaceLane,
} from "@/design-system";
import { LivePulse } from "@/components/agent-native";
import { fetchBoard, fetchShellSummary, openBoardStream } from "@/lib/api";
import type {
  BoardData,
  ShellSummary,
} from "@/lib/types";
import { AgentConversationRail } from "@/features/agent/AgentConversationRail";
import { AgentRunTracePanel } from "@/features/agent/AgentRunTracePanel";
import { AgentStageStepper } from "@/features/agent/AgentRunPresenters";
import { AgentTranscriptPanel } from "@/features/agent/AgentTranscriptPanel";
import {
  buildActiveToolActivity,
  buildLogBlockItems,
  buildTaskRunLogItems,
  buildTaskRunTraceEntries,
  buildThreadTimelineEntries,
  buildVoiceTimelineEntries,
  summarizeTraceEvents,
} from "@/features/agent/AgentTimelineBuilders";
import { AgentTraceRail } from "@/features/agent/AgentTraceRail";
import { AgentVoicePanel } from "@/features/agent/AgentVoicePanel";
import {
  APPROVAL_EVENT_TYPES,
  LOG_EVENT_TYPES,
  THREAD_EVENT_TYPES,
  approvalDecisionFromText,
  findPendingBlockingItem,
  historyStillLoading,
  sortRunsNewestFirst,
  statusTokenAccounting,
  taskLatestRunTime,
  truncateText,
  upsertTimelineItem,
  type AgentMode,
  type AgentStatus,
  type ApprovalDraft,
  type ChatMetaResponse,
  type ChatRespondResponse,
  type ChatResponse,
  type HistoryResponse,
  type QuestionDraft,
  type SessionListResponse,
  type TimelineItem,
  type TranscriptFilter,
} from "@/features/agent/agent-model";
import { useAgentPageAnimations } from "@/hooks/use-agent-page-animations";
import { useRealtimeVoice } from "@/hooks/use-realtime-voice";
import { useRuntimePreferences } from "@/hooks/use-runtime-preferences";

async function getResponseError(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: unknown };
    if (typeof payload.detail === "string") return payload.detail;
    if (payload.detail) return JSON.stringify(payload.detail);
  } catch {
    // Ignore JSON parse failures and fall back to status text.
  }

  return response.statusText || `Request failed with status ${response.status}`;
}

export default function AgentPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { preferences, updatePreferences } = useRuntimePreferences();
  const [items, setItems] = useState<TimelineItem[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [, setModelName] = useState<string | null>(null);
  const [, setEffortName] = useState<string | null>(null);
  const [threadRuntimeSdk, setRuntimeSdk] = useState<string | null>(null);
  const [, setProviderName] = useState<string | null>(null);
  const [selectedRuntimeSdk, setSelectedRuntimeSdk] = useState<string | null>(null);
  const [, setSelectedProviderName] = useState<string | null>(null);
  const [repoIdentity, setRepoIdentity] = useState<string | null>(null);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const [latestResumeSessionId, setLatestResumeSessionId] = useState<string | null>(null);
  const [streamingText, setStreamingText] = useState("");
  const [questionDrafts, setQuestionDrafts] = useState<Record<string, QuestionDraft>>({});
  const [approvalDrafts, setApprovalDrafts] = useState<Record<string, ApprovalDraft>>({});
  const [submittingEventId, setSubmittingEventId] = useState<string | null>(null);
  const [agentMode, setAgentMode] = useState<AgentMode>(preferences.agentDefaultMode);
  const [transcriptFilter, setTranscriptFilter] = useState<TranscriptFilter>(preferences.transcriptFilterDefault);
  const [shellSummary, setShellSummary] = useState<ShellSummary | null>(null);
  const [boardData, setBoardData] = useState<BoardData | null>(null);
  const [boardError, setBoardError] = useState<string | null>(null);
  const [selectedTraceSprintId, setSelectedTraceSprintId] = useState<string | null>(null);
  const [selectedTraceTaskId, setSelectedTraceTaskId] = useState<string | null>(null);
  const [selectedTraceRunId, setSelectedTraceRunId] = useState<string | null>(null);
  const requestedAgentMode = searchParams.get("mode") ?? searchParams.get("tab");
  const requestedSessionId = searchParams.get("session");
  const traceTaskParam = searchParams.get("task");
  const traceRunParam = searchParams.get("run");
  const {
    voiceStatus,
    voiceError,
    voiceNotice,
    voiceMode,
    voiceCallId,
    voiceEvents,
    voiceMessages,
    sendRealtimeText,
    startVoiceSession,
    stopVoiceSession,
    clearVoiceTranscript,
  } = useRealtimeVoice();
  const [realtimeTextDraft, setRealtimeTextDraft] = useState("");
  const [realtimeTextError, setRealtimeTextError] = useState<string | null>(null);
  const [realtimeTextSubmitting, setRealtimeTextSubmitting] = useState(false);
  const realtimeTextSubmittingRef = useRef(false);
  const realtimeTextInputRef = useRef<HTMLTextAreaElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const transcriptScrollRef = useRef<HTMLDivElement>(null);
  const settledBlockingItemIdRef = useRef<string | null>(null);
  const sessionIdRef = useRef<string | null>(null);
  const chatStreamRef = useRef<EventSource | null>(null);
  const detachedVoiceSessionIdsRef = useRef<Set<string>>(new Set());
  const voiceTranscriptRefreshTimerRef = useRef<number | null>(null);
  const voiceTranscriptRefreshInFlightRef = useRef(false);
  const latestVoiceNavigationEventIdRef = useRef<string | null>(null);
  const pageRef = useAgentPageAnimations("evidence");
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

  const setActiveSessionId = (nextSessionId: string | null) => {
    sessionIdRef.current = nextSessionId;
    setSessionId(nextSessionId);
  };

  useEffect(() => {
    setTranscriptFilter(preferences.transcriptFilterDefault);
  }, [preferences.transcriptFilterDefault]);

  useEffect(() => {
    if (requestedAgentMode === "chat") {
      setAgentMode("chat");
      setTranscriptFilter("thread");
      return;
    }
    if (requestedAgentMode === "voice") {
      setAgentMode("voice");
      return;
    }
    if (requestedAgentMode === "trace") {
      setAgentMode("trace");
      setTranscriptFilter("full");
      return;
    }
    setAgentMode(preferences.agentDefaultMode);
  }, [preferences.agentDefaultMode, requestedAgentMode]);

  const handleAgentModeChange = (nextMode: AgentMode) => {
    setAgentMode(nextMode);
    if (nextMode === "chat") {
      setTranscriptFilter("thread");
    }
    const nextSearchParams = new URLSearchParams(searchParams);
    nextSearchParams.delete("tab");
    nextSearchParams.set("mode", nextMode);
    const nextSearch = nextSearchParams.toString();
    navigate(`${window.location.pathname}${nextSearch ? `?${nextSearch}` : ""}`, { replace: true });
  };

  const navigateToSession = (nextSessionId: string, nextMode: AgentMode = agentMode) => {
    const nextSearchParams = new URLSearchParams(searchParams);
    nextSearchParams.delete("tab");
    nextSearchParams.set("mode", nextMode);
    nextSearchParams.set("session", nextSessionId);
    const nextSearch = nextSearchParams.toString();
    navigate(`${window.location.pathname}${nextSearch ? `?${nextSearch}` : ""}`, { replace: true });
  };

  const applyVoiceNavigationPayload = (payload: Record<string, unknown>) => {
    const route = typeof payload.route === "string" ? payload.route : "";
    const routeSessionId = route.startsWith("/")
      ? new URL(route, window.location.origin).searchParams.get("session") || ""
      : "";
    const nextSessionId =
      typeof payload.session_id === "string" && payload.session_id ? payload.session_id : routeSessionId;
    if (nextSessionId) {
      detachedVoiceSessionIdsRef.current.delete(nextSessionId);
      setActiveSessionId(nextSessionId);
      writeStoredSessionId(nextSessionId);
      void loadHistory(nextSessionId);
      void loadSessionList(nextSessionId);
    }
    if (!route.startsWith("/")) return;
    const targetUrl = new URL(route, window.location.origin);
    const requestedMode = targetUrl.searchParams.get("mode");
    if (requestedMode === "trace") {
      setAgentMode("trace");
      setTranscriptFilter("full");
      setSelectedTraceTaskId(targetUrl.searchParams.get("task"));
      setSelectedTraceRunId(targetUrl.searchParams.get("run"));
    } else if (requestedMode === "voice") {
      setAgentMode("voice");
    } else if (requestedMode === "chat") {
      setAgentMode("chat");
      setTranscriptFilter("thread");
    }
    navigate(route);
  };

  const submitRealtimeText = async (textOverride?: string) => {
    if (realtimeTextSubmittingRef.current) return;
    const message = (textOverride ?? realtimeTextInputRef.current?.value ?? realtimeTextDraft).trim();
    if (!message) return;
    realtimeTextSubmittingRef.current = true;
    setRealtimeTextError(null);
    setRealtimeTextSubmitting(true);
    try {
      await sendRealtimeText(message);
      setRealtimeTextDraft("");
      if (realtimeTextInputRef.current) {
        realtimeTextInputRef.current.value = "";
      }
    } catch (error) {
      setRealtimeTextError(error instanceof Error ? error.message : "Realtime message failed.");
    } finally {
      realtimeTextSubmittingRef.current = false;
      setRealtimeTextSubmitting(false);
    }
  };

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
    let active = true;
    let receivedSnapshot = false;
    const loadFallback = async () => {
      try {
        const board = await fetchBoard();
        if (active) {
          setBoardData(board);
          setBoardError(null);
        }
      } catch (error) {
        if (active) {
          setBoardError(error instanceof Error ? error.message : "Failed to load board task runs");
        }
      }
    };
    void loadFallback();
    if (agentMode === "voice") {
      const interval = window.setInterval(() => void loadFallback(), 15000);
      return () => {
        active = false;
        window.clearInterval(interval);
      };
    }
    const stream = openBoardStream((board) => {
      if (!active) return;
      receivedSnapshot = true;
      setBoardData(board);
      setBoardError(null);
    });

    stream.onerror = () => {
      if (!active) return;
      if (!receivedSnapshot) {
        void loadFallback();
      }
    };

    return () => {
      active = false;
      stream.close();
    };
  }, [agentMode]);

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
          setEffortName(data.effort ?? null);
          setSelectedRuntimeSdk(data.runtime_sdk ?? null);
          setSelectedProviderName(data.provider ?? null);
          setRuntimeSdk(data.runtime_sdk ?? null);
          setProviderName(data.provider ?? null);
          setRepoIdentity(data.repo_identity);
        }
      } catch (error) {
        console.error("Failed to load chat metadata:", error);
      }
    };

    void loadChatMeta();
    const onRuntimeSettingsUpdated = (event: Event) => {
      const settings = (event as CustomEvent<{ sdk?: string; provider?: string; model?: string }>).detail;
      setSelectedRuntimeSdk(settings?.sdk ?? null);
      setSelectedProviderName(settings?.provider ?? null);
      setModelName(settings?.model ?? "");
    };
    window.addEventListener("aab:runtime-settings-updated", onRuntimeSettingsUpdated);

    return () => {
      cancelled = true;
      window.removeEventListener("aab:runtime-settings-updated", onRuntimeSettingsUpdated);
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
      setLatestResumeSessionId(data.latest_resume_session_id ?? null);

      if (preferredSessionId) {
        const match = data.sessions.find((session) => session.id === preferredSessionId);
        if (!match) {
          writeStoredSessionId(null);
          setActiveSessionId(null);
        }
      }
    } catch (error) {
      console.error("Failed to load session list:", error);
    }
  };

  const loadHistory = async (
    targetSessionId?: string | null,
    options?: { fresh?: boolean; quiet?: boolean },
  ) => {
    const selectedSessionId =
      targetSessionId === undefined
        ? searchParams.get("session") || readStoredSessionId()
        : targetSessionId;
    const fresh = Boolean(options?.fresh);
    const quiet = Boolean(options?.quiet);

    if (!quiet) {
      setHistoryLoaded(false);
    }

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
      setEffortName(data.effort ?? data.status?.effort ?? null);
      setRuntimeSdk(data.runtime_sdk ?? data.status?.runtime_sdk ?? null);
      setProviderName(data.provider ?? data.status?.provider ?? null);
      setRepoIdentity(data.repo_identity);
      const nextSessionId = data.session_id || null;
      if (nextSessionId) {
        detachedVoiceSessionIdsRef.current.delete(nextSessionId);
      }
      setActiveSessionId(nextSessionId);
      setItems(data.items ?? []);
      setStatus(data.status ?? null);
      setStreamingText("");
      setLoading(historyStillLoading(data));

      writeStoredSessionId(data.session_id || null);
      return data;
    } catch (error) {
      if (selectedSessionId && error instanceof Error && error.message.includes("different repo or workspace")) {
        writeStoredSessionId(null);
        return await loadHistory(null);
      }
      console.error("Failed to load chat history:", error);
      if (!quiet) {
        setItems([]);
        setStatus(null);
      }
      return null;
    } finally {
      if (!quiet) {
        setHistoryLoaded(true);
      }
    }
  };

  const applyVoiceHistoryIfRelevant = (data: HistoryResponse) => {
    if (!data.session_id) return;
    if (detachedVoiceSessionIdsRef.current.has(data.session_id)) return;
    const nextItems = data.items ?? [];
    const hasVoiceTranscript = nextItems.some(
      (item) =>
        item.type.startsWith("voice_") ||
        item.type === "voice_operator_message" ||
        item.type === "voice_final_summary" ||
        item.payload.source === "realtime_voice" ||
        item.payload.speaker === "realtime_voice_ai",
    );
    if (!hasVoiceTranscript) return;

    const switchingSession = data.session_id !== sessionIdRef.current;
    const currentLastItem = items.at(-1);
    const nextLastItem = nextItems.at(-1);
    const transcriptChanged =
      switchingSession ||
      items.length !== nextItems.length ||
      currentLastItem?.id !== nextLastItem?.id ||
      currentLastItem?.status !== nextLastItem?.status;
    if (!transcriptChanged) return;

    setModelName(data.model ?? null);
    setEffortName(data.effort ?? data.status?.effort ?? null);
    setRuntimeSdk(data.runtime_sdk ?? data.status?.runtime_sdk ?? null);
    setProviderName(data.provider ?? data.status?.provider ?? null);
    setRepoIdentity(data.repo_identity);
    const nextSessionId = data.session_id || null;
    setActiveSessionId(nextSessionId);
    setItems(nextItems);
    setStatus(data.status ?? null);
    if (switchingSession || !data.status?.running) {
      setStreamingText("");
    }
    setLoading(historyStillLoading(data));
    writeStoredSessionId(data.session_id || null);
    if (switchingSession) {
      void loadSessionList(data.session_id || null);
    }
  };

  const syncVoiceTranscript = async () => {
    if (voiceTranscriptRefreshInFlightRef.current) return;
    voiceTranscriptRefreshInFlightRef.current = true;
    try {
      const activeSessionId = sessionIdRef.current;
      const historyUrl = activeSessionId
        ? `/api/agent/chat/history?session_id=${encodeURIComponent(activeSessionId)}`
        : "/api/agent/chat/history?fresh=1";
      const response = await fetch(historyUrl);
      if (!response.ok) return;
      applyVoiceHistoryIfRelevant((await response.json()) as HistoryResponse);
    } catch (error) {
      console.error("Failed to sync voice transcript:", error);
    } finally {
      voiceTranscriptRefreshInFlightRef.current = false;
    }
  };

  const scheduleVoiceTranscriptSync = () => {
    if (voiceTranscriptRefreshTimerRef.current !== null) {
      window.clearTimeout(voiceTranscriptRefreshTimerRef.current);
    }
    voiceTranscriptRefreshTimerRef.current = window.setTimeout(() => {
      voiceTranscriptRefreshTimerRef.current = null;
      void syncVoiceTranscript();
    }, 700);
  };

  useEffect(() => {
    const onVoiceSessionBound = (event: Event) => {
      const sessionIdFromVoice = (event as CustomEvent<{ sessionId?: string }>).detail?.sessionId;
      if (!sessionIdFromVoice) return;
      if (detachedVoiceSessionIdsRef.current.has(sessionIdFromVoice)) return;
      setActiveSessionId(sessionIdFromVoice);
      writeStoredSessionId(sessionIdFromVoice);
      void loadHistory(sessionIdFromVoice);
      void loadSessionList(sessionIdFromVoice);
    };
    const onVoiceTranscriptSync = () => scheduleVoiceTranscriptSync();

    window.addEventListener("aab:voice-session-bound", onVoiceSessionBound);
    window.addEventListener("aab:voice-transcript-sync", onVoiceTranscriptSync);
    return () => {
      window.removeEventListener("aab:voice-session-bound", onVoiceSessionBound);
      window.removeEventListener("aab:voice-transcript-sync", onVoiceTranscriptSync);
    };
  });

  useEffect(() => {
    const bootstrap = async () => {
      localStorage.removeItem("chat_session_id");
      const storedSessionId = requestedSessionId || readStoredSessionId();
      const loadedHistory = storedSessionId
        ? await loadHistory(storedSessionId)
        : await loadHistory(null, { fresh: true });
      let activeSessionId = storedSessionId;
      const explicitSessionId = requestedSessionId;
      const loadedRuntime = loadedHistory?.status?.runtime_sdk ?? loadedHistory?.runtime_sdk ?? null;
      if (
        !explicitSessionId &&
        selectedRuntimeSdk &&
        loadedRuntime &&
        loadedRuntime !== selectedRuntimeSdk
      ) {
        writeStoredSessionId(null);
        await loadHistory(null, { fresh: true });
        activeSessionId = null;
      }
      await loadSessionList(activeSessionId ?? readStoredSessionId());
    };

    void bootstrap();
    // Bootstrap intentionally re-runs only when the repo key or search params change.
    // loadHistory/loadSessionList/readStoredSessionId are inline closures that read
    // current state; including them would cascade re-fetches.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestedSessionId, selectedRuntimeSdk, sessionStorageKey]);

  useEffect(() => {
    if (!sessionId) return;
    if (agentMode === "voice") return;

    const stream = new EventSource(`/api/agent/chat/stream?session_id=${encodeURIComponent(sessionId)}`);
    chatStreamRef.current = stream;

    stream.addEventListener("snapshot", (event) => {
      const message = event as MessageEvent<string>;
      const payload = JSON.parse(message.data) as HistoryResponse;
      setHistoryLoaded(true);
      setItems(payload.items ?? []);
      setModelName(payload.model ?? payload.status?.model ?? null);
      setEffortName(payload.effort ?? payload.status?.effort ?? null);
      setRuntimeSdk(payload.runtime_sdk ?? payload.status?.runtime_sdk ?? null);
      setProviderName(payload.provider ?? payload.status?.provider ?? null);
      setStatus(payload.status ?? null);
      setStreamingText("");
      setLoading(historyStillLoading(payload));
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
        if (nextStatus.model) {
          setModelName(nextStatus.model);
        }
        if (nextStatus.effort) {
          setEffortName(nextStatus.effort);
        }
        if (nextStatus.runtime_sdk) {
          setRuntimeSdk(nextStatus.runtime_sdk);
        }
        if (nextStatus.provider) {
          setProviderName(nextStatus.provider);
        }
        setStatus(nextStatus);
        setLoading(Boolean(nextStatus.running));
        return;
      }

      setItems((current) => upsertTimelineItem(current, payload));
      if (
        (payload.type === "voice_navigation_request" || payload.type === "voice_control_action") &&
        payload.id !== latestVoiceNavigationEventIdRef.current
      ) {
        latestVoiceNavigationEventIdRef.current = payload.id;
        applyVoiceNavigationPayload(payload.payload);
      }
      if (
        payload.type === "assistant_message" ||
        payload.type === "run_error" ||
        payload.type === "ask_user_question" ||
        APPROVAL_EVENT_TYPES.has(payload.type)
      ) {
        setStreamingText("");
        if (payload.type !== "assistant_message" || payload.status === "completed") {
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
      if (chatStreamRef.current === stream) {
        chatStreamRef.current = null;
      }
    };
    // Stream is keyed to sessionId only; loadSessionList is an inline closure
    // that reads current state, by design.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, agentMode]);

  useEffect(() => {
    if (!sessionId || !loading) return undefined;
    const interval = window.setInterval(() => {
      void loadHistory(sessionId, { quiet: true });
    }, 2000);
    return () => window.clearInterval(interval);
    // This is a narrow recovery path for missed SSE events while a run is active.
    // loadHistory is an inline closure that reads current state, by design.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, loading]);

  useEffect(() => {
    const handleVoiceNavigation = (event: Event) => {
      const detail = (event as CustomEvent<Record<string, unknown>>).detail ?? {};
      applyVoiceNavigationPayload(detail);
    };
    window.addEventListener("aab:voice-navigation-request", handleVoiceNavigation);
    window.addEventListener("aab:voice-control-action", handleVoiceNavigation);
    return () => {
      window.removeEventListener("aab:voice-navigation-request", handleVoiceNavigation);
      window.removeEventListener("aab:voice-control-action", handleVoiceNavigation);
    };
  });

  useEffect(() => {
    if (voiceStatus !== "connected") return undefined;
    scheduleVoiceTranscriptSync();
    const interval = window.setInterval(() => scheduleVoiceTranscriptSync(), 3000);
    return () => {
      window.clearInterval(interval);
      if (voiceTranscriptRefreshTimerRef.current !== null) {
        window.clearTimeout(voiceTranscriptRefreshTimerRef.current);
        voiceTranscriptRefreshTimerRef.current = null;
      }
    };
    // Voice transcript sync deliberately follows the active voice transport, not the current SSE session.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [voiceStatus]);

  const pendingBlockingItem = useMemo(() => findPendingBlockingItem(items), [items]);
  const pendingBlockingItemId = pendingBlockingItem?.id ?? null;

  useEffect(() => {
    const transcriptScroller = transcriptScrollRef.current;
    if (pendingBlockingItemId) {
      if (!transcriptScroller) return undefined;
      if (settledBlockingItemIdRef.current === pendingBlockingItemId) {
        return undefined;
      }
      settledBlockingItemIdRef.current = pendingBlockingItemId;
      const animationFrame = requestAnimationFrame(() => {
        transcriptScroller.scrollTo({
          top: transcriptScroller.scrollHeight,
          behavior: "smooth",
        });
      });
      return () => {
        cancelAnimationFrame(animationFrame);
      };
    }
    settledBlockingItemIdRef.current = null;
    return undefined;
  }, [pendingBlockingItemId]);

  const transcriptTailKey = `${items.length}:${items.at(-1)?.id ?? "empty"}:${streamingText}`;

  useEffect(() => {
    if (pendingBlockingItemId) return;
    const transcriptScroller = transcriptScrollRef.current;
    if (!transcriptScroller) return;
    const animationFrame = requestAnimationFrame(() => {
      transcriptScroller.scrollTo({
        top: transcriptScroller.scrollHeight,
        behavior: "auto",
      });
    });
    return () => {
      cancelAnimationFrame(animationFrame);
    };
  }, [transcriptTailKey, pendingBlockingItemId]);

  const sendMessage = async () => {
    const prompt = input.trim();
    if (!prompt || (loading && !pendingBlockingItem)) return;
    if (pendingBlockingItem?.type === "ask_user_question") {
      setInput("");
      await submitQuestion(pendingBlockingItem, { customText: prompt });
      return;
    }
    if (pendingBlockingItem && APPROVAL_EVENT_TYPES.has(pendingBlockingItem.type)) {
      const decision = approvalDecisionFromText(prompt);
      if (!decision) return;
      setInput("");
      await submitApproval(pendingBlockingItem, decision, prompt);
      return;
    }
    if (pendingBlockingItem) return;

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
      let refreshedHistory: HistoryResponse | null = null;
      if (data.session_id) {
        detachedVoiceSessionIdsRef.current.delete(data.session_id);
        setActiveSessionId(data.session_id);
        writeStoredSessionId(data.session_id);
        navigateToSession(data.session_id, "chat");
        refreshedHistory = await loadHistory(data.session_id);
        void loadSessionList(data.session_id);
      }

      if (data.model) {
        setModelName(data.model);
      }
      if (data.effort) {
        setEffortName(data.effort);
      }
      if (data.runtime_sdk) {
        setRuntimeSdk(data.runtime_sdk);
      }
      if (data.provider) {
        setProviderName(data.provider);
      }

      if (data.status) {
        if (data.status.model) {
          setModelName(data.status.model);
        }
        if (data.status.effort) {
          setEffortName(data.status.effort);
        }
        if (data.status.runtime_sdk) {
          setRuntimeSdk(data.status.runtime_sdk);
        }
        if (data.status.provider) {
          setProviderName(data.status.provider);
        }
        setStatus(data.status);
        const refreshedHasPending = refreshedHistory
          ? findPendingBlockingItem(refreshedHistory.items ?? []) !== null
          : false;
        setLoading(Boolean(data.status.running) && !refreshedHasPending);
      } else {
        setLoading(false);
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

  const submitQuestion = async (
    item: TimelineItem,
    override?: { selectedOptions?: string[]; customText?: string },
  ) => {
    if (!sessionId) return;
    const draft = questionDrafts[item.id] ?? { selected: [], customText: "" };
    const customText = (override?.customText ?? draft.customText).trim();
    const selectedOptions = (override?.selectedOptions ?? draft.selected).filter(Boolean);
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
        navigateToSession(sessionId, "chat");
        setQuestionDrafts((current) => {
          const next = { ...current };
          delete next[item.id];
          return next;
        });
        await loadHistory(sessionId);
        void loadSessionList(sessionId);
      }
    } catch (error) {
      console.error("Failed to submit question response:", error);
    } finally {
      setSubmittingEventId(null);
    }
  };

  const submitApproval = async (
    item: TimelineItem,
    decision: "allow" | "deny",
    overrideReason?: string,
  ) => {
    if (!sessionId) return;
    const draft = approvalDrafts[item.id] ?? { reason: "" };
    const reason = overrideReason ?? draft.reason;

    setSubmittingEventId(item.id);
    try {
      const response = await fetch("/api/agent/chat/respond", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          event_id: item.id,
          decision,
          reason,
        }),
      });
      if (!response.ok) {
        throw new Error(await getResponseError(response));
      }
      const data = (await response.json()) as ChatRespondResponse;
      if (data.ok) {
        navigateToSession(sessionId, "chat");
        setApprovalDrafts((current) => {
          const next = { ...current };
          delete next[item.id];
          return next;
        });
        await loadHistory(sessionId);
        void loadSessionList(sessionId);
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
    const clearedSessionId = sessionIdRef.current;
    if (clearedSessionId) {
      detachedVoiceSessionIdsRef.current.add(clearedSessionId);
    }
    if (voiceTranscriptRefreshTimerRef.current !== null) {
      window.clearTimeout(voiceTranscriptRefreshTimerRef.current);
      voiceTranscriptRefreshTimerRef.current = null;
    }
    if (chatStreamRef.current !== null) {
      chatStreamRef.current.close();
      chatStreamRef.current = null;
    }
    if (voiceStatus === "connected" || voiceStatus === "connecting") {
      stopVoiceSession();
    }
    clearVoiceTranscript();
    const nextSearchParams = new URLSearchParams(searchParams);
    nextSearchParams.delete("session");
    nextSearchParams.delete("task");
    nextSearchParams.delete("run");
    nextSearchParams.delete("tab");
    nextSearchParams.set("mode", agentMode);
    const nextSearch = nextSearchParams.toString();
    navigate(`${window.location.pathname}${nextSearch ? `?${nextSearch}` : ""}`, { replace: true });
    writeStoredSessionId(null);
    setActiveSessionId(null);
    setItems([]);
    setStatus(null);
    setStreamingText("");
    setInput("");
    setRealtimeTextDraft("");
    setRealtimeTextError(null);
    realtimeTextSubmittingRef.current = false;
    setRealtimeTextSubmitting(false);
    setLoading(false);
    setQuestionDrafts({});
    setApprovalDrafts({});
    void (async () => {
      await loadHistory(null, { fresh: true });
      await loadSessionList(null);
    })();
  };

  const openSession = (nextSessionId: string) => {
    navigateToSession(nextSessionId);
    void loadHistory(nextSessionId);
  };

  const resumeLatestSession = () => {
    if (!latestResumeSessionId) return;
    openSession(latestResumeSessionId);
  };

  const assistantMessages = items.filter((item) => item.type === "assistant_message");
  const logBlockItems = useMemo(() => buildLogBlockItems(items), [items]);
  const activeToolActivity = useMemo(() => buildActiveToolActivity(items), [items]);
  const timelineEntries = useMemo(
    () => buildThreadTimelineEntries({
      activeToolActivity,
      items,
      status,
      threadRuntimeSdk,
      transcriptFilter,
    }),
    [activeToolActivity, items, status, threadRuntimeSdk, transcriptFilter],
  );
  const voiceTimelineEntries = useMemo(() => buildVoiceTimelineEntries(voiceMessages), [voiceMessages]);

  const useTimelineLayout =
    transcriptFilter === "thread" && preferences.transcriptLayout === "timeline";
  const filteredItems = useMemo(() => {
    if (transcriptFilter === "thread") {
      return items.filter((item) => THREAD_EVENT_TYPES.has(item.type));
    }
    if (transcriptFilter === "logs") {
      return items.filter((item) => LOG_EVENT_TYPES.has(item.type));
    }
    return items;
  }, [items, transcriptFilter]);

  const latestOperatorPrompt = useMemo(() => {
    const latest = [...items].reverse().find((item) => item.type === "user_message");
    return truncateText(String(latest?.payload.content ?? ""), 86);
  }, [items]);
  const runVisualStatus = status?.error
    ? "failed"
    : pendingBlockingItem
      ? "review_pending"
      : status?.running
        ? "running"
        : "ready";
  const runTitle = latestOperatorPrompt || "Tell Builder what to improve next";
  const runDescription = pendingBlockingItem
    ? "A decision is waiting for you. Answer below so Builder can continue with recorded evidence."
    : "Follow Builder's conversation, questions, decisions, and work evidence in one place. Use this surface to guide the next improvement or continue current work.";
  const pendingApprovalDecision = pendingBlockingItem && APPROVAL_EVENT_TYPES.has(pendingBlockingItem.type)
    ? approvalDecisionFromText(input)
    : null;
  const composerPlaceholder = pendingBlockingItem?.type === "ask_user_question"
    ? "Other answer: type what you have in mind."
    : pendingBlockingItem && APPROVAL_EVENT_TYPES.has(pendingBlockingItem.type)
      ? "Type approve/start or deny/hold."
      : "Type the next instruction. Shift+Enter adds a newline.";
  const composerSendDisabled =
    !input.trim() ||
    (loading && !pendingBlockingItem) ||
    Boolean(
      pendingBlockingItem &&
      APPROVAL_EVENT_TYPES.has(pendingBlockingItem.type) &&
      !pendingApprovalDecision,
    );
  const currentPhaseIndex = pendingBlockingItem
    ? 4
    : status?.running
      ? 2
      : assistantMessages.length > 0
        ? 6
        : 0;
  const activeSessionLabel = sessionId ? sessionId.slice(0, 8) : "new";
  const boardTasks = useMemo(() => {
    return boardData
      ? [
          ...boardData.active,
          ...boardData.review,
          ...boardData.pending,
          ...boardData.done,
          ...boardData.blocked,
        ]
      : [];
  }, [boardData]);
  const sprintOptions = boardData?.sprints ?? [];
  const activeSprintId = selectedTraceSprintId === "all"
    ? null
    : selectedTraceSprintId
      ?? boardData?.current_sprint?.sprint_id
      ?? sprintOptions[0]?.sprint_id
      ?? null;
  const activeSprint = sprintOptions.find((sprint) => sprint.sprint_id === activeSprintId) ?? boardData?.current_sprint ?? null;
  const traceTasks = useMemo(() => {
    const sprintTaskIds = new Set(activeSprint?.generated_task_ids ?? []);
    const tasks = activeSprint
      ? boardTasks.filter((task) => sprintTaskIds.has(task.id))
      : boardTasks;
    return [...tasks].sort((left, right) => taskLatestRunTime(right) - taskLatestRunTime(left));
  }, [activeSprint, boardTasks]);
  const selectedTraceTask = useMemo(() => {
    const tasks = traceTasks.length > 0 ? traceTasks : boardTasks;
    if (!tasks.length) return null;
    const defaultTask = tasks.find((task) => task.agent_runs.length > 0) ?? tasks[0] ?? null;
    if (traceTaskParam) {
      return tasks.find((task) => task.id === traceTaskParam) ?? boardTasks.find((task) => task.id === traceTaskParam) ?? null;
    }
    if (selectedTraceTaskId) {
      return tasks.find((task) => task.id === selectedTraceTaskId) ?? boardTasks.find((task) => task.id === selectedTraceTaskId) ?? null;
    }
    if (traceRunParam) {
      return tasks.find((task) => task.agent_runs.some((run) => run.id === traceRunParam))
        ?? boardTasks.find((task) => task.agent_runs.some((run) => run.id === traceRunParam))
        ?? defaultTask;
    }
    if (selectedTraceRunId) {
      return tasks.find((task) => task.agent_runs.some((run) => run.id === selectedTraceRunId))
        ?? boardTasks.find((task) => task.agent_runs.some((run) => run.id === selectedTraceRunId))
        ?? defaultTask;
    }
    if (sessionId) {
      return tasks.find((task) => task.agent_runs.some((run) => run.session_id === sessionId))
        ?? boardTasks.find((task) => task.agent_runs.some((run) => run.session_id === sessionId))
        ?? defaultTask;
    }
    return defaultTask;
  }, [boardTasks, selectedTraceRunId, selectedTraceTaskId, sessionId, traceRunParam, traceTaskParam, traceTasks]);
  const selectedTraceRun = useMemo(() => {
    if (!selectedTraceTask) return null;
    const runs = sortRunsNewestFirst(selectedTraceTask.agent_runs);
    if (traceRunParam) return runs.find((run) => run.id === traceRunParam) ?? runs[0] ?? null;
    if (selectedTraceRunId) return runs.find((run) => run.id === selectedTraceRunId) ?? runs[0] ?? null;
    if (sessionId) return runs.find((run) => run.session_id === sessionId) ?? runs[0] ?? null;
    return runs[0] ?? null;
  }, [selectedTraceRunId, selectedTraceTask, sessionId, traceRunParam]);
  const selectedTraceRuns = useMemo(
    () => sortRunsNewestFirst(selectedTraceTask?.agent_runs ?? []),
    [selectedTraceTask],
  );
  const selectedTraceEvents = useMemo(() => {
    if (!selectedTraceTask || !selectedTraceRun) return [];
    return selectedTraceTask.activity_timeline
      .filter((event) => event.run_id === selectedTraceRun.id)
      .sort((left, right) => new Date(left.timestamp).getTime() - new Date(right.timestamp).getTime());
  }, [selectedTraceRun, selectedTraceTask]);
  const summarizedTraceEvents = useMemo(() => summarizeTraceEvents(selectedTraceEvents), [selectedTraceEvents]);
  const taskRunTraceEntries = useMemo(
    () => buildTaskRunTraceEntries({ selectedTraceRun, selectedTraceTask, summarizedTraceEvents }),
    [selectedTraceRun, selectedTraceTask, summarizedTraceEvents],
  );
  const taskRunLogItems = useMemo(() => buildTaskRunLogItems(selectedTraceEvents), [selectedTraceEvents]);
  const taskRunDiff = selectedTraceRun?.diff_summary ?? null;
  const currentTurnTokens = statusTokenAccounting(status);
  const traceSelectorRail = (
    <AgentTraceRail
      activeSprintId={activeSprintId}
      selectedTraceRun={selectedTraceRun}
      selectedTraceRuns={selectedTraceRuns}
      selectedTraceTask={selectedTraceTask}
      sprintOptions={sprintOptions}
      traceTasks={traceTasks}
      onSelectRun={(runId) => {
        setSelectedTraceRunId(runId);
        setAgentMode("trace");
      }}
      onSelectSprint={(value) => {
        setSelectedTraceSprintId(value === "all" ? "all" : value);
        setSelectedTraceTaskId(null);
        setSelectedTraceRunId(null);
      }}
      onSelectTask={(taskId) => {
        setSelectedTraceTaskId(taskId);
        setSelectedTraceRunId(null);
      }}
    />
  );
  const conversationRail = (
    <AgentConversationRail
      currentTurnTokens={currentTurnTokens}
      pendingBlocked={Boolean(pendingBlockingItem)}
      recentRuns={selectedTraceRuns}
      runVisualStatus={runVisualStatus}
      selectedRuntimeSdk={selectedRuntimeSdk}
      selectedTask={selectedTraceTask}
      sessionId={sessionId}
      status={status}
      threadRuntimeSdk={threadRuntimeSdk}
      onOpenTrace={() => setAgentMode("trace")}
      onSelectRun={(runId, mode) => {
        setSelectedTraceRunId(runId);
        setAgentMode(mode);
      }}
    />
  );

  const agentStageStrip = (
    <SurfacePanel
      data-agent-stage="section"
      className={[
        "relative overflow-hidden rounded-[1.35rem] px-3.5 py-3.5 sm:px-4",
        status?.running ? "ambient-scan" : "",
      ].join(" ")}
    >
      <div className="relative flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <AgentStageStepper current={currentPhaseIndex} />
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
    </SurfacePanel>
  );

  const agentRunPending = (loading || Boolean(status?.running)) && !streamingText && !pendingBlockingItem;
  const transcriptLoading = !historyLoaded && (loading || Boolean(status?.running) || Boolean(sessionId));
  const transcriptPanel = (
    <AgentTranscriptPanel
      activeToolActivity={activeToolActivity}
      agentRunPending={agentRunPending}
      approvalDrafts={approvalDrafts}
      composerPlaceholder={composerPlaceholder}
      composerSendDisabled={composerSendDisabled}
      filteredItems={filteredItems}
      handleKeyDown={handleKeyDown}
      input={input}
      logBlockItems={logBlockItems}
      messagesEndRef={messagesEndRef}
      pendingBlockingItem={pendingBlockingItem}
      questionDrafts={questionDrafts}
      sendMessage={sendMessage}
      setApprovalDrafts={setApprovalDrafts}
      setInput={setInput}
      setQuestionDrafts={setQuestionDrafts}
      streamingText={streamingText}
      submitApproval={submitApproval}
      submitQuestion={submitQuestion}
      submittingEventId={submittingEventId}
      timelineEntries={timelineEntries}
      transcriptFilter={transcriptFilter}
      transcriptLoading={transcriptLoading}
      transcriptScrollRef={transcriptScrollRef}
      useTimelineLayout={useTimelineLayout}
    />
  );

  const voicePanel = (
    <AgentVoicePanel
      realtimeTextDraft={realtimeTextDraft}
      realtimeTextError={realtimeTextError}
      realtimeTextInputRef={realtimeTextInputRef}
      realtimeTextSubmitting={realtimeTextSubmitting}
      sessionId={sessionId}
      setRealtimeTextDraft={setRealtimeTextDraft}
      startVoiceSession={startVoiceSession}
      stopVoiceSession={stopVoiceSession}
      submitRealtimeText={submitRealtimeText}
      voiceCallId={voiceCallId}
      voiceError={voiceError}
      voiceEvents={voiceEvents}
      voiceMessages={voiceMessages}
      voiceMode={voiceMode}
      voiceNotice={voiceNotice}
      voiceStatus={voiceStatus}
      voiceTimelineEntries={voiceTimelineEntries}
    />
  );

  const runTracePanel = (
    <AgentRunTracePanel
      boardData={boardData}
      boardError={boardError}
      selectedTraceRun={selectedTraceRun}
      selectedTraceTask={selectedTraceTask}
      taskRunDiff={taskRunDiff}
      taskRunLogItems={taskRunLogItems}
      taskRunTraceEntries={taskRunTraceEntries}
      traceSelectorRail={traceSelectorRail}
      transcriptFilter={transcriptFilter}
    />
  );

  return (
    <PageFrame variant="explorer" className="max-w-[1500px]" data-screen-label="Agent">
      <div ref={pageRef} className="space-y-5">
        <PageHeader
          eyebrow={`Task · ${activeSessionLabel}`}
          title={runTitle}
          description={runDescription}
          aside={
            <div className="flex flex-wrap items-center justify-end gap-2">
              <Tabs<AgentMode>
                value={agentMode}
                onChange={handleAgentModeChange}
                items={[
                  { value: "chat", label: "Conversation" },
                  { value: "voice", label: "Voice" },
                  { value: "trace", label: "Run trace" },
                ]}
              />
              <StatusPill status={runVisualStatus} />
              <LivePulse
                running={Boolean(status?.running)}
                label={
                  status?.running
                    ? shellSummary?.running_label ?? "agent · live"
                    : pendingBlockingItem
                      ? "agent · blocked"
                      : "agent · ready"
                }
              />
              <Button variant="outline" size="sm" className="h-9 rounded-full px-3" onClick={resumeLatestSession} disabled={!latestResumeSessionId}>
                Resume
              </Button>
              <Button size="sm" className="h-9 rounded-full px-3" onClick={clearSession}>
                New thread
              </Button>
            </div>
          }
        />

        {agentMode === "trace" ? agentStageStrip : null}

        {agentMode === "chat" ? (
          <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_340px] xl:items-start">
            <WorkspaceLane className="min-w-0">
              {transcriptPanel}
            </WorkspaceLane>
            {conversationRail}
          </div>
        ) : agentMode === "voice" ? (
          <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_340px] xl:items-start">
            <WorkspaceLane className="min-w-0">
              {voicePanel}
            </WorkspaceLane>
            {conversationRail}
          </div>
        ) : (
          runTracePanel
        )}
      </div>
    </PageFrame>
  );
}
