import type { ReactNode } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Navigate, NavLink, Route, Routes, useNavigate } from "react-router-dom";
import {
  Bot,
  Command,
  GitCompare,
  Inbox,
  Moon,
  Search,
  Sparkles,
  Sun,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
  fetchShellSummary,
  openOnboardingStream,
  retryOnboarding,
  startOnboarding,
  dispatchTask,
} from "@/lib/api";
import type {
  CommandPaletteItem,
  OnboardingStatus,
  RuntimePreferenceState,
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
import OnboardingPage from "@/pages/OnboardingPage";
import { useRuntimePreferences } from "@/hooks/use-runtime-preferences";
import { SectionLabel, StatusDot, SurfacePanel } from "@/components/workspace";

const NAV_ITEMS = [
  { to: "/", label: "Agent", end: true },
  { to: "/board", label: "Board", end: false },
  { to: "/metrics", label: "Metrics", end: false },
  { to: "/knowledge", label: "Knowledge", end: false },
  { to: "/memory", label: "Memory", end: false },
  { to: "/backlog", label: "Backlog", end: false },
] as const;

const ROUTE_JUMPS: Record<string, string> = {
  a: "/",
  b: "/board",
  m: "/metrics",
  k: "/knowledge",
  y: "/memory",
  l: "/backlog",
  i: "/inbox",
  c: "/compare",
};

function ThemeToggle() {
  const [dark, setDark] = useState(() => {
    if (typeof window === "undefined") return false;
    const stored = localStorage.getItem("aab-theme");
    if (stored) return stored === "dark";
    return window.matchMedia("(prefers-color-scheme: dark)").matches;
  });

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    localStorage.setItem("aab-theme", dark ? "dark" : "light");
  }, [dark]);

  return (
    <Button
      variant="outline"
      size="icon"
      onClick={() => setDark((value) => !value)}
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
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[1rem] bg-[linear-gradient(180deg,oklch(0.48_0.14_252),oklch(0.34_0.08_244))] text-primary-foreground shadow-[0_14px_34px_-22px_rgba(7,94,169,0.82)]">
        <Bot className="h-5 w-5" />
      </div>
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
              isActive ? "bg-foreground text-background shadow-[0_14px_32px_-24px_rgba(30,26,21,0.8)]" : "text-muted-foreground hover:text-foreground",
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
      variant="outline"
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
    <button
      type="button"
      onClick={onClick}
      aria-label="Open command palette"
      title="Command palette"
      className="hidden h-8 w-8 items-center justify-center rounded-full border border-border/75 bg-background-sunk/75 text-muted-foreground transition hover:bg-background md:inline-flex"
    >
      <Search className="h-3.5 w-3.5" />
    </button>
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

  useEffect(() => {
    if (!open) setQuery("");
  }, [open]);

  const filteredItems = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return items;
    return items.filter((item) =>
      [item.label, item.description, item.kind].some((value) => value.toLowerCase().includes(normalized)),
    );
  }, [items, query]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl rounded-[1.5rem] p-0" showCloseButton={false}>
        <div className="border-b border-border/70 px-5 py-4">
          <DialogHeader>
            <DialogTitle>Command palette</DialogTitle>
            <DialogDescription>Jump to routes, resume sessions, review approvals, or dispatch a task.</DialogDescription>
          </DialogHeader>
          <div className="mt-4">
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
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
            <div className="space-y-2">
              {filteredItems.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => onSelect(item)}
                  className="w-full rounded-[1rem] border border-border/70 bg-background/60 px-4 py-3 text-left transition hover:border-border hover:bg-background/85"
                >
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-medium text-foreground">{item.label}</p>
                      <p className="text-xs text-muted-foreground">{item.description}</p>
                    </div>
                    <span className="text-[10px] uppercase tracking-[0.16em] text-muted-foreground">{item.kind}</span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

function PreferenceSelect({
  label,
  description,
  value,
  options,
  onChange,
}: {
  label: string;
  description: string;
  value: string;
  options: Array<{ label: string; value: string }>;
  onChange: (value: string) => void;
}) {
  return (
    <div className="rounded-[1rem] border border-border/70 bg-background/55 p-4">
      <p className="text-sm font-medium text-foreground">{label}</p>
      <p className="mt-1 text-xs text-muted-foreground">{description}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {options.map((option) => (
          <Button
            key={option.value}
            type="button"
            variant={value === option.value ? "default" : "outline"}
            className="h-9 rounded-full"
            onClick={() => onChange(option.value)}
          >
            {option.label}
          </Button>
        ))}
      </div>
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

function SystemInspectorDialog({
  open,
  onOpenChange,
  summary,
  preferences,
  updatePreferences,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  summary: ShellSummary | null;
  preferences: RuntimePreferenceState;
  updatePreferences: (patch: Partial<RuntimePreferenceState>) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl rounded-[1.5rem] p-0">
        <div className="border-b border-border/70 px-5 py-4">
          <DialogHeader>
            <DialogTitle>System inspector</DialogTitle>
            <DialogDescription>
              Live runtime state plus the persisted view preferences that replaced the prototype tweaks panel.
            </DialogDescription>
          </DialogHeader>
        </div>

        <div className="grid gap-5 p-5 md:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
          <div className="space-y-4">
            <SectionLabel>Runtime</SectionLabel>
            <div className="grid gap-2">
              <RuntimeMetricRow label="Running" value={summary?.running_label ?? "0 running"} tone="active" />
              <RuntimeMetricRow label="Approvals" value={String(summary?.pending_approvals ?? 0)} tone="review" />
              <RuntimeMetricRow label="Questions" value={String(summary?.pending_questions ?? 0)} tone="review" />
              <RuntimeMetricRow label="Permission" value={summary?.permission_mode ?? "unknown"} />
              <RuntimeMetricRow label="Cost" value={`$${(summary?.total_cost ?? 0).toFixed(4)}`} />
              <RuntimeMetricRow label="Tokens" value={(summary?.total_tokens ?? 0).toLocaleString()} />
            </div>

            <SurfacePanel className="space-y-3">
              <SectionLabel>SDK-derived signals</SectionLabel>
              <div className="space-y-2 text-sm text-muted-foreground">
                <p>Active session: <span className="font-mono text-foreground">{summary?.active_session_id ?? "none"}</span></p>
                <p>MCP servers: <span className="text-foreground">{summary?.mcp_servers.length ? summary.mcp_servers.join(", ") : "unknown"}</span></p>
                <p>MCP tools: <span className="text-foreground">{summary?.mcp_tools.length ? summary.mcp_tools.join(", ") : "unknown"}</span></p>
              </div>
            </SurfacePanel>

            <SurfacePanel className="space-y-3">
              <SectionLabel>Todo progress</SectionLabel>
              {!summary?.todo_snapshots.length ? (
                <p className="text-sm text-muted-foreground">No TodoWrite snapshots captured yet.</p>
              ) : (
                <div className="space-y-3">
                  {summary.todo_snapshots.map((snapshot) => (
                    <div key={snapshot.session_id} className="rounded-[1rem] border border-border/70 bg-background/55 p-4">
                      <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">
                        Session {snapshot.session_id.slice(0, 8)}
                      </p>
                      <p className="mt-2 text-sm text-foreground">
                        {snapshot.in_progress_count} in progress / {snapshot.pending_count} pending / {snapshot.completed_count} completed
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </SurfacePanel>
          </div>

          <div className="space-y-4">
            <SectionLabel>Preferences</SectionLabel>
            <PreferenceSelect
              label="Board density"
              description="Controls the lane/card density on the board page."
              value={preferences.boardDensity}
              options={[
                { label: "Comfortable", value: "comfortable" },
                { label: "Compact", value: "compact" },
              ]}
              onChange={(value) => updatePreferences({ boardDensity: value as RuntimePreferenceState["boardDensity"] })}
            />
            <PreferenceSelect
              label="Agent inspector default"
              description="Sets the default right-rail inspector on the Agent page."
              value={preferences.agentInspectorDefault}
              options={[
                { label: "Evidence", value: "evidence" },
                { label: "Sessions", value: "sessions" },
              ]}
              onChange={(value) =>
                updatePreferences({ agentInspectorDefault: value as RuntimePreferenceState["agentInspectorDefault"] })
              }
            />
            <PreferenceSelect
              label="Transcript default"
              description="Sets the default transcript filter on the Agent page."
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
            <PreferenceSelect
              label="Compare display"
              description="Controls how the compare page lays out the two selected runs."
              value={preferences.compareDisplayMode}
              options={[
                { label: "Split", value: "split" },
                { label: "Stacked", value: "stacked" },
              ]}
              onChange={(value) =>
                updatePreferences({ compareDisplayMode: value as RuntimePreferenceState["compareDisplayMode"] })
              }
            />
          </div>
        </div>
      </DialogContent>
    </Dialog>
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
  const [systemOpen, setSystemOpen] = useState(false);
  const [shellSummary, setShellSummary] = useState<ShellSummary | null>(null);
  const [commandItems, setCommandItems] = useState<CommandPaletteItem[]>([]);
  const [commandLoading, setCommandLoading] = useState(false);
  const [shellCondensed, setShellCondensed] = useState(false);
  const jumpAwaitingRef = useRef(false);
  const jumpTimeoutRef = useRef<number | null>(null);

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
  }, [location.pathname, ready]);

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
        setSystemOpen(true);
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
    <div className="min-h-screen bg-background text-foreground">
      <div className="relative min-h-screen">
        <header
          className={[
            "sticky top-0 z-40 transition-all duration-200",
            shellCondensed
              ? "border-b border-transparent bg-transparent backdrop-blur-0"
              : "border-b border-border/65 bg-background/78 backdrop-blur-xl",
          ].join(" ")}
        >
          <div
            className={[
              "mx-auto grid max-w-[1440px] grid-cols-[1fr_auto_1fr] items-center gap-4 px-4 sm:px-6",
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
            <div className="justify-self-center">{ready ? <NavPills /> : null}</div>
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
                <UtilityButton icon={<GitCompare className="h-3.5 w-3.5" />} label="Compare" onClick={() => navigate("/compare")} />
                <UtilityButton icon={<Command className="h-3.5 w-3.5" />} label="System" onClick={() => setSystemOpen(true)} />
                <ThemeToggle />
              </div>
            ) : (
              <div
                className={[
                  "justify-self-end transition-all duration-200",
                  shellCondensed ? "pointer-events-none translate-y-[-4px] opacity-0" : "translate-y-0 opacity-100",
                ].join(" ")}
              >
                <ThemeToggle />
              </div>
            )}
          </div>
          <div className="mx-auto hidden max-w-[1440px] px-4 pb-3 sm:px-6 md:block lg:hidden">
            <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
              {NAV_ITEMS.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  className={({ isActive }) =>
                    [
                      "rounded-full px-2.5 py-1 transition-colors",
                      isActive ? "bg-foreground text-background" : "bg-background/60 text-muted-foreground",
                    ].join(" ")
                  }
                >
                  {item.label}
                </NavLink>
              ))}
            </div>
          </div>
        </header>

        <main className="px-4 pb-8 pt-4 sm:px-6 lg:pb-10 lg:pt-5">{children}</main>
      </div>

      <CommandPaletteDialog
        open={commandOpen}
        onOpenChange={setCommandOpen}
        items={commandItems}
        loading={commandLoading}
        onSelect={handleCommandSelect}
      />
      <SystemInspectorDialog
        open={systemOpen}
        onOpenChange={setSystemOpen}
        summary={shellSummary}
        preferences={preferences}
        updatePreferences={updatePreferences}
      />
    </div>
  );
}

export default function App() {
  const [onboarding, setOnboarding] = useState<OnboardingStatus | null>(null);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const status = await fetchOnboardingStatus();
        if (!cancelled) {
          setOnboarding(status);
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

  const handleStart = async () => {
    setPending(true);
    try {
      const status = await startOnboarding();
      setOnboarding(status);
    } catch (error) {
      console.error("Failed to start onboarding:", error);
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
                  actionPending={pending}
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
            <Route path="/board" element={<BoardPage />} />
            <Route path="/metrics" element={<MetricsPage />} />
            <Route path="/approvals/:gateId" element={<ApprovalPage />} />
            <Route path="/knowledge" element={<KnowledgePage />} />
            <Route path="/memory" element={<MemoryPage />} />
            <Route path="/backlog" element={<BacklogPage />} />
            <Route path="/inbox" element={<InboxPage />} />
            <Route path="/compare" element={<ComparePage />} />
          </>
        )}
      </Routes>
    </AppShell>
  );
}
