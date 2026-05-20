import type { TimelineEntry, TimelineLogItem } from "@/components/agent-native";
import type { TaskActivityEvent, TaskAgentRunSummary, TaskBoardItem } from "@/lib/types";
import type { RealtimeVoiceMessage } from "@/hooks/use-realtime-voice";
import {
  AGENT_RESPONSE_EVENT_TYPES,
  APPROVAL_EVENT_TYPES,
  LOG_EVENT_TYPES,
  THREAD_EVENT_TYPES,
  TOOL_ACTIVITY_EVENT_TYPES,
  decisionTimelineStatus,
  diagnosticForItem,
  formatTime,
  isUninformativeToolUse,
  questionAnswerText,
  readablePayloadText,
  runtimeTimelineIcon,
  type AgentStatus,
  type TimelineItem,
  type TranscriptFilter,
} from "@/features/agent/agent-model";

export interface ActiveToolActivity {
  active: boolean;
  count: number;
  latestToolName: string;
  itemIds: Set<string>;
}

export function buildLogBlockItems(items: TimelineItem[]): TimelineLogItem[] {
  const specialistEvents = items.filter((item) => item.type === "specialist_status");
  const builderLogItems = items.filter((item) => LOG_EVENT_TYPES.has(item.type));
  return [...specialistEvents, ...builderLogItems]
    .sort((left, right) => new Date(left.timestamp).getTime() - new Date(right.timestamp).getTime())
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
}

export function buildActiveToolActivity(items: TimelineItem[]): ActiveToolActivity {
  const latestUserIndex = items.findLastIndex((item) => item.type === "user_message");
  if (latestUserIndex < 0) {
    return { active: false, count: 0, latestToolName: "", itemIds: new Set<string>() };
  }
  const turnItems = items.slice(latestUserIndex + 1);
  const responseIndex = turnItems.findIndex((item) => AGENT_RESPONSE_EVENT_TYPES.has(item.type));
  if (responseIndex >= 0) {
    return { active: false, count: 0, latestToolName: "", itemIds: new Set<string>() };
  }
  const toolItems = turnItems.filter((item) => TOOL_ACTIVITY_EVENT_TYPES.has(item.type));
  const itemIds = new Set(toolItems.map((item) => item.id));
  const latestTool = toolItems.at(-1);
  const latestToolName = readablePayloadText(latestTool?.payload.tool_name ?? latestTool?.type ?? "");
  return {
    active: toolItems.length > 0,
    count: toolItems.length,
    latestToolName,
    itemIds,
  };
}

export function buildThreadTimelineEntries({
  activeToolActivity,
  items,
  status,
  threadRuntimeSdk,
  transcriptFilter,
}: {
  activeToolActivity: ActiveToolActivity;
  items: TimelineItem[];
  status: AgentStatus | null;
  threadRuntimeSdk: string | null;
  transcriptFilter: TranscriptFilter;
}): TimelineEntry[] {
  return items
    .filter((item) => {
      if (activeToolActivity.itemIds.has(item.id)) return false;
      if (transcriptFilter === "thread") return THREAD_EVENT_TYPES.has(item.type);
      return true;
    })
    .map((item): TimelineEntry => {
      const ts = formatTime(item.timestamp);
      if (item.type === "voice_operator_message") {
        return {
          id: item.id,
          kind: "user",
          timestamp: ts,
          label: "Operator",
          body: <span className="whitespace-pre-wrap">{String(item.payload.content ?? "")}</span>,
        };
      }
      if (item.type === "user_message") {
        const voiceDelegation = item.payload.source === "realtime_voice";
        return {
          id: item.id,
          kind: voiceDelegation ? "tool" : "user",
          timestamp: ts,
          label: voiceDelegation ? "Samantha" : undefined,
          icon: voiceDelegation ? "openai" : undefined,
          body: voiceDelegation
            ? undefined
            : <span className="whitespace-pre-wrap">{String(item.payload.content ?? "")}</span>,
          args: voiceDelegation ? String(item.payload.routing_reason ?? "") : undefined,
          result: voiceDelegation ? String(item.payload.content ?? "") : undefined,
        };
      }
      if (item.type === "assistant_message") {
        return {
          id: item.id,
          kind: "assistant",
          timestamp: ts,
          heading: "Assistant",
          icon: runtimeTimelineIcon(threadRuntimeSdk, status?.provider),
          body: String(item.payload.content ?? ""),
        };
      }
      if (item.type === "voice_final_summary") {
        return {
          id: item.id,
          kind: "tool",
          timestamp: ts,
          label: "Builder",
          result: String(item.payload.summary ?? ""),
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
      if (item.type === "ask_user_question" || APPROVAL_EVENT_TYPES.has(item.type)) {
        const answerText = item.type === "ask_user_question" ? questionAnswerText(item) : "";
        const questionText = readablePayloadText(
          item.payload.summary ?? item.payload.question ?? item.payload.tool_name,
        );
        return {
          id: item.id,
          kind: "assistant",
          timestamp: ts,
          heading: item.type === "ask_user_question" ? "Question" : "Approval needed",
          status: decisionTimelineStatus(item),
          icon: runtimeTimelineIcon(threadRuntimeSdk, status?.provider),
          body: answerText ? (
            <span className="space-y-2">
              <span className="block">{questionText}</span>
              <span className="stream-inner-panel block px-2.5 py-2">
                <span className="block font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                  Answered with
                </span>
                <span className="mt-1 block text-foreground/90">{answerText}</span>
              </span>
            </span>
          ) : (
            questionText
          ),
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
}

export function buildVoiceTimelineEntries(voiceMessages: RealtimeVoiceMessage[]): TimelineEntry[] {
  return voiceMessages.map((message): TimelineEntry => {
    const assistantMessage = message.role === "assistant";
    const systemMessage = message.role === "system";
    return {
      id: message.id,
      kind: assistantMessage ? "assistant" : systemMessage ? "gate" : "user",
      timestamp: formatTime(message.timestamp),
      heading: assistantMessage ? "Samantha" : systemMessage ? "Realtime system" : "Operator",
      icon: assistantMessage ? "openai" : undefined,
      label: assistantMessage
        ? "Samantha"
        : systemMessage
          ? "Realtime system"
          : "Operator",
      status: message.status === "streaming" ? "running" : undefined,
      body: <span className="whitespace-pre-wrap">{message.content}</span>,
    };
  });
}

export function summarizeTraceEvents(selectedTraceEvents: TaskActivityEvent[]): TaskActivityEvent[] {
  const summarized: TaskActivityEvent[] = [];
  let pendingEmptyTools: TaskActivityEvent[] = [];

  const flushEmptyTools = () => {
    if (pendingEmptyTools.length === 0) return;
    if (pendingEmptyTools.length === 1) {
      summarized.push(pendingEmptyTools[0]);
    } else {
      const first = pendingEmptyTools[0];
      summarized.push({
        ...first,
        id: `${first.id}:summary:${pendingEmptyTools.length}`,
        action: `${pendingEmptyTools.length} Builder action${pendingEmptyTools.length === 1 ? "" : "s"} completed`,
        event_type: "tool_use_summary",
      });
    }
    pendingEmptyTools = [];
  };

  selectedTraceEvents.forEach((event) => {
    if (isUninformativeToolUse(event)) {
      pendingEmptyTools.push(event);
      return;
    }
    flushEmptyTools();
    summarized.push(event);
  });
  flushEmptyTools();
  return summarized;
}

export function buildTaskRunTraceEntries({
  selectedTraceRun,
  selectedTraceTask,
  summarizedTraceEvents,
}: {
  selectedTraceRun: TaskAgentRunSummary | null;
  selectedTraceTask: TaskBoardItem | null;
  summarizedTraceEvents: TaskActivityEvent[];
}): TimelineEntry[] {
  if (!selectedTraceTask || !selectedTraceRun) return [];
  const entries: TimelineEntry[] = [
    {
      id: `${selectedTraceRun.id}:task`,
      kind: "user",
      timestamp: formatTime(selectedTraceRun.started_at),
      label: "task",
      body: selectedTraceTask.title,
      result: selectedTraceTask.feature_title,
    },
  ];
  summarizedTraceEvents.forEach((event) => {
    const toolSummaryCount = event.event_type === "tool_use_summary"
      ? Number(String(event.action).match(/^(\d+)/)?.[1] ?? 0)
      : 0;
    entries.push({
      id: event.id,
      kind: event.event_type.includes("tool") ? "tool" : event.event_type.includes("error") ? "gate" : "thinking",
      timestamp: formatTime(event.timestamp),
      label: event.event_type.replaceAll("_", " "),
      icon: runtimeTimelineIcon(event.runtime_sdk, event.provider),
      body: event.action || event.file_path || "run event",
      count: toolSummaryCount > 1 ? toolSummaryCount : undefined,
      result: event.file_path,
    });
  });
  entries.push({
    id: `${selectedTraceRun.id}:status`,
    kind: "gate",
    timestamp: selectedTraceRun.completed_at ? formatTime(selectedTraceRun.completed_at) : "running",
    label: "run status",
    body: selectedTraceRun.error ?? selectedTraceRun.status,
    status: selectedTraceRun.status,
    result: selectedTraceRun.stop_reason ?? undefined,
  });
  return entries;
}

export function buildTaskRunLogItems(selectedTraceEvents: TaskActivityEvent[]): TimelineLogItem[] {
  return selectedTraceEvents.map((event) => ({
    id: event.id,
    type: event.event_type,
    timestamp: event.timestamp,
    tool_name: event.event_type.replaceAll("_", " "),
    summary: event.action,
    preview: event.file_path,
  }));
}
