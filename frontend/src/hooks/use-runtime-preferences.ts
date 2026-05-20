import { useEffect, useState } from "react";
import type { RuntimePreferenceState } from "@/lib/types";

const STORAGE_KEY = "aab-runtime-preferences";
const PREFERENCE_EVENT = "aab:runtime-preferences-changed";
const AGENT_DEFAULT_CHAT_MIGRATION_KEY = "aab:agent-default-chat-migrated";
const AGENT_TIMELINE_LAYOUT_MIGRATION_KEY = "aab:agent-timeline-layout-migrated";

const DEFAULTS: RuntimePreferenceState = {
  designTheme: "calm",
  designMode: "preset",
  designAccentHue: null,
  designAccentChroma: null,
  designDensity: null,
  designRadius: null,
  designDisplayFace: "preset",
  realtimeModel: "gpt-realtime-mini",
  realtimeVoice: "alloy",
  pushToTalkMode: "hold",
  inlineTranscript: "on",
  bindVoiceToCurrentSession: "on",
  destructiveActionPhrase: "required-before-dispatch",
  agentDefaultMode: "chat",
  boardDensity: "comfortable",
  agentInspectorDefault: "evidence",
  transcriptFilterDefault: "thread",
  transcriptLayout: "timeline",
  runTraceDefault: "thread",
  compareDisplayMode: "split",
};

function readStoredPreferences(): RuntimePreferenceState {
  if (typeof window === "undefined") return DEFAULTS;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return window.localStorage.getItem("aab-theme") === "dark"
        ? { ...DEFAULTS, designTheme: "operator" }
        : DEFAULTS;
    }
    const parsed = JSON.parse(raw) as Partial<RuntimePreferenceState>;
    let preferences = { ...DEFAULTS, ...parsed };
    let shouldPersistPreferences = false;
    if (
      parsed.agentDefaultMode === "trace"
      && !window.localStorage.getItem(AGENT_DEFAULT_CHAT_MIGRATION_KEY)
    ) {
      preferences = { ...preferences, agentDefaultMode: "chat" as const };
      shouldPersistPreferences = true;
    }
    if (
      preferences.transcriptLayout === "cards"
      && !window.localStorage.getItem(AGENT_TIMELINE_LAYOUT_MIGRATION_KEY)
    ) {
      preferences = { ...preferences, transcriptLayout: "timeline" as const };
      shouldPersistPreferences = true;
    }
    if (shouldPersistPreferences) {
      window.localStorage.setItem(AGENT_DEFAULT_CHAT_MIGRATION_KEY, "1");
      window.localStorage.setItem(AGENT_TIMELINE_LAYOUT_MIGRATION_KEY, "1");
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(preferences));
      return preferences;
    }
    window.localStorage.setItem(AGENT_DEFAULT_CHAT_MIGRATION_KEY, "1");
    window.localStorage.setItem(AGENT_TIMELINE_LAYOUT_MIGRATION_KEY, "1");
    return preferences;
  } catch {
    return DEFAULTS;
  }
}

export function useRuntimePreferences() {
  const [preferences, setPreferences] = useState<RuntimePreferenceState>(readStoredPreferences);

  useEffect(() => {
    const handlePreferenceEvent = (event: Event) => {
      const nextPreferences = (event as CustomEvent<RuntimePreferenceState>).detail;
      setPreferences(nextPreferences ?? readStoredPreferences());
    };
    const handleStorageEvent = (event: StorageEvent) => {
      if (event.key === STORAGE_KEY || event.key === "aab-theme") {
        setPreferences(readStoredPreferences());
      }
    };

    window.addEventListener(PREFERENCE_EVENT, handlePreferenceEvent);
    window.addEventListener("storage", handleStorageEvent);
    return () => {
      window.removeEventListener(PREFERENCE_EVENT, handlePreferenceEvent);
      window.removeEventListener("storage", handleStorageEvent);
    };
  }, []);

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(preferences));
  }, [preferences]);

  const updatePreferences = (patch: Partial<RuntimePreferenceState>) => {
    setPreferences((current) => {
      const nextPreferences = { ...current, ...patch };
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(nextPreferences));
      window.dispatchEvent(new CustomEvent(PREFERENCE_EVENT, { detail: nextPreferences }));
      return nextPreferences;
    });
  };

  return { preferences, updatePreferences };
}
