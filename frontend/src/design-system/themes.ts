import type { RuntimePreferenceState } from "@/lib/types";

export type DesignThemeId = RuntimePreferenceState["designTheme"];

export interface DesignThemePreset {
  id: DesignThemeId;
  name: string;
  tagline: string;
  hue: number;
  density: number;
  radius: number;
  mode: "light" | "dark";
  fontDisplay: "Newsreader" | "Geist";
  fontUi: "Geist";
  chroma?: number;
}

export const DESIGN_THEMES: DesignThemePreset[] = [
  {
    id: "calm",
    name: "Calm Paper",
    tagline: "Editorial · warm · cobalt",
    hue: 252,
    density: 1,
    radius: 10,
    mode: "light",
    fontDisplay: "Newsreader",
    fontUi: "Geist",
  },
  {
    id: "operator",
    name: "Operator",
    tagline: "Terminal · graphite · azure",
    hue: 212,
    density: 0.82,
    radius: 4,
    mode: "dark",
    fontDisplay: "Geist",
    fontUi: "Geist",
  },
  {
    id: "sage",
    name: "Sage Studio",
    tagline: "Original · teal · soft",
    hue: 180,
    density: 1,
    radius: 16,
    mode: "light",
    fontDisplay: "Newsreader",
    fontUi: "Geist",
  },
  {
    id: "ember",
    name: "Ember",
    tagline: "Warm · amber · cozy",
    hue: 28,
    density: 1.15,
    radius: 14,
    mode: "light",
    fontDisplay: "Newsreader",
    fontUi: "Geist",
  },
  {
    id: "midnight",
    name: "Midnight",
    tagline: "Cinematic · iris · dense",
    hue: 264,
    density: 0.82,
    radius: 8,
    mode: "dark",
    fontDisplay: "Newsreader",
    fontUi: "Geist",
  },
  {
    id: "paper",
    name: "Paper Mono",
    tagline: "Stripped · neutral · 0 chroma",
    hue: 0,
    density: 1,
    radius: 6,
    mode: "light",
    fontDisplay: "Geist",
    fontUi: "Geist",
    chroma: 0,
  },
];

export function getDesignTheme(id: DesignThemeId): DesignThemePreset {
  return DESIGN_THEMES.find((theme) => theme.id === id) ?? DESIGN_THEMES[0];
}

export function resolveDesignTheme(preferences: RuntimePreferenceState): DesignThemePreset {
  const preset = getDesignTheme(preferences.designTheme);
  return {
    ...preset,
    hue: preferences.designAccentHue ?? preset.hue,
    chroma: preferences.designAccentChroma ?? preset.chroma,
    density: preferences.designDensity ?? preset.density,
    radius: preferences.designRadius ?? preset.radius,
    mode: preferences.designMode === "preset" ? preset.mode : preferences.designMode,
    fontDisplay: preferences.designDisplayFace === "preset" ? preset.fontDisplay : preferences.designDisplayFace,
  };
}
