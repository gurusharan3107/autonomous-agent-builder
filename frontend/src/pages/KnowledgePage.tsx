import { useEffect, useMemo, useState } from "react";
import { Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import { PageFrame, PageHeader, SurfacePanel } from "@/components/workspace";
import { KnowledgeDocumentView } from "@/components/KnowledgeDocumentView";
import {
  getKBDoc,
  getRelatedDocs,
  listKBDocs,
  searchKBDocs,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import type { KBDocType, KBDocument, RelatedDocs } from "@/lib/types";

const DOC_TYPE_FILTERS: Array<{ value: "all" | KBDocType; label: string }> = [
  { value: "all", label: "all" },
  { value: "adr", label: "adr" },
  { value: "runbook", label: "runbook" },
  { value: "api_contract", label: "api_contract" },
  { value: "schema", label: "schema" },
  { value: "context", label: "context" },
];

const TYPE_LABELS: Record<string, string> = {
  adr: "ADR",
  api_contract: "Contract",
  schema: "Schema",
  runbook: "Runbook",
  context: "Context",
  raw: "Article",
  "reverse-engineering": "Reference",
  metadata: "Metadata",
};

function formatDate(value?: string) {
  if (!value) return "recent";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "recent";
  return parsed.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

function cleanInline(text: string) {
  return text
    .replace(/\[\[([^\]|]+)\|([^\]]+)\]\]/g, "$2")
    .replace(/\[\[([^\]]+)\]\]/g, "$1")
    .replace(/\[(.*?)\]\((.*?)\)/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/\*([^*]+)\*/g, "$1")
    .replace(/^---[\s\S]*?---\s*/, "")
    .replace(/^#+\s+.*$/gm, "")
    .replace(/\s+/g, " ")
    .trim();
}

function truncateWords(text: string, maxWords: number) {
  const words = text.trim().split(/\s+/).filter(Boolean);
  if (words.length <= maxWords) return text.trim();
  return `${words.slice(0, maxWords).join(" ").replace(/[,:;.-]+$/, "")}...`;
}

function getDocSummary(doc: KBDocument) {
  const preferred =
    doc.detail_summary ||
    doc.excerpt ||
    doc.card_summary ||
    cleanInline(doc.content);
  return truncateWords(preferred, 52);
}

function getDocType(doc: KBDocument) {
  return doc.doc_type ?? "raw";
}

function getTagList(doc: KBDocument) {
  return (doc.tags ?? []).slice(0, 8);
}

function getContextParagraph(doc: KBDocument) {
  const content = cleanInline(doc.content);
  if (!content) return "No context excerpt is available for this record yet.";
  return truncateWords(content, 68);
}

export default function KnowledgePage() {
  const [scope, setScope] = useState<"local" | "global">("local");
  const [selectedType, setSelectedType] = useState<"all" | KBDocType>("all");
  const [docs, setDocs] = useState<KBDocument[]>([]);
  const [search, setSearch] = useState("");
  const [selectedDoc, setSelectedDoc] = useState<KBDocument | null>(null);
  const [relatedDocs, setRelatedDocs] = useState<RelatedDocs | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    setLoading(true);

    const request =
      search.trim().length >= 2
        ? searchKBDocs(search.trim(), scope)
        : listKBDocs({
            limit: 50,
            scope,
            doc_type: selectedType === "all" ? undefined : selectedType,
          });

    request
      .then((results) => {
        if (!active) return;
        const filtered =
          selectedType === "all"
            ? results
            : results.filter((doc) => getDocType(doc) === selectedType);
        setDocs(filtered);
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [scope, search, selectedType]);

  useEffect(() => {
    let active = true;
    if (loading || docs.length === 0) return () => undefined;
    if (selectedDoc && docs.some((doc) => doc.id === selectedDoc.id)) return () => undefined;

    Promise.all([
      getKBDoc(docs[0].id, scope),
      getRelatedDocs(docs[0].id, scope).catch(() => null),
    ]).then(([doc, related]) => {
      if (!active) return;
      setSelectedDoc(doc);
      setRelatedDocs(related);
    });

    return () => {
      active = false;
    };
  }, [docs, loading, scope, selectedDoc]);

  const handleSelectDoc = async (id: string) => {
    const listDoc = docs.find((doc) => doc.id === id) ?? null;
    if (listDoc) setSelectedDoc(listDoc);
    const [doc, related] = await Promise.all([
      getKBDoc(id, scope),
      getRelatedDocs(id, scope).catch(() => null),
    ]);
    setSelectedDoc(doc);
    setRelatedDocs(related);
  };

  const selectedDocType = selectedDoc ? getDocType(selectedDoc) : selectedType;
  const relatedTitles = useMemo(
    () => [
      ...(relatedDocs?.backlinks ?? []),
      ...(relatedDocs?.similar ?? []),
      ...(relatedDocs?.wikilinks ?? []),
    ].slice(0, 3),
    [relatedDocs],
  );

  return (
    <PageFrame variant="explorer">
      <PageHeader
        className="page-intro-compact"
        eyebrow="Knowledge · graph"
        title="ADRs, runbooks, contracts, linked."
        description="Browse repo-local knowledge with the same calm reading hierarchy as the reference: narrow framing on the left, a dense document list, and one readable document surface."
      />

      <div className="grid gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
        <SurfacePanel className="space-y-3 lg:sticky lg:top-24 lg:max-h-[calc(100vh-8rem)] lg:self-start lg:overflow-hidden">
          <div className="inline-flex w-full rounded-[1rem] border border-border/75 bg-background/84 p-1">
            {(["local", "global"] as const).map((value) => (
              <button
                key={value}
                type="button"
                onClick={() => setScope(value)}
                className={cn(
                  "flex-1 rounded-[0.85rem] px-3 py-2 text-[12px] font-medium transition-colors",
                  scope === value
                    ? "bg-foreground text-background"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {value}
              </button>
            ))}
          </div>

          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground/80" />
            <Input
              name="knowledge-search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search docs, tags, wikilinks..."
              className="pl-9"
            />
          </div>

          <div className="flex flex-wrap gap-1">
            {DOC_TYPE_FILTERS.map((item) => {
              const active = selectedType === item.value;
              return (
                <button
                  key={item.value}
                  type="button"
                  onClick={() => setSelectedType(item.value)}
                  className={cn(
                    "rounded-full px-2.5 py-1 text-[11px] font-mono transition-colors",
                    active
                      ? "bg-foreground text-background"
                      : "border border-border/80 text-muted-foreground hover:text-foreground",
                  )}
                >
                  {item.label}
                </button>
              );
            })}
          </div>

          <div className="scroll-panel space-y-1 lg:max-h-[calc(100vh-18rem)] lg:overflow-y-auto lg:pr-1">
            {loading ? (
              <div className="rounded-[1rem] border border-border/70 bg-background/60 px-4 py-6 text-sm text-muted-foreground">
                Loading knowledge documents...
              </div>
            ) : docs.length === 0 ? (
              <div className="rounded-[1rem] border border-border/70 bg-background/60 px-4 py-6 text-sm text-muted-foreground">
                No knowledge documents match the current framing.
              </div>
            ) : (
              docs.map((doc) => {
                const active = selectedDoc?.id === doc.id;
                return (
                  <button
                    key={doc.id}
                    type="button"
                    onClick={() => void handleSelectDoc(doc.id)}
                    className={cn(
                      "w-full rounded-[1rem] border px-3 py-3 text-left transition-colors",
                      active
                        ? "border-foreground/20 bg-foreground/[0.04]"
                        : "border-transparent hover:border-border/70 hover:bg-background/70",
                    )}
                  >
                    <div className="mb-2 flex items-center gap-2">
                      <span className="rounded-[5px] border border-border/70 bg-background/75 px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                        {TYPE_LABELS[getDocType(doc)] ?? getDocType(doc)}
                      </span>
                      <span className="ml-auto font-mono text-[10px] text-muted-foreground">
                        {formatDate(doc.date_published ?? doc.created_at)}
                      </span>
                    </div>
                    <h3 className="text-[13px] font-medium leading-[1.35] text-foreground">
                      {doc.title}
                    </h3>
                  </button>
                );
              })
            )}
          </div>
        </SurfacePanel>

        <SurfacePanel className="space-y-5 px-6 py-6 sm:px-7 lg:min-h-[calc(100vh-14rem)]">
          {selectedDoc ? (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded-[5px] border border-border/70 bg-background/75 px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                  {TYPE_LABELS[selectedDocType] ?? selectedDocType}
                </span>
                <span className="font-mono text-[11px] text-muted-foreground">
                  {selectedDoc.id} · v{selectedDoc.version}
                </span>
                <span className="ml-auto font-mono text-[11px] text-muted-foreground">
                  Updated {formatDate(selectedDoc.date_published ?? selectedDoc.created_at)}
                </span>
              </div>

              <h2 className="font-[family:var(--font-heading)] text-[2rem] leading-[1.06] tracking-[-0.04em] text-foreground sm:text-[2.25rem]">
                {selectedDoc.title}
              </h2>

              <p className="max-w-[66ch] text-[15px] leading-[1.7] text-muted-foreground">
                {getDocSummary(selectedDoc)}
              </p>

              <div className="grid gap-4 lg:grid-cols-[minmax(0,1.1fr)_minmax(260px,0.9fr)]">
                <div className="space-y-3">
                  <p className="text-[13px] font-medium text-foreground">Context</p>
                  <p className="text-[14px] leading-[1.7] text-muted-foreground">
                    {getContextParagraph(selectedDoc)}
                  </p>
                </div>

                <div className="space-y-3">
                  <p className="text-[13px] font-medium text-foreground">Supporting context</p>
                  <div className="space-y-2 text-[13px] text-muted-foreground">
                    <p>
                      Scope:{" "}
                      <span className="font-semibold text-foreground">
                        {selectedDoc.scope === "global" ? "Global workspace" : "Local workspace"}
                      </span>
                    </p>
                    <p>
                      Related records:{" "}
                      <span className="font-semibold text-foreground">
                        {(relatedDocs?.backlinks.length ?? 0) +
                          (relatedDocs?.similar.length ?? 0) +
                          (relatedDocs?.wikilinks.length ?? 0)}
                      </span>
                    </p>
                  </div>
                </div>
              </div>

              <KnowledgeDocumentView
                content={selectedDoc.content}
                externalTitle={selectedDoc.title}
              />

              {getTagList(selectedDoc).length > 0 ? (
                <div className="flex flex-wrap gap-1.5 pt-2">
                  {getTagList(selectedDoc).map((tag) => (
                    <span
                      key={tag}
                      className="inline-flex items-center rounded-full border border-border/75 px-2 py-1 font-mono text-[10.5px] text-muted-foreground"
                    >
                      #{tag}
                    </span>
                  ))}
                </div>
              ) : null}

              {relatedTitles.length > 0 ? (
                <div className="space-y-3 pt-2">
                  <p className="text-[13px] font-medium text-foreground">Referenced by</p>
                  <div className="space-y-2">
                    {relatedTitles.map((doc) => (
                      <button
                        key={doc.id}
                        type="button"
                        onClick={() => void handleSelectDoc(doc.id)}
                        className="block w-full rounded-[0.95rem] border border-border/70 bg-background/55 px-3 py-2 text-left text-[13px] text-foreground transition-colors hover:bg-background/80"
                      >
                        {doc.title}
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}
            </>
          ) : (
            <div className="rounded-[1rem] border border-border/70 bg-background/60 px-4 py-6 text-sm text-muted-foreground">
              Select a document to read.
            </div>
          )}
        </SurfacePanel>
      </div>
    </PageFrame>
  );
}
