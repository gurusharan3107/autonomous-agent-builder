import { useEffect, useMemo, useState, type ReactNode } from "react";
import { Code, Input, StatusPill } from "@/design-system";
import { MemorySidebar } from "@/components/MemorySidebar";
import { EditorialContent } from "@/components/EditorialContent";
import { PageFrame, PageHeader, SurfacePanel } from "@/design-system";
import { getMemory, listMemories } from "@/lib/api";
import type { MemoryEntry, MemoryType } from "@/lib/types";

const TYPE_STYLES: Record<
  MemoryType,
  { label: string; tone: "decision" | "pattern" | "correction" }
> = {
  decision: { label: "Decision", tone: "decision" },
  pattern: { label: "Pattern", tone: "pattern" },
  correction: { label: "Correction", tone: "correction" },
};

type MemoryFilter = "all" | MemoryType;

function buildExcerpt(entry: MemoryEntry, content: string) {
  const source = (content || entry.content || "")
    .replace(/^---[\s\S]*?---\s*/, "")
    .replace(/^#+\s+.*$/gm, "")
    .replace(/\s+/g, " ")
    .trim();
  if (!source) return "No detail has been captured for this memory entry yet.";
  const words = source.split(/\s+/).filter(Boolean);
  if (words.length <= 40) return source;
  return `${words.slice(0, 40).join(" ").replace(/[,:;.-]+$/, "")}...`;
}

export default function MemoryPage() {
  const [entries, setEntries] = useState<MemoryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [selectedType, setSelectedType] = useState<MemoryFilter>("all");
  const [selectedEntry, setSelectedEntry] = useState<MemoryEntry | null>(null);
  const [selectedContent, setSelectedContent] = useState("");
  const [sidebarOpen, setSidebarOpen] = useState(false);

  useEffect(() => {
    listMemories()
      .then(setEntries)
      .finally(() => setLoading(false));
  }, []);

  const filteredEntries = useMemo(() => {
    const query = search.trim().toLowerCase();
    return entries.filter((entry) => {
      if (selectedType !== "all" && entry.type !== selectedType) return false;
      if (!query) return true;
      const haystack = [
        entry.title,
        entry.phase,
        entry.entity,
        entry.status,
        ...(entry.tags ?? []),
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(query);
    });
  }, [entries, search, selectedType]);

  useEffect(() => {
    if (selectedEntry && filteredEntries.some((entry) => entry.slug === selectedEntry.slug)) return;

    if (filteredEntries.length > 0) {
      const next = filteredEntries[0];
      getMemory(next.slug)
        .then((entry) => {
          setSelectedEntry(next);
          setSelectedContent(entry.content ?? "");
        })
        .catch(() => {
          setSelectedEntry(next);
          setSelectedContent("");
        });
      return;
    }

    // Deliberate: reset selection when the filtered result set is empty.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSelectedEntry(null);
    setSelectedContent("");
  }, [filteredEntries, selectedEntry]);

  const handleSelectEntry = async (entry: MemoryEntry) => {
    const full = await getMemory(entry.slug);
    setSelectedEntry(entry);
    setSelectedContent(full.content ?? "");
    setSidebarOpen(true);
  };

  const detailPanel = selectedEntry ? (
    <SurfacePanel className="space-y-5 p-7">
      <div className="flex flex-wrap items-center gap-2">
        <MemoryTypeBadge type={selectedEntry.type} />
        <span className="font-mono text-[11px] text-muted-foreground">{selectedEntry.slug}</span>
        <span className="ml-auto font-mono text-[11px] text-muted-foreground">{selectedEntry.date}</span>
      </div>

      <h2 className="display-serif text-[30px] leading-[1.12] text-foreground">
        {selectedEntry.title}
      </h2>

      <div className="flex flex-wrap gap-3 text-[11.5px]">
        <Field label="Phase" value={<Code>{selectedEntry.phase || "not set"}</Code>} />
        <Field label="Entity" value={<Code>{selectedEntry.entity || "repo"}</Code>} />
        <Field label="Status" value={<StatusPill status={memoryStatusToPill(selectedEntry.status)} />} />
      </div>

      <p className="max-w-[64ch] font-serif text-[15px] leading-[1.72] text-muted-foreground">
        {buildExcerpt(selectedEntry, selectedContent)}
      </p>

      <div className="space-y-3">
        <h3 className="text-[13px] font-medium text-foreground">Context</h3>
        <p className="text-[13.5px] leading-[1.72] text-muted-foreground">
          Observed during the {selectedEntry.phase || "active"} phase while working on{" "}
          <span className="font-mono text-foreground">{selectedEntry.entity || "the repo"}</span>.
          This entry remains in memory because it is meant to shape future work, not just document a past run.
        </p>
      </div>

      <div className="space-y-3">
        <h3 className="text-[13px] font-medium text-foreground">Memory content</h3>
        <EditorialContent content={selectedContent || "No content available for this memory."} />
      </div>

      {selectedEntry.tags?.length ? (
        <div className="flex flex-wrap gap-1.5 pt-2">
          {selectedEntry.tags.map((tag) => (
            <span
              key={tag}
              className="inline-flex items-center rounded-full border border-border/75 px-2 py-1 font-mono text-[10.5px] text-muted-foreground"
            >
              #{tag}
            </span>
          ))}
        </div>
      ) : null}
    </SurfacePanel>
  ) : (
    <div className="rounded-[var(--radius-md)] border border-border/70 bg-background/60 px-3.5 py-3.5 text-sm text-muted-foreground">
      Select a memory entry to inspect.
    </div>
  );

  return (
    <PageFrame variant="explorer" data-screen-label="Memory">
      <PageHeader
        className="page-intro-compact"
        eyebrow="Memory · corrections · decisions · patterns"
        title="What we learned, and what we will not repeat."
        description="Use the reference memory composition here: one narrow filter column, one dense list of durable lessons, and one readable detail surface for the selected entry."
      />

      <div className="grid gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
        <SurfacePanel className="space-y-2 p-3 lg:sticky lg:top-24 lg:max-h-[calc(100vh-8rem)] lg:self-start lg:overflow-hidden">
          <Input
            name="memory-search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search memory..."
          />

          <div className="flex gap-1 pb-1 pt-1">
            {([
              { value: "all", label: "All" },
              { value: "decision", label: "Decisions" },
              { value: "pattern", label: "Patterns" },
              { value: "correction", label: "Corrections" },
            ] as Array<{ value: MemoryFilter; label: string }>).map((item) => {
              const active = selectedType === item.value;
              const count =
                item.value === "all"
                  ? entries.length
                  : entries.filter((entry) => entry.type === item.value).length;
              return (
                <button
                  key={item.value}
                  type="button"
                  onClick={() => setSelectedType(item.value)}
                  className={[
                    "inline-flex h-7 flex-1 items-center justify-center gap-1 rounded-[var(--radius-sm)] border border-[var(--line)] px-2 text-[11px] font-medium transition-colors",
                    active
                      ? "bg-[var(--accent)] text-[var(--fg-on-accent)]"
                      : "bg-[var(--surface-2)] text-muted-foreground hover:text-foreground",
                  ].join(" ")}
                >
                  {item.label}{" "}
                  <span className="font-mono text-[9.5px] opacity-70">{count}</span>
                </button>
              );
            })}
          </div>

          <div className="scroll-panel space-y-1 lg:max-h-[calc(100vh-16rem)] lg:overflow-y-auto lg:pr-1">
            {loading ? (
              <div className="rounded-[var(--radius-md)] border border-border/70 bg-background/60 px-3.5 py-3.5 text-sm text-muted-foreground">
                Loading memory index...
              </div>
            ) : filteredEntries.length === 0 ? (
              <div className="rounded-[var(--radius-md)] border border-border/70 bg-background/60 px-3.5 py-3.5 text-sm text-muted-foreground">
                No memory entries match the current filters.
              </div>
            ) : (
              filteredEntries.map((entry) => {
                const active = selectedEntry?.slug === entry.slug;
                return (
                  <button
                    key={entry.slug}
                    type="button"
                    onClick={() => void handleSelectEntry(entry)}
                    className="w-full rounded-[var(--radius-md)] border px-3 py-2.5 text-left transition-colors hover:bg-[var(--surface-2)]"
                    style={{
                      background: active
                        ? "color-mix(in oklab, var(--accent) 6%, var(--surface))"
                        : "transparent",
                      borderColor: active
                        ? "color-mix(in oklab, var(--accent) 30%, var(--line))"
                        : "transparent",
                    }}
                  >
                    <div className="mb-2 flex items-center gap-2">
                      <MemoryTypeBadge type={entry.type} />
                      <span className="ml-auto font-mono text-[10px] text-muted-foreground">
                        {entry.date}
                      </span>
                    </div>
                    <h3 className="text-[13px] font-medium leading-[1.35] text-foreground">
                      {entry.title}
                    </h3>
                  </button>
                );
              })
            )}
          </div>
        </SurfacePanel>

        <div className="hidden lg:block">{detailPanel}</div>
      </div>

      <div className="lg:hidden">
        <MemorySidebar
          entry={selectedEntry}
          content={selectedContent}
          isOpen={sidebarOpen && !!selectedEntry}
          onClose={() => setSidebarOpen(false)}
        />
      </div>
    </PageFrame>
  );
}

function MemoryTypeBadge({ type }: { type: MemoryType }) {
  const meta = TYPE_STYLES[type];
  const toneStyles = {
    decision: {
      background: "color-mix(in oklab, var(--accent) 14%, transparent)",
      color: "var(--accent)",
      borderColor: "color-mix(in oklab, var(--accent) 34%, var(--line))",
    },
    pattern: {
      background: "var(--surface-2)",
      color: "var(--fg-2)",
      borderColor: "var(--line)",
    },
    correction: {
      background: "color-mix(in oklab, var(--status-blocked) 10%, transparent)",
      color: "var(--status-blocked)",
      borderColor: "color-mix(in oklab, var(--status-blocked) 30%, var(--line))",
    },
  }[meta.tone];

  return (
    <span
      className="inline-flex h-5 items-center rounded-[5px] border px-1.5 font-mono text-[10px] uppercase tracking-[0.14em]"
      style={toneStyles}
    >
      {meta.label}
    </span>
  );
}

function memoryStatusToPill(status?: string) {
  if (status === "accepted" || status === "applied" || status === "recorded") return "done";
  if (status === "failed" || status === "blocked") return "blocked";
  if (status === "pending" || status === "queued") return "pending";
  return "done";
}

function Field({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="inline-flex items-center gap-2">
      <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">{label}</span>
      <span className="font-mono text-[11px] text-foreground">{value}</span>
    </div>
  );
}
