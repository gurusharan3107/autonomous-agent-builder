import { type RefObject } from "react";
import { Mic, MicOff } from "lucide-react";
import { AgentTimeline, type TimelineEntry } from "@/components/agent-native";
import { Textarea } from "@/components/ui/textarea";
import { Button, Code, EmptyState, SectionLabel, SurfacePanel } from "@/design-system";
import type {
  RealtimeVoiceMessage,
  VoiceMode,
  VoiceStatus,
} from "@/hooks/use-realtime-voice";

interface AgentVoicePanelProps {
  sessionId: string | null;
  voiceStatus: VoiceStatus;
  voiceMode: VoiceMode | null;
  voiceCallId: string | null;
  voiceError: string | null;
  voiceNotice: string | null;
  voiceEvents: string[];
  voiceMessages: RealtimeVoiceMessage[];
  voiceTimelineEntries: TimelineEntry[];
  realtimeTextDraft: string;
  realtimeTextError: string | null;
  realtimeTextSubmitting: boolean;
  realtimeTextInputRef: RefObject<HTMLTextAreaElement | null>;
  setRealtimeTextDraft: (value: string) => void;
  submitRealtimeText: (textOverride?: string) => Promise<void>;
  startVoiceSession: (options?: { sessionId?: string | null }) => Promise<void>;
  stopVoiceSession: () => void;
}

export function AgentVoicePanel({
  sessionId,
  voiceStatus,
  voiceMode,
  voiceCallId,
  voiceError,
  voiceNotice,
  voiceEvents,
  voiceMessages,
  voiceTimelineEntries,
  realtimeTextDraft,
  realtimeTextError,
  realtimeTextSubmitting,
  realtimeTextInputRef,
  setRealtimeTextDraft,
  submitRealtimeText,
  startVoiceSession,
  stopVoiceSession,
}: AgentVoicePanelProps) {
  const voiceButton = (
    <Button
      type="button"
      variant={voiceStatus === "connected" ? "destructive" : "outline"}
      size="sm"
      className="h-8 rounded-full px-3 text-[12px]"
      onClick={() => {
        if (voiceStatus === "connected" || voiceStatus === "connecting") {
          stopVoiceSession();
          return;
        }
        void startVoiceSession({ sessionId });
      }}
    >
      {voiceStatus === "connected" || voiceStatus === "connecting" ? (
        <MicOff className="mr-1.5 h-3.5 w-3.5" />
      ) : (
        <Mic className="mr-1.5 h-3.5 w-3.5" />
      )}
      {voiceStatus === "connecting"
        ? "Stop connecting"
        : voiceStatus === "connected"
          ? "Stop voice"
          : "Start voice"}
    </Button>
  );

  return (
    <SurfacePanel data-agent-stage="section" className="space-y-3 rounded-[1.35rem] px-3.5 py-3.5 sm:px-4 sm:py-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <SectionLabel>Voice</SectionLabel>
          <p className="mt-2 max-w-[68ch] text-sm leading-6 text-muted-foreground">
            Voice and typed Samantha turns stay here. Related Builder work stays visible in Conversation.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {voiceStatus === "connected" ? (
            <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
              {voiceMode === "text" ? "Text mode" : "Voice"} · {voiceCallId ? voiceCallId.slice(0, 8) : "live"}
            </span>
          ) : null}
          {voiceButton}
        </div>
      </div>

      {voiceError ? (
        <p className="stream-card stream-card-error px-3 py-2 text-sm text-status-blocked">{voiceError}</p>
      ) : null}

      {voiceNotice ? (
        <p className="stream-inner-panel px-3 py-2 text-sm text-muted-foreground">{voiceNotice}</p>
      ) : null}

      {voiceEvents.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {voiceEvents.slice(-4).map((event, index) => (
            <Code key={`${event}-${index}`} className="max-w-full truncate text-[10px] uppercase tracking-[0.14em]">
              {event}
            </Code>
          ))}
        </div>
      ) : null}

      {voiceMessages.length === 0 ? (
        <EmptyState
          label="No voice turns yet"
          detail="Start voice, then speak or type to Samantha. Related Builder work will also appear in Conversation."
        />
      ) : (
        <div className="scroll-panel max-h-[calc(100vh-14rem)] overflow-y-auto pr-1">
          <AgentTimeline entries={voiceTimelineEntries} />
        </div>
      )}

      {voiceStatus === "connected" || voiceStatus === "error" ? (
        <div className="border-t border-border/60 pt-3">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <Code className="text-[10px] uppercase tracking-[0.16em]">Realtime input</Code>
            <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
              {voiceStatus === "error" ? "Text fallback" : voiceMode === "text" ? "Text mode" : "Audio + text"}
            </span>
          </div>
          <div className="flex gap-2">
            <Textarea
              ref={realtimeTextInputRef}
              value={realtimeTextDraft}
              onChange={(event) => setRealtimeTextDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  if (realtimeTextSubmitting) return;
                  void submitRealtimeText(event.currentTarget.value);
                }
              }}
              disabled={realtimeTextSubmitting}
              placeholder={voiceMode === "text" ? "Type to Samantha" : "Speak or type to Samantha"}
              className="min-h-10 flex-1 resize-none rounded-[1rem] bg-background/70 text-sm"
            />
            <Button
              type="button"
              size="sm"
              className="h-10 rounded-full px-3"
              disabled={realtimeTextSubmitting}
              onClick={() => void submitRealtimeText()}
            >
              {realtimeTextSubmitting ? "Sending" : "Send"}
            </Button>
          </div>
          {realtimeTextError ? (
            <p className="mt-2 text-sm text-status-blocked">{realtimeTextError}</p>
          ) : null}
        </div>
      ) : null}
    </SurfacePanel>
  );
}
