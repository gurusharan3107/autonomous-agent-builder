import type { CSSProperties, KeyboardEvent as ReactKeyboardEvent, ReactNode } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Navigate, NavLink, Route, Routes, useNavigate } from "react-router-dom";
import {
  GitCompare,
  Inbox,
  Moon,
  Search,
  Settings2,
  Sparkles,
  Sun,
} from "lucide-react";
import { Button } from "@/design-system";
import { Input } from "@/design-system";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  fetchCommandIndex,
  fetchOnboardingStatus,
  fetchRuntimeSettings,
  fetchShellSummary,
  openOnboardingStream,
  retryOnboarding,
  startOnboarding,
  dispatchTask,
  updateRuntimeSettings,
} from "@/lib/api";
import type {
  CommandPaletteItem,
  OnboardingStatus,
  RuntimePreferenceState,
  RuntimeSdk,
  RuntimeSettings,
  ShellSummary,
} from "@/lib/types";
import AgentPage from "@/pages/AgentPage";
import ApprovalPage from "@/pages/ApprovalPage";
import BacklogPage from "@/pages/BacklogPage";
import BoardPage from "@/pages/BoardPage";
import ComparePage from "@/pages/ComparePage";
import InboxPage from "@/pages/InboxPage";
import KnowledgePage from "@/pages/KnowledgePage";
import MemoryPage from "@/pages/MemoryPage";
import MetricsPage from "@/pages/MetricsPage";
import ObservabilityPage from "@/pages/ObservabilityPage";
import OnboardingPage from "@/pages/OnboardingPage";
import { useRuntimePreferences } from "@/hooks/use-runtime-preferences";
import { RealtimeVoiceProvider } from "@/hooks/use-realtime-voice";
import { SamanthaVoiceOrb } from "@/components/SamanthaVoiceOrb";
import { BrandMark, PageFrame, PageHeader, StatusDot, SurfacePanel } from "@/design-system";
import { DESIGN_THEMES, resolveDesignTheme, type DesignThemeId } from "@/design-system";

const NAV_ITEMS = [
  { to: "/", label: "Agent", end: true },
  { to: "/board", label: "Board", end: false },
  { to: "/metrics", label: "Metrics", end: false },
  { to: "/observability", label: "Observability", end: false },
  { to: "/knowledge", label: "Knowledge", end: false },
  { to: "/memory", label: "Memory", end: false },
  { to: "/backlog", label: "Backlog", end: false },
  { to: "/settings", label: "Settings", end: false },
] as const;

const ROUTE_JUMPS: Record<string, string> = {
  a: "/",
  b: "/board",
  m: "/metrics",
  o: "/observability",
  k: "/knowledge",
  y: "/memory",
  l: "/backlog",
  s: "/settings",
  i: "/inbox",
  c: "/compare",
};

function ThemeToggle({
  mode,
  onModeChange,
}: {
  mode: "light" | "dark";
  onModeChange: (mode: "light" | "dark") => void;
}) {
  const dark = mode === "dark";
  return (
    <Button
      variant="secondary"
      size="icon"
      onClick={() => onModeChange(dark ? "light" : "dark")}
      className="h-9 w-9 rounded-full border-border/75 bg-background/74"
      aria-label="Toggle theme"
    >
      {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
    </Button>
  );
}

function ShellBrand() {
  return (
    <div className="flex min-w-0 items-center gap-3">
      <BrandMark />
      <div className="min-w-0 leading-none">
        <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
          Autonomous Agent Builder
        </p>
      </div>
    </div>
  );
}

function NavPills() {
  return (
    <nav className="hidden items-center gap-1 rounded-full border border-border/75 bg-background/70 p-1.5 lg:flex">
      {NAV_ITEMS.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          className={({ isActive }) =>
            [
              "rounded-full px-4 py-1.5 text-[12px] font-medium transition-colors",
              isActive ? "bg-foreground text-background shadow-[var(--shadow-md)]" : "text-muted-foreground hover:text-foreground",
            ].join(" ")
          }
        >
          {item.label}
        </NavLink>
      ))}
    </nav>
  );
}

function UtilityButton({
  icon,
  label,
  value,
  pulse = false,
  onClick,
  className = "",
}: {
  icon: ReactNode;
  label: string;
  value?: string;
  pulse?: boolean;
  onClick: () => void;
  className?: string;
}) {
  return (
    <Button
      type="button"
      variant="secondary"
      size="icon"
      className={`relative h-8 w-8 rounded-full border-border/75 bg-background/72 text-[12px] font-medium ${className}`}
      onClick={onClick}
      aria-label={label}
      title={value ? `${label} ${value}` : label}
    >
      <span className="text-muted-foreground">{icon}</span>
      {pulse ? <StatusDot tone="active" pulse className="absolute -right-0.5 -top-0.5 h-2 w-2" /> : null}
      {value && value !== "0" ? (
        <span className="absolute -right-1 -top-1 min-w-[1rem] rounded-full bg-foreground px-1 text-center font-mono text-[9px] leading-4 text-background">
          {value}
        </span>
      ) : null}
    </Button>
  );
}

function CommandSearchButton({ onClick }: { onClick: () => void }) {
  return (
    <Button
      type="button"
      variant="secondary"
      size="icon"
      onClick={onClick}
      aria-label="Open command palette"
      title="Command palette"
      className="hidden h-8 w-8 items-center justify-center rounded-full border border-border/75 bg-background-sunk/75 text-muted-foreground transition hover:bg-background md:inline-flex"
    >
      <Search className="h-3.5 w-3.5" />
    </Button>
  );
}

function shouldIgnoreHotkeys(target: EventTarget | null) {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName.toLowerCase();
  return tag === "input" || tag === "textarea" || tag === "select" || target.isContentEditable;
}

function CommandPaletteDialog({
  open,
  onOpenChange,
  items,
  loading,
  onSelect,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  items: CommandPaletteItem[];
  loading: boolean;
  onSelect: (item: CommandPaletteItem) => void;
}) {
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);

  const handleOpenChange = (next: boolean) => {
    if (!next) {
      setQuery("");
      setActiveIndex(0);
    }
    onOpenChange(next);
  };

  const filteredItems = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return items;
    return items.filter((item) =>
      [item.label, item.description, item.kind].some((value) => value.toLowerCase().includes(normalized)),
      );
    }, [items, query]);

  const groupedItems = useMemo(() => {
    const groups = new Map<string, CommandPaletteItem[]>();
    filteredItems.forEach((item) => {
      const groupName = item.kind.replaceAll("_", " ");
      groups.set(groupName, [...(groups.get(groupName) ?? []), item]);
    });
    return Array.from(groups.entries()).map(([groupName, groupItems]) => ({ groupName, groupItems }));
  }, [filteredItems]);

  const selectedIndex = Math.min(activeIndex, Math.max(filteredItems.length - 1, 0));

  const handleKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      handleOpenChange(false);
      return;
    }
    if (filteredItems.length === 0) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((current) => Math.min(current + 1, filteredItems.length - 1));
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((current) => Math.max(current - 1, 0));
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      onSelect(filteredItems[selectedIndex] ?? filteredItems[0]);
    }
  };

  let renderedIndex = 0;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent
        className="max-w-2xl rounded-[1.5rem] p-0"
        showCloseButton={false}
        onKeyDown={handleKeyDown}
      >
        <div className="border-b border-border/70 px-5 py-4">
          <DialogHeader>
            <DialogTitle>Command palette</DialogTitle>
            <DialogDescription>Jump to routes, resume sessions, review approvals, or dispatch a task.</DialogDescription>
          </DialogHeader>
          <div className="mt-4">
            <Input
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
                setActiveIndex(0);
              }}
              placeholder="Search routes, sessions, approvals, or tasks"
              className="h-11 rounded-full border-border/80 bg-background/70"
              autoFocus
            />
          </div>
        </div>
        <div className="max-h-[60vh] overflow-y-auto p-4">
          {loading ? (
            <div className="px-2 py-10 text-sm text-muted-foreground">Loading command index...</div>
          ) : filteredItems.length === 0 ? (
            <div className="px-2 py-10 text-sm text-muted-foreground">No command matches the current filter.</div>
          ) : (
            <div className="space-y-4">
              {groupedItems.map(({ groupName, groupItems }) => (
                <section key={groupName} aria-label={groupName} className="space-y-2">
                  <p className="px-2 font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                    {groupName}
                  </p>
                  {groupItems.map((item) => {
                    const itemIndex = renderedIndex;
                    renderedIndex += 1;
                    const selected = itemIndex === selectedIndex;
                    return (
                      <button
                        key={item.id}
                        type="button"
                        onMouseEnter={() => setActiveIndex(itemIndex)}
                        onClick={() => onSelect(item)}
                        aria-selected={selected}
                        className={[
                          "w-full rounded-[1rem] border px-4 py-3 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                          selected
                            ? "border-primary/50 bg-primary-soft text-primary-ink"
                            : "border-border/70 bg-background/60 hover:border-border hover:bg-background/85",
                        ].join(" ")}
                      >
                        <div className="flex items-center justify-between gap-3">
                          <div>
                            <p className="text-sm font-medium text-foreground">{item.label}</p>
                            <p className="text-xs text-muted-foreground">{item.description}</p>
                          </div>
                          <span className="text-[10px] uppercase tracking-[0.16em] text-muted-foreground">{item.kind}</span>
                        </div>
                      </button>
                    );
                  })}
                </section>
              ))}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

function ThemePresetSelect({
  value,
  onChange,
}: {
  value: DesignThemeId;
  onChange: (value: DesignThemeId) => void;
}) {
  return (
    <div className="rounded-[var(--radius-lg)] border border-border/70 bg-background/55 p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-foreground">Theme presets</p>
          <p className="mt-1 text-xs text-muted-foreground">
            Sets the Builder token knobs for hue, density, radius, display face, and color mode.
          </p>
        </div>
        <span className="rounded-full border border-border/70 bg-background-sunk px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
          {value}
        </span>
      </div>
      <div className="mt-4 grid gap-2 sm:grid-cols-2">
        {DESIGN_THEMES.map((theme) => {
          const active = value === theme.id;
          const swatchStyle = {
            "--swatch-accent": `oklch(${theme.mode === "dark" ? 0.72 : 0.48} ${theme.chroma ?? 0.14} ${theme.hue})`,
          } as CSSProperties;
          return (
            <Button
              key={theme.id}
              type="button"
              variant={active ? "default" : "outline"}
              aria-pressed={active}
              className="h-auto justify-start rounded-[var(--radius-md)] px-3 py-3 text-left"
              onClick={() => onChange(theme.id)}
            >
              <span className="theme-swatch h-7 w-7 shrink-0 rounded-[var(--radius-sm)] border border-foreground/10" style={swatchStyle} />
              <span className="min-w-0">
                <span className="block truncate text-sm leading-tight">{theme.name}</span>
                <span className="block truncate text-[10px] font-normal uppercase tracking-[0.14em] opacity-70">
                  {theme.tagline}
                </span>
              </span>
            </Button>
          );
        })}
      </div>
    </div>
  );
}

function DesignRangeControl({
  label,
  value,
  min,
  max,
  step,
  suffix = "",
  overridden,
  onChange,
  onReset,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  suffix?: string;
  overridden: boolean;
  onChange: (value: number) => void;
  onReset: () => void;
}) {
  const displayValue = Number.isInteger(step)
    ? String(Math.round(value))
    : value.toFixed(2);
  return (
    <div className="rounded-[var(--radius-md)] border border-border/70 bg-background/55 p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-medium text-foreground">{label}</p>
          <p className="mt-1 font-mono text-[11px] text-muted-foreground">
            {displayValue}{suffix} {overridden ? "override" : "preset"}
          </p>
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="h-8 rounded-full px-3"
          onClick={onReset}
          disabled={!overridden}
        >
          Reset
        </Button>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        className="mt-3 w-full accent-foreground"
        aria-label={label}
      />
    </div>
  );
}

function RuntimeMetricRow({
  label,
  value,
  tone = "muted",
}: {
  label: string;
  value: string;
  tone?: "active" | "review" | "pending" | "done" | "blocked" | "muted";
}) {
  return (
    <div className="flex min-w-0 items-center justify-between gap-3 rounded-[0.9rem] border border-border/70 bg-background/60 px-3 py-2">
      <span className="inline-flex min-w-0 items-center gap-2">
        <StatusDot tone={tone} className="h-1.5 w-1.5" />
        <span className="truncate text-[10px] uppercase tracking-[0.16em] text-muted-foreground">{label}</span>
      </span>
      <span className="max-w-[8rem] truncate text-right font-mono text-[11px] text-foreground">{value}</span>
    </div>
  );
}

function SettingsSection({
  id,
  eyebrow,
  title,
  description,
  children,
}: {
  id: string;
  eyebrow: string;
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <section
      id={id}
      className="grid gap-5 border-b border-border/70 pb-7 lg:grid-cols-[280px_minmax(0,1fr)] lg:gap-10"
      data-board-section
    >
      <div>
        <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">{eyebrow}</p>
        <h2 className="mt-3 max-w-[14rem] text-[1.45rem] font-semibold leading-[1.16] tracking-normal text-foreground">
          {title}
        </h2>
        <p className="mt-3 max-w-[30ch] text-sm leading-6 text-muted-foreground">{description}</p>
      </div>
      <SurfacePanel className="space-y-4 p-5">{children}</SurfacePanel>
    </section>
  );
}

function SettingsChoiceRow({
  label,
  hint,
  value,
  options,
  onChange,
}: {
  label: string;
  hint?: string;
  value: string;
  options: Array<{ label: string; value: string }>;
  onChange: (value: string) => void;
}) {
  return (
    <div className="grid gap-3 border-b border-border/45 py-2 last:border-b-0 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
      <div>
        <p className="text-sm font-medium text-foreground">{label}</p>
        {hint ? <p className="mt-1 text-xs leading-5 text-muted-foreground">{hint}</p> : null}
      </div>
      <div className="inline-flex w-fit flex-wrap rounded-full border border-border/70 bg-background-sunk p-1">
        {options.map((option) => (
          <Button
            key={option.value}
            type="button"
            variant={value === option.value ? "default" : "ghost"}
            aria-pressed={value === option.value}
            className="h-8 rounded-full px-3 text-xs"
            onClick={() => onChange(option.value)}
          >
            {option.label}
          </Button>
        ))}
      </div>
    </div>
  );
}

function SettingsPage({
  runtimeSettings,
  runtimePending,
  onRuntimeSelect,
}: {
  runtimeSettings: RuntimeSettings | null;
  runtimePending: boolean;
  onRuntimeSelect: (sdk: RuntimeSdk) => void;
}) {
  const { preferences, updatePreferences } = useRuntimePreferences();
  const [summary, setSummary] = useState<ShellSummary | null>(null);
  const activeTheme = resolveDesignTheme(preferences);

  useEffect(() => {
    let cancelled = false;
    const loadSummary = async () => {
      try {
        const nextSummary = await fetchShellSummary();
        if (!cancelled) setSummary(nextSummary);
      } catch (error) {
        console.error("Failed to load settings summary:", error);
      }
    };

    void loadSummary();
    const interval = window.setInterval(() => void loadSummary(), 15000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, []);

  return (
    <PageFrame variant="overview" data-screen-label="Settings" className="mx-auto max-w-[1400px] space-y-7">
      <PageHeader
        eyebrow="Workspace · Settings"
        title="Settings"
        description="Tune voice transport, board density, Agent surface defaults, runtime lane, and appearance tokens. Preferences persist across sessions."
        aside={
          <a
            href="#voice"
            className="rounded-full border border-border/70 bg-surface px-3 py-2 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground no-underline"
          >
            Jump to voice ↓
          </a>
        }
      />

      <SettingsSection
        id="voice"
        eyebrow="01 - Voice & Realtime"
        title="Voice transport"
        description="Voice rides on top of the Agent surface. Utterances merge into the same timeline as text, with confirmation safeguards for destructive actions."
      >
        <div className="mb-2 flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-full bg-status-done-bg text-sm font-medium text-status-done-fg">●</span>
          <div>
            <p className="text-sm font-medium text-foreground">Idle</p>
            <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">No active call</p>
          </div>
        </div>
        <SettingsChoiceRow
          label="Realtime model"
          hint="Selects the realtime voice model for new operator sessions."
          value={preferences.realtimeModel}
          options={[
            { label: "Realtime mini", value: "gpt-realtime-mini" },
            { label: "Realtime", value: "gpt-realtime" },
          ]}
          onChange={(value) => updatePreferences({ realtimeModel: value as RuntimePreferenceState["realtimeModel"] })}
        />
        <SettingsChoiceRow
          label="Voice timbre"
          hint="Sets the default voice timbre for realtime sessions."
          value={preferences.realtimeVoice}
          options={[
            { label: "Alloy", value: "alloy" },
            { label: "Verse", value: "verse" },
            { label: "Cedar", value: "cedar" },
          ]}
          onChange={(value) => updatePreferences({ realtimeVoice: value as RuntimePreferenceState["realtimeVoice"] })}
        />
        <SettingsChoiceRow
          label="Push-to-talk"
          hint="Hold space to talk, or toggle continuous capture."
          value={preferences.pushToTalkMode}
          options={[
            { label: "Hold", value: "hold" },
            { label: "Toggle", value: "toggle" },
          ]}
          onChange={(value) => updatePreferences({ pushToTalkMode: value as RuntimePreferenceState["pushToTalkMode"] })}
        />
        <SettingsChoiceRow
          label="Show inline transcript"
          hint="Render voice utterances in the Agent timeline."
          value={preferences.inlineTranscript}
          options={[
            { label: "On", value: "on" },
            { label: "Off", value: "off" },
          ]}
          onChange={(value) => updatePreferences({ inlineTranscript: value as RuntimePreferenceState["inlineTranscript"] })}
        />
        <SettingsChoiceRow
          label="Bind to current session"
          hint="Continue the open Agent session over voice instead of starting fresh."
          value={preferences.bindVoiceToCurrentSession}
          options={[
            { label: "On", value: "on" },
            { label: "Off", value: "off" },
          ]}
          onChange={(value) =>
            updatePreferences({ bindVoiceToCurrentSession: value as RuntimePreferenceState["bindVoiceToCurrentSession"] })
          }
        />
        <SettingsChoiceRow
          label="Require confirmation phrase for destructive actions"
          hint="Voice AI must hear an exact phrase before running destructive tools."
          value={preferences.destructiveActionPhrase}
          options={[
            { label: "Required", value: "required-before-dispatch" },
            { label: "Typed", value: "typed-confirmation" },
          ]}
          onChange={(value) =>
            updatePreferences({ destructiveActionPhrase: value as RuntimePreferenceState["destructiveActionPhrase"] })
          }
        />
      </SettingsSection>

      <SettingsSection
        id="board"
        eyebrow="02 - Board & Layout"
        title="Board density and surface modes"
        description="Default layout decisions persist across sessions and apply per surface."
      >
        <SettingsChoiceRow
          label="Board density"
          hint="Card padding and row height on the Board surface."
          value={preferences.boardDensity}
          options={[
            { label: "Comfortable", value: "comfortable" },
            { label: "Compact", value: "compact" },
          ]}
          onChange={(value) => updatePreferences({ boardDensity: value as RuntimePreferenceState["boardDensity"] })}
        />
        <SettingsChoiceRow
          label="Transcript layout"
          hint="How agent timeline events stack inside the Agent page."
          value={preferences.transcriptLayout}
          options={[
            { label: "Timeline", value: "timeline" },
            { label: "Cards", value: "cards" },
          ]}
          onChange={(value) => updatePreferences({ transcriptLayout: value as RuntimePreferenceState["transcriptLayout"] })}
        />
        <SettingsChoiceRow
          label="Compare display"
          hint="Default comparison layout when two runs are pinned."
          value={preferences.compareDisplayMode}
          options={[
            { label: "Split", value: "split" },
            { label: "Stacked", value: "stacked" },
          ]}
          onChange={(value) => updatePreferences({ compareDisplayMode: value as RuntimePreferenceState["compareDisplayMode"] })}
        />
      </SettingsSection>

      <SettingsSection
        id="agent"
        eyebrow="03 - Agent Surface"
        title="Inspector and transcript defaults"
        description="Defaults applied when the Agent page mounts. Per-session overrides still win."
      >
        <SettingsChoiceRow
          label="Agent default mode"
          hint="Which Agent surface opens when no route mode is specified."
          value={preferences.agentDefaultMode}
          options={[
            { label: "Conversation", value: "chat" },
            { label: "Run trace", value: "trace" },
          ]}
          onChange={(value) => updatePreferences({ agentDefaultMode: value as RuntimePreferenceState["agentDefaultMode"] })}
        />
        <SettingsChoiceRow
          label="Inspector default tab"
          hint="Sets the default right-rail inspector on the Agent page."
          value={preferences.agentInspectorDefault}
          options={[
            { label: "Evidence", value: "evidence" },
            { label: "Sessions", value: "sessions" },
          ]}
          onChange={(value) =>
            updatePreferences({ agentInspectorDefault: value as RuntimePreferenceState["agentInspectorDefault"] })
          }
        />
        <SettingsChoiceRow
          label="Transcript filter"
          hint="Sets the default transcript filter on the Agent page."
          value={preferences.transcriptFilterDefault}
          options={[
            { label: "Thread", value: "thread" },
            { label: "Full", value: "full" },
            { label: "Logs", value: "logs" },
          ]}
          onChange={(value) =>
            updatePreferences({ transcriptFilterDefault: value as RuntimePreferenceState["transcriptFilterDefault"] })
          }
        />
        <SettingsChoiceRow
          label="Run trace default"
          hint="Chooses the preferred trace tab for task-owned runs."
          value={preferences.runTraceDefault}
          options={[
            { label: "Thread", value: "thread" },
            { label: "Raw log", value: "raw" },
            { label: "Full trace", value: "full" },
          ]}
          onChange={(value) => updatePreferences({ runTraceDefault: value as RuntimePreferenceState["runTraceDefault"] })}
        />
      </SettingsSection>

      <SettingsSection
        id="runtime"
        eyebrow="04 - Runtime"
        title="Runtime lane"
        description="Future runs use the selected SDK. Historical state keeps the runtime that created it."
      >
        <SettingsChoiceRow
          label="Runtime SDK"
          hint="Selects the agent execution harness for future chats and task runs."
          value={runtimeSettings?.sdk ?? "claude"}
          options={[
            { label: "Claude Agent SDK", value: "claude" },
            { label: "Codex SDK", value: "codex_sdk" },
          ]}
          onChange={(value) => {
            if (!runtimePending) onRuntimeSelect(value as RuntimeSdk);
          }}
        />
        <div className="grid gap-2 sm:grid-cols-2">
          <RuntimeMetricRow label="Model" value={runtimeSettings?.model ?? "unknown"} />
          <RuntimeMetricRow label="Telemetry" value={runtimeSettings?.telemetry?.active_lane ?? "unknown"} />
          <RuntimeMetricRow label="Running" value={summary?.running_label ?? "0 running"} tone="active" />
          <RuntimeMetricRow label="Approvals" value={String(summary?.pending_approvals ?? 0)} tone="review" />
          <RuntimeMetricRow label="Questions" value={String(summary?.pending_questions ?? 0)} tone="review" />
          <RuntimeMetricRow label="Tokens" value={(summary?.total_tokens ?? 0).toLocaleString()} />
        </div>
      </SettingsSection>

      <SettingsSection
        id="appearance"
        eyebrow="05 - Appearance"
        title="Theme and design tokens"
        description="Theme presets and advanced token controls live here so appearance changes stay in the durable Settings hierarchy."
      >
        <ThemePresetSelect
          value={preferences.designTheme}
          onChange={(value) =>
            updatePreferences({
              designTheme: value,
              designAccentHue: null,
              designAccentChroma: null,
              designDensity: null,
              designRadius: null,
              designDisplayFace: "preset",
              designMode: "preset",
            })
          }
        />
        <div className="grid gap-4 xl:grid-cols-2">
          <SettingsChoiceRow
            label="Color mode"
            hint="Preset follows the selected theme. Light and dark override only the mode token."
            value={preferences.designMode}
            options={[
              { label: "Preset", value: "preset" },
              { label: "Light", value: "light" },
              { label: "Dark", value: "dark" },
            ]}
            onChange={(value) => updatePreferences({ designMode: value as RuntimePreferenceState["designMode"] })}
          />
          <SettingsChoiceRow
            label="Display face"
            hint="Controls the dashboard display heading family without changing body text."
            value={preferences.designDisplayFace}
            options={[
              { label: "Preset", value: "preset" },
              { label: "Newsreader", value: "Newsreader" },
              { label: "Geist", value: "Geist" },
            ]}
            onChange={(value) =>
              updatePreferences({ designDisplayFace: value as RuntimePreferenceState["designDisplayFace"] })
            }
          />
        </div>
        <div className="grid gap-4 xl:grid-cols-2">
          <DesignRangeControl
            label="Accent hue"
            value={preferences.designAccentHue ?? activeTheme.hue}
            min={0}
            max={360}
            step={1}
            suffix="deg"
            overridden={preferences.designAccentHue !== null}
            onChange={(value) => updatePreferences({ designAccentHue: value })}
            onReset={() => updatePreferences({ designAccentHue: null })}
          />
          <DesignRangeControl
            label="Accent chroma"
            value={preferences.designAccentChroma ?? activeTheme.chroma ?? 0.14}
            min={0}
            max={0.22}
            step={0.01}
            overridden={preferences.designAccentChroma !== null}
            onChange={(value) => updatePreferences({ designAccentChroma: value })}
            onReset={() => updatePreferences({ designAccentChroma: null })}
          />
          <DesignRangeControl
            label="Density"
            value={preferences.designDensity ?? activeTheme.density}
            min={0.78}
            max={1.22}
            step={0.01}
            overridden={preferences.designDensity !== null}
            onChange={(value) => updatePreferences({ designDensity: value })}
            onReset={() => updatePreferences({ designDensity: null })}
          />
          <DesignRangeControl
            label="Radius"
            value={preferences.designRadius ?? activeTheme.radius}
            min={4}
            max={16}
            step={1}
            suffix="px"
            overridden={preferences.designRadius !== null}
            onChange={(value) => updatePreferences({ designRadius: value })}
            onReset={() => updatePreferences({ designRadius: null })}
          />
        </div>
      </SettingsSection>
    </PageFrame>
  );
}

function AppShell({
  ready,
  children,
}: {
  ready: boolean;
  children: ReactNode;
}) {
  const navigate = useNavigate();
  const { preferences, updatePreferences } = useRuntimePreferences();
  const [commandOpen, setCommandOpen] = useState(false);
  const [shellSummary, setShellSummary] = useState<ShellSummary | null>(null);
  const [commandItems, setCommandItems] = useState<CommandPaletteItem[]>([]);
  const [commandLoading, setCommandLoading] = useState(false);
  const [shellCondensed, setShellCondensed] = useState(false);
  const jumpAwaitingRef = useRef(false);
  const jumpTimeoutRef = useRef<number | null>(null);
  const activeTheme = resolveDesignTheme(preferences);

  useEffect(() => {
    const root = document.documentElement;
    root.dataset.builderTheme = activeTheme.id;
    root.dataset.theme = activeTheme.mode;
    root.classList.toggle("dark", activeTheme.mode === "dark");
    root.style.setProperty("--accent-hue", String(activeTheme.hue));
    root.style.setProperty("--accent-chroma", String(activeTheme.chroma ?? 0.14));
    root.style.setProperty("--density", String(activeTheme.density));
    root.style.setProperty("--radius-base", `${activeTheme.radius}px`);
    root.style.setProperty(
      "--font-heading",
      activeTheme.fontDisplay === "Geist" ? '"Geist Sans", ui-sans-serif, system-ui, sans-serif' : '"Newsreader", serif',
    );
    localStorage.setItem("aab-theme", activeTheme.mode);
    localStorage.setItem("aab-design-theme", activeTheme.id);
  }, [activeTheme]);

  useEffect(() => {
    if (!ready) return;
    let cancelled = false;
    const loadSummary = async () => {
      try {
        const summary = await fetchShellSummary();
        if (!cancelled) {
          setShellSummary(summary);
        }
      } catch (error) {
        console.error("Failed to load shell summary:", error);
      }
    };

    void loadSummary();
    const interval = window.setInterval(() => void loadSummary(), 15000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [ready]);

  useEffect(() => {
    if (!commandOpen || commandItems.length > 0) return;
    let cancelled = false;
    const loadIndex = async () => {
      setCommandLoading(true);
      try {
        const payload = await fetchCommandIndex();
        if (!cancelled) setCommandItems(payload.items);
      } catch (error) {
        console.error("Failed to load command index:", error);
      } finally {
        if (!cancelled) setCommandLoading(false);
      }
    };
    void loadIndex();
    return () => {
      cancelled = true;
    };
  }, [commandItems.length, commandOpen]);

  useEffect(() => {
    const onScroll = () => {
      setShellCondensed(window.scrollY > 24);
    };

    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (shouldIgnoreHotkeys(event.target)) return;
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setCommandOpen(true);
        return;
      }
      if (!event.metaKey && !event.ctrlKey && event.key === "?") {
        event.preventDefault();
        navigate("/settings");
        return;
      }
      if (!event.metaKey && !event.ctrlKey && event.key.toLowerCase() === "g") {
        jumpAwaitingRef.current = true;
        if (jumpTimeoutRef.current) window.clearTimeout(jumpTimeoutRef.current);
        jumpTimeoutRef.current = window.setTimeout(() => {
          jumpAwaitingRef.current = false;
        }, 1200);
        return;
      }
      if (jumpAwaitingRef.current) {
        const destination = ROUTE_JUMPS[event.key.toLowerCase()];
        if (destination) {
          event.preventDefault();
          navigate(destination);
        }
        jumpAwaitingRef.current = false;
        if (jumpTimeoutRef.current) window.clearTimeout(jumpTimeoutRef.current);
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      if (jumpTimeoutRef.current) window.clearTimeout(jumpTimeoutRef.current);
    };
  }, [navigate]);

  const handleCommandSelect = async (item: CommandPaletteItem) => {
    setCommandOpen(false);
    if (item.action === "dispatch" && item.task_id) {
      try {
        await dispatchTask(item.task_id);
        const summary = await fetchShellSummary();
        setShellSummary(summary);
        navigate("/board");
      } catch (error) {
        console.error("Failed to dispatch task from command palette:", error);
      }
      return;
    }
    if (item.route) {
      navigate(item.route);
    }
  };

  const activeRuns = shellSummary?.active_run_count ?? 0;
  const pendingApprovals = shellSummary?.pending_approvals ?? 0;
  return (
    <RealtimeVoiceProvider>
      <div className="min-h-screen text-foreground">
      <div className="relative min-h-screen">
        <a
          href="#dashboard-main"
          className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:rounded-full focus:border focus:border-[var(--line-strong)] focus:bg-[var(--surface-raised)] focus:px-4 focus:py-2 focus:font-mono focus:text-[11px] focus:uppercase focus:tracking-[0.14em] focus:text-foreground focus:shadow-[var(--shadow-md)]"
        >
          Skip to dashboard
        </a>
        <header
          className={[
            "sticky top-0 z-40 transition-all duration-200",
            shellCondensed
              ? "border-b border-transparent bg-transparent backdrop-blur-0"
              : "border-b border-transparent bg-transparent backdrop-blur-0",
          ].join(" ")}
        >
          <div
            className={[
              "mx-auto grid max-w-[1440px] grid-cols-[1fr_auto] items-center gap-3 px-4 sm:px-6 lg:grid-cols-[1fr_auto_1fr] lg:gap-4",
              shellCondensed ? "py-2" : "py-3",
            ].join(" ")}
          >
            <div
              className={[
                "min-w-0 justify-self-start transition-all duration-200",
                shellCondensed ? "pointer-events-none translate-y-[-4px] opacity-0" : "translate-y-0 opacity-100",
              ].join(" ")}
            >
              <ShellBrand />
            </div>
            <div className="hidden justify-self-center lg:block">{ready ? <NavPills /> : null}</div>
            {ready ? (
              <div
                className={[
                  "flex shrink-0 justify-self-end gap-2 transition-all duration-200",
                  shellCondensed ? "pointer-events-none translate-y-[-4px] opacity-0" : "translate-y-0 opacity-100",
                ].join(" ")}
              >
                {activeRuns > 0 ? (
                  <UtilityButton
                    icon={<Sparkles className="h-3.5 w-3.5" />}
                    label={shellSummary?.running_label ?? "0 runs active"}
                    pulse
                    onClick={() => navigate("/")}
                  />
                ) : null}
                <CommandSearchButton onClick={() => setCommandOpen(true)} />
                <UtilityButton className="md:hidden" icon={<Search className="h-3.5 w-3.5" />} label="Cmd" onClick={() => setCommandOpen(true)} />
                <UtilityButton icon={<Inbox className="h-3.5 w-3.5" />} label="Inbox" value={String(pendingApprovals)} onClick={() => navigate("/inbox")} />
                <UtilityButton className="hidden sm:inline-flex" icon={<GitCompare className="h-3.5 w-3.5" />} label="Compare" onClick={() => navigate("/compare")} />
                <UtilityButton className="hidden sm:inline-flex" icon={<Settings2 className="h-3.5 w-3.5" />} label="Settings" onClick={() => navigate("/settings")} />
                <ThemeToggle
                  mode={activeTheme.mode}
                  onModeChange={(designMode) => updatePreferences({ designMode })}
                />
              </div>
            ) : (
              <div
                className={[
                  "justify-self-end transition-all duration-200",
                  shellCondensed ? "pointer-events-none translate-y-[-4px] opacity-0" : "translate-y-0 opacity-100",
                ].join(" ")}
              >
                <ThemeToggle mode={activeTheme.mode} onModeChange={(designMode) => updatePreferences({ designMode })} />
              </div>
            )}
          </div>
          <div className="mx-auto block max-w-[1440px] px-4 pb-3 sm:px-6 lg:hidden" data-responsive-nav>
            <div className="flex items-center gap-2 overflow-x-auto text-[11px] text-muted-foreground [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
              {NAV_ITEMS.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  className={({ isActive }) =>
                    [
                      "rounded-full px-2.5 py-1 transition-colors",
                      isActive ? "bg-foreground text-background" : "bg-[color-mix(in_oklab,var(--surface)_60%,transparent)] text-muted-foreground",
                    ].join(" ")
                  }
                >
                  {item.label}
                </NavLink>
              ))}
            </div>
          </div>
        </header>

        <main
          id="dashboard-main"
          tabIndex={-1}
          className="px-4 pb-6 pt-3 sm:px-6 lg:pb-8 lg:pt-4"
        >
          {children}
        </main>
      </div>

      <CommandPaletteDialog
        open={commandOpen}
        onOpenChange={setCommandOpen}
        items={commandItems}
        loading={commandLoading}
        onSelect={handleCommandSelect}
      />
      <SamanthaVoiceOrb />
    </div>
    </RealtimeVoiceProvider>
  );
}

export default function App() {
  const [onboarding, setOnboarding] = useState<OnboardingStatus | null>(null);
  const [runtimeSettings, setRuntimeSettings] = useState<RuntimeSettings | null>(null);
  const [pending, setPending] = useState(false);
  const [runtimePending, setRuntimePending] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const [status, runtime] = await Promise.all([
          fetchOnboardingStatus(),
          fetchRuntimeSettings(),
        ]);
        if (!cancelled) {
          setOnboarding(status);
          setRuntimeSettings(runtime);
        }
      } catch (error) {
        console.error("Failed to load onboarding status:", error);
      }
    };

    void load();
    const stream = openOnboardingStream((snapshot) => {
      if (!cancelled) {
        setOnboarding(snapshot);
        if (snapshot.ready) {
          setPending(false);
        }
      }
    });

    return () => {
      cancelled = true;
      stream.close();
    };
  }, []);

  const handleRuntimeSelect = async (sdk: RuntimeSdk) => {
    setRuntimePending(true);
    try {
      const settings = await updateRuntimeSettings(sdk);
      setRuntimeSettings(settings);
      window.dispatchEvent(new CustomEvent("aab:runtime-settings-updated", { detail: settings }));
    } catch (error) {
      console.error("Failed to update runtime settings:", error);
    } finally {
      setRuntimePending(false);
    }
  };

  const handleStart = async () => {
    setPending(true);
    try {
      const sdk = runtimeSettings?.sdk === "codex_sdk" ? "codex_sdk" : "claude";
      const status = await startOnboarding(sdk);
      const settings = await fetchRuntimeSettings();
      setOnboarding(status);
      setRuntimeSettings(settings);
    } catch (error) {
      console.error("Failed to start onboarding:", error);
    } finally {
      setPending(false);
    }
  };

  const handleRetry = async () => {
    setPending(true);
    try {
      const status = await retryOnboarding();
      setOnboarding(status);
    } catch (error) {
      console.error("Failed to retry onboarding:", error);
    } finally {
      setPending(false);
    }
  };

  if (!onboarding) {
    return (
      <AppShell ready={false}>
        <div className="px-5 py-10 text-sm text-muted-foreground">Loading onboarding status...</div>
      </AppShell>
    );
  }

  const onboardingMode = !onboarding.ready;

  return (
    <AppShell ready={!onboardingMode}>
      <Routes>
        {onboardingMode ? (
          <>
            <Route
              path="/"
              element={
                <OnboardingPage
                  status={onboarding}
                  runtimeSettings={runtimeSettings}
                  runtimePending={runtimePending}
                  actionPending={pending}
                  onRuntimeSelect={handleRuntimeSelect}
                  onStart={handleStart}
                  onRetry={handleRetry}
                />
              }
            />
            <Route path="*" element={<Navigate to="/" replace />} />
          </>
        ) : (
          <>
            <Route path="/" element={<AgentPage />} />
            <Route path="/agent" element={<Navigate to="/" replace />} />
            <Route path="/onboarding" element={<Navigate to="/" replace />} />
            <Route path="/board" element={<BoardPage />} />
            <Route path="/metrics" element={<MetricsPage />} />
            <Route path="/observability" element={<ObservabilityPage />} />
            <Route path="/approvals/:gateId" element={<ApprovalPage />} />
            <Route path="/knowledge" element={<KnowledgePage />} />
            <Route path="/memory" element={<MemoryPage />} />
            <Route path="/backlog" element={<BacklogPage />} />
            <Route path="/inbox" element={<InboxPage />} />
            <Route path="/compare" element={<ComparePage />} />
            <Route
              path="/settings"
              element={
                <SettingsPage
                  runtimeSettings={runtimeSettings}
                  runtimePending={runtimePending}
                  onRuntimeSelect={handleRuntimeSelect}
                />
              }
            />
          </>
        )}
      </Routes>
    </AppShell>
  );
}
