import { type Dispatch, type SetStateAction } from "react";
import { Textarea } from "@/components/ui/textarea";
import { Button, Input } from "@/design-system";
import {
  APPROVAL_EVENT_TYPES,
  decisionItemWasAnswered,
  normalizeQuestionOptions,
  operatorChoiceLabel,
  type ApprovalDraft,
  type QuestionDraft,
  type TimelineItem,
} from "@/features/agent/agent-model";

interface AgentDecisionActionsProps {
  item: TimelineItem;
  questionDrafts: Record<string, QuestionDraft>;
  approvalDrafts: Record<string, ApprovalDraft>;
  submittingEventId: string | null;
  setQuestionDrafts: Dispatch<SetStateAction<Record<string, QuestionDraft>>>;
  setApprovalDrafts: Dispatch<SetStateAction<Record<string, ApprovalDraft>>>;
  submitQuestion: (
    item: TimelineItem,
    override?: { selectedOptions?: string[]; customText?: string },
  ) => Promise<void>;
  submitApproval: (
    item: TimelineItem,
    decision: "allow" | "deny",
    overrideReason?: string,
  ) => Promise<void>;
}

export function AgentDecisionActions({
  item,
  questionDrafts,
  approvalDrafts,
  submittingEventId,
  setQuestionDrafts,
  setApprovalDrafts,
  submitQuestion,
  submitApproval,
}: AgentDecisionActionsProps) {
  if (decisionItemWasAnswered(item)) return null;

  if (item.type === "ask_user_question") {
    const draft = questionDrafts[item.id] ?? { selected: [], customText: "" };
    const options = normalizeQuestionOptions(item.payload.options).slice(0, 3);
    if (options.length === 0) {
      return (
        <div className="stream-inner-panel flex gap-2 p-2">
          <Textarea
            value={draft.customText}
            onChange={(event) =>
              setQuestionDrafts((current) => ({
                ...current,
                [item.id]: {
                  selected: current[item.id]?.selected ?? [],
                  customText: event.target.value,
                },
              }))
            }
            placeholder="Answer the agent"
            className="min-h-11 flex-1 resize-none rounded-[0.85rem] bg-background/70 text-sm"
          />
          <Button
            size="sm"
            className="h-11 rounded-full px-4"
            onClick={() => void submitQuestion(item)}
            disabled={submittingEventId === item.id}
          >
            Send
          </Button>
        </div>
      );
    }
    return (
      <div className="stream-inner-panel grid gap-2 p-2 sm:grid-cols-2" aria-label="Question choices">
        {options.map((option) => (
          <Button
            key={option.label}
            type="button"
            variant="outline"
            size="sm"
            title={option.description}
            className="h-auto justify-start rounded-[0.85rem] px-3 py-2 text-left text-[12px]"
            onClick={() => void submitQuestion(item, { selectedOptions: [option.label] })}
            disabled={submittingEventId === item.id}
          >
            <span className="min-w-0">
              <span className="block text-sm font-medium">{operatorChoiceLabel(option.label)}</span>
              {option.description ? (
                <span className="mt-1 block text-[12px] leading-5 text-muted-foreground">
                  {option.description}
                </span>
              ) : null}
            </span>
          </Button>
        ))}
        <div className="flex gap-2 sm:col-span-2">
          <Textarea
            value={draft.customText}
            onChange={(event) =>
              setQuestionDrafts((current) => ({
                ...current,
                [item.id]: {
                  selected: current[item.id]?.selected ?? [],
                  customText: event.target.value,
                },
              }))
            }
            placeholder="Other answer: type what you have in mind."
            className="min-h-10 flex-1 resize-none rounded-[0.85rem] bg-background/70 text-sm"
          />
          <Button
            size="sm"
            className="h-10 rounded-full px-4"
            onClick={() => void submitQuestion(item, { customText: draft.customText })}
            disabled={!draft.customText.trim() || submittingEventId === item.id}
          >
            Send
          </Button>
        </div>
      </div>
    );
  }

  if (APPROVAL_EVENT_TYPES.has(item.type)) {
    const draft = approvalDrafts[item.id] ?? { reason: "" };
    return (
      <div className="stream-inner-panel flex flex-wrap gap-2 p-2" aria-label="Approval choices">
        <Input
          value={draft.reason}
          onChange={(event) =>
            setApprovalDrafts((current) => ({ ...current, [item.id]: { reason: event.target.value } }))
          }
          placeholder="Optional note"
          className="h-10 min-w-[220px] flex-1 rounded-full bg-background/70"
        />
        <Button
          size="sm"
          className="h-10 rounded-full px-4"
          onClick={() => void submitApproval(item, "allow")}
          disabled={submittingEventId === item.id}
        >
          Approve
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="h-10 rounded-full px-4"
          onClick={() => void submitApproval(item, "deny")}
          disabled={submittingEventId === item.id}
        >
          Deny
        </Button>
      </div>
    );
  }

  return null;
}
