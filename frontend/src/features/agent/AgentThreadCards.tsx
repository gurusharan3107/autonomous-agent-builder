import { EditorialContent } from "@/components/EditorialContent";
import { Code, StatusPill } from "@/design-system";
import {
  APPROVAL_EVENT_TYPES,
  decisionItemWasAnswered,
  decisionTimelineStatus,
  formatTime,
  questionAnswerText,
  readablePayloadText,
  type TimelineItem,
} from "@/features/agent/agent-model";

export function renderAgentThreadItem(item: TimelineItem) {
  const time = formatTime(item.timestamp);
  if (item.type === "voice_operator_message" || item.type === "user_message") {
    const voiceDelegation = item.type === "user_message" && item.payload.source === "realtime_voice";
    return (
      <div key={item.id} className={voiceDelegation ? "flex justify-center" : "flex justify-end"}>
        <div
          className={
            voiceDelegation
              ? "stream-card stream-card-delegated w-full max-w-[960px] px-4 py-3 text-foreground"
              : "stream-card stream-card-operator w-full max-w-[960px] px-4 py-3"
          }
        >
          <div className="mb-2 flex items-center gap-2">
            <Code className="text-[10px] uppercase tracking-[0.18em]">
              {voiceDelegation ? "Samantha" : "Operator"}
            </Code>
            <span className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">{time}</span>
          </div>
          <p className="whitespace-pre-wrap text-sm leading-6">{String(item.payload.content ?? "")}</p>
        </div>
      </div>
    );
  }

  if (item.type === "assistant_message" || item.type === "run_error") {
    return (
      <div key={item.id} className="flex justify-start">
        <div className="stream-card stream-card-agent w-full max-w-[960px] px-4 py-3 text-foreground">
          <div className="mb-2 flex items-center gap-2">
            <Code className="text-[10px] uppercase tracking-[0.18em]">
              {item.type === "run_error" ? "Agent error" : "Agent"}
            </Code>
            <span className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">{time}</span>
          </div>
          <EditorialContent content={String(item.payload.content ?? "")} className="text-sm" />
        </div>
      </div>
    );
  }

  if (item.type === "ask_user_question") {
    const answered = decisionItemWasAnswered(item);
    const answerText = questionAnswerText(item);
    return (
      <div
        key={item.id}
        className="stream-card border-status-review/35 bg-[color:var(--status-review-soft)] px-4 py-3"
      >
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Code className="text-[10px] uppercase tracking-[0.18em]">Question</Code>
            <StatusPill status={decisionTimelineStatus(item)} />
          </div>
          <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
            {time}
          </span>
        </div>
        <p className="max-w-[76ch] text-sm leading-6 text-foreground">
          {readablePayloadText(item.payload.question ?? item.payload.summary)}
        </p>
        {answered && answerText ? (
          <div className="stream-inner-panel mt-3 px-3 py-2">
            <Code className="mb-1 text-[10px] uppercase tracking-[0.18em]">Answered with</Code>
            <p className="text-sm leading-6 text-foreground">{answerText}</p>
          </div>
        ) : null}
      </div>
    );
  }

  if (APPROVAL_EVENT_TYPES.has(item.type)) {
    return (
      <div
        key={item.id}
        className="stream-card border-status-review/35 bg-[color:var(--status-review-soft)] px-4 py-3"
      >
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Code className="text-[10px] uppercase tracking-[0.18em]">Approval needed</Code>
            <StatusPill status={decisionTimelineStatus(item)} />
          </div>
          <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
            {time}
          </span>
        </div>
        <p className="max-w-[76ch] text-sm leading-6 text-foreground">
          {readablePayloadText(item.payload.summary ?? item.payload.tool_name ?? item.payload.action) || "Approval requested"}
        </p>
      </div>
    );
  }

  return null;
}
