import type { Dispatch, KeyboardEvent, RefObject, SetStateAction } from "react";
import { CornerDownLeft } from "lucide-react";
import { Button, Code, EmptyState, LoadingState, SectionLabel, StatusPill, SurfacePanel } from "@/design-system";
import { Textarea } from "@/components/ui/textarea";
import { AgentTimeline, LogBlock, type TimelineEntry, type TimelineLogItem } from "@/components/agent-native";
import { AgentDecisionActions } from "@/features/agent/AgentDecisionActions";
import { renderAgentThreadItem } from "@/features/agent/AgentThreadCards";
import type {
  ApprovalDraft,
  QuestionDraft,
  TimelineItem,
  TranscriptFilter,
} from "@/features/agent/agent-model";

interface ActiveToolActivity {
  count: number;
  latestToolName: string;
}

interface AgentTranscriptPanelProps {
  activeToolActivity: ActiveToolActivity;
  agentRunPending: boolean;
  approvalDrafts: Record<string, ApprovalDraft>;
  composerPlaceholder: string;
  composerSendDisabled: boolean;
  filteredItems: TimelineItem[];
  handleKeyDown: (event: KeyboardEvent<HTMLTextAreaElement>) => void;
  input: string;
  logBlockItems: TimelineLogItem[];
  messagesEndRef: RefObject<HTMLDivElement | null>;
  pendingBlockingItem: TimelineItem | null;
  questionDrafts: Record<string, QuestionDraft>;
  sendMessage: () => Promise<void>;
  setApprovalDrafts: Dispatch<SetStateAction<Record<string, ApprovalDraft>>>;
  setInput: (value: string) => void;
  setQuestionDrafts: Dispatch<SetStateAction<Record<string, QuestionDraft>>>;
  streamingText: string;
  submitApproval: (item: TimelineItem, decision: "allow" | "deny", reason?: string) => Promise<void>;
  submitQuestion: (item: TimelineItem, options?: { selected?: string[]; customText?: string }) => Promise<void>;
  submittingEventId: string | null;
  timelineEntries: TimelineEntry[];
  transcriptFilter: TranscriptFilter;
  transcriptLoading: boolean;
  transcriptScrollRef: RefObject<HTMLDivElement | null>;
  useTimelineLayout: boolean;
}

function ActiveAgentWorkIndicator({
  activeToolActivity,
}: {
  activeToolActivity: ActiveToolActivity;
}) {
  return (
    <div
      className="flex justify-start"
      aria-label={`Agent working with ${activeToolActivity.count} active tool use ${activeToolActivity.count === 1 ? "call" : "calls"}`}
      aria-live="polite"
    >
      <div className="stream-card stream-card-agent agent-tool-activity w-full max-w-[960px] px-4 py-3 text-foreground">
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Code className="text-[10px] uppercase tracking-[0.18em]">Agent</Code>
            <StatusPill status="running" />
          </div>
          <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
            {activeToolActivity.count} tool use {activeToolActivity.count === 1 ? "call" : "calls"}
          </span>
        </div>
        <p className="text-sm leading-6 text-foreground">
          Agent is working through tool calls before the next response.
        </p>
        {activeToolActivity.latestToolName ? (
          <p className="mt-1 font-mono text-[11px] text-muted-foreground">
            Latest: {activeToolActivity.latestToolName}
          </p>
        ) : null}
      </div>
    </div>
  );
}

export function AgentTranscriptPanel({
  activeToolActivity,
  agentRunPending,
  approvalDrafts,
  composerPlaceholder,
  composerSendDisabled,
  filteredItems,
  handleKeyDown,
  input,
  logBlockItems,
  messagesEndRef,
  pendingBlockingItem,
  questionDrafts,
  sendMessage,
  setApprovalDrafts,
  setInput,
  setQuestionDrafts,
  streamingText,
  submitApproval,
  submitQuestion,
  submittingEventId,
  timelineEntries,
  transcriptFilter,
  transcriptLoading,
  transcriptScrollRef,
  useTimelineLayout,
}: AgentTranscriptPanelProps) {
  const activeAgentWorkIndicator = agentRunPending ? (
    <ActiveAgentWorkIndicator activeToolActivity={activeToolActivity} />
  ) : null;

  return (
    <SurfacePanel data-agent-stage="section" className="space-y-3 rounded-[1.35rem] px-3.5 py-3.5 sm:px-4 sm:py-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <SectionLabel>Thread</SectionLabel>
        <span className="sr-only">
          Conversation shows direct operator chat, Samantha handoffs, and Builder work.
        </span>
      </div>

      {transcriptLoading ? (
        <LoadingState label="Loading agent transcript..." />
      ) : filteredItems.length === 0 && !streamingText && !agentRunPending ? (
        <EmptyState label={transcriptFilter === "logs" ? "No raw builder log yet" : "No active transcript"} detail="Start a conversation. Interactive questions and approvals will appear inline in the thread." />
      ) : transcriptFilter === "logs" ? (
        <div ref={transcriptScrollRef} className="scroll-panel max-h-[calc(100vh-14rem)] overflow-y-auto pr-1">
          <LogBlock items={logBlockItems} emptyLabel="No log events for this session yet." maxHeight={560} />
        </div>
      ) : useTimelineLayout || transcriptFilter === "full" ? (
        <div ref={transcriptScrollRef} className="scroll-panel max-h-[calc(100vh-14rem)] overflow-y-auto pr-1">
          <AgentTimeline entries={timelineEntries} />
          <div className="mt-3 space-y-3">
            {activeAgentWorkIndicator}
          </div>
          <div ref={messagesEndRef} />
        </div>
      ) : (
        <div ref={transcriptScrollRef} className="scroll-panel max-h-[calc(100vh-14rem)] space-y-3 overflow-y-auto pr-1">
          {filteredItems.map(renderAgentThreadItem)}
          {streamingText ? (
            <div className="flex justify-start">
              <div className="stream-card stream-card-agent max-w-[74%] px-4 py-3 text-foreground">
                <Code className="mb-2 text-[10px] uppercase tracking-[0.18em]">Agent</Code>
                <p className="whitespace-pre-wrap text-sm leading-6">{streamingText}</p>
              </div>
            </div>
          ) : null}
          {activeAgentWorkIndicator}
          <div ref={messagesEndRef} />
        </div>
      )}

      <div className="border-t border-border/60 pt-3">
        {pendingBlockingItem ? (
          <div className="stream-inner-panel px-3 py-2" aria-label="Pending decision response" aria-live="polite">
            <div className="flex items-center gap-2">
              <StatusPill status="review_pending" />
              <span className="text-sm text-muted-foreground">
                Builder is blocked until you answer this decision.
              </span>
            </div>
            <div className="mt-3">
              <AgentDecisionActions
                item={pendingBlockingItem}
                questionDrafts={questionDrafts}
                approvalDrafts={approvalDrafts}
                submittingEventId={submittingEventId}
                setQuestionDrafts={setQuestionDrafts}
                setApprovalDrafts={setApprovalDrafts}
                submitQuestion={submitQuestion}
                submitApproval={submitApproval}
              />
            </div>
          </div>
        ) : (
          <div className="flex gap-2">
            <Textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={composerPlaceholder}
              className="min-h-11 flex-1 resize-none rounded-[1rem] bg-background/70 text-sm"
            />
            <Button
              aria-label="Send agent instruction"
              className="h-11 rounded-full px-3"
              onClick={() => void sendMessage()}
              disabled={composerSendDisabled}
            >
              <CornerDownLeft className="h-4 w-4" />
            </Button>
          </div>
        )}
      </div>
    </SurfacePanel>
  );
}
