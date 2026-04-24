import { useEffect, useState } from "react";
import type { RuntimePreferenceState } from "@/lib/types";

const STORAGE_KEY = "aab-runtime-preferences";

const DEFAULTS: RuntimePreferenceState = {
  boardDensity: "comfortable",
  agentInspectorDefault: "evidence",
  transcriptFilterDefault: "thread",
  compareDisplayMode: "split",
};

function readStoredPreferences(): RuntimePreferenceState {
  if (typeof window === "undefined") return DEFAULTS;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULTS;
    const parsed = JSON.parse(raw) as Partial<RuntimePreferenceState>;
    return { ...DEFAULTS, ...parsed };
  } catch {
    return DEFAULTS;
  }
}

export function useRuntimePreferences() {
  const [preferences, setPreferences] = useState<RuntimePreferenceState>(readStoredPreferences);

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(preferences));
  }, [preferences]);

  const updatePreferences = (patch: Partial<RuntimePreferenceState>) => {
    setPreferences((current) => ({ ...current, ...patch }));
  };

  return { preferences, updatePreferences };
}
