import { useRef } from "react";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { ChevronRight, X } from "lucide-react";
import { KnowledgeDocumentView } from "@/components/KnowledgeDocumentView";
import { EmptyState, SectionLabel } from "@/components/workspace";
import type { KBDocument, RelatedDocs } from "@/lib/types";

const TYPE_LABELS: Record<string, string> = {
  adr: "ADR",
  api_contract: "API Contract",
  schema: "Schema",
  runbook: "Runbook",
  context: "Context",
  raw: "Article",
};

interface RelatedSidebarProps {
  doc: KBDocument | null;
  relatedDocs: RelatedDocs | null;
  onSelectDoc: (id: string) => void;
  onClose: () => void;
  isOpen: boolean;
}

interface RelatedItem {
  id: string;
  title: string;
  content: string;
  doc_type?: string;
  shared_tags?: string[];
}

function excerpt(content: string) {
  return content
    .replace(/^---[\s\S]*?---/, "")
    .replace(/^#+\s+.*$/gm, "")
    .replace(/\[\[([^\]|]+)\|([^\]]+)\]\]/g, "$2")
    .replace(/\[\[([^\]]+)\]\]/g, "$1")
    .trim()
    .substring(0, 88);
}

function RelatedSection({
  title,
  items,
  onSelectDoc,
}: {
  title: string;
  items: RelatedItem[];
  onSelectDoc: (id: string) => void;
}) {
  return (
    <details className="group rounded-[1.4rem] border border-border/75 bg-background/55 px-4 py-3">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-sm font-medium text-foreground">
        <span>{title}</span>
        <ChevronRight className="h-4 w-4 transition-transform group-open:rotate-90" />
      </summary>

      <div className="mt-3 space-y-2">
        {items.map((item) => (
          <button
            key={item.id}
            type="button"
            className="surface-list-item p-3"
            onClick={() => onSelectDoc(item.id)}
          >
            <div className="flex items-start justify-between gap-2">
              <p className="line-clamp-2 flex-1 text-sm font-medium">{item.title}</p>
              {item.doc_type ? (
                <Badge variant="outline" className="text-[10px] uppercase tracking-[0.18em]">
                  {TYPE_LABELS[item.doc_type] || item.doc_type}
                </Badge>
              ) : null}
            </div>
            <p className="mt-2 line-clamp-2 text-xs leading-5 text-muted-foreground">
              {excerpt(item.content)}
            </p>
          </button>
        ))}
      </div>
    </details>
  );
}

export function RelatedSidebar({
  doc,
  relatedDocs,
  onSelectDoc,
  onClose,
  isOpen,
}: RelatedSidebarProps) {
  const sidebarRef = useRef<HTMLDivElement>(null);
  const backdropRef = useRef<HTMLDivElement>(null);

  useGSAP(() => {
    if (!sidebarRef.current || !backdropRef.current) return;
    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    if (prefersReducedMotion) {
      sidebarRef.current.style.transform = isOpen ? "translateX(0)" : "translateX(100%)";
      backdropRef.current.style.opacity = isOpen ? "1" : "0";
      backdropRef.current.style.pointerEvents = isOpen ? "auto" : "none";
      return;
    }

    gsap.to(sidebarRef.current, {
      x: isOpen ? 0 : "100%",
      duration: 0.32,
      ease: "power3.out",
    });

    gsap.to(backdropRef.current, {
      opacity: isOpen ? 1 : 0,
      duration: 0.24,
      onComplete: () => {
        if (backdropRef.current) {
          backdropRef.current.style.pointerEvents = isOpen ? "auto" : "none";
        }
      },
    });
  }, [isOpen]);

  const wikilinks = relatedDocs?.wikilinks ?? [];
  const backlinks = relatedDocs?.backlinks ?? [];
  const similar = relatedDocs?.similar ?? [];
  const hasAnyRelated = wikilinks.length + backlinks.length + similar.length > 0;

  const content = doc ? (
    <div className="flex h-full flex-col">
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="secondary" className="text-[10px] uppercase tracking-[0.18em]">
              {TYPE_LABELS[doc.doc_type] || doc.doc_type}
            </Badge>
            <span className="text-[10px] font-mono uppercase tracking-[0.18em] text-muted-foreground">
              {doc.source_author || "local doc"}
            </span>
          </div>
          <div>
            <h2 className="text-2xl font-semibold tracking-tight text-foreground">
              {doc.title}
            </h2>
            <div className="mt-3 flex flex-wrap gap-1.5">
              {doc.tags?.map((tag) => (
                <span
                  key={tag}
                  className="rounded-full border border-border/70 bg-background/65 px-2.5 py-1 text-[10px] uppercase tracking-[0.16em] text-muted-foreground"
                >
                  {tag}
                </span>
              ))}
            </div>
          </div>
        </div>
        <Button variant="ghost" size="icon" onClick={onClose} className="shrink-0 xl:hidden">
          <X className="h-4 w-4" />
        </Button>
      </div>

      <Separator className="my-5" />

      <div className="min-h-0 flex-1 space-y-6 overflow-y-auto pr-1">
        <KnowledgeDocumentView content={doc.content} />

        <div className="space-y-3">
          <SectionLabel>Related context</SectionLabel>
          {!hasAnyRelated ? (
            <EmptyState
              label="No related documents yet."
              detail="This record has no linked or similar documents in the current knowledge scope."
            />
          ) : null}
          {wikilinks.length > 0 ? (
            <RelatedSection title={`Links to (${wikilinks.length})`} items={wikilinks} onSelectDoc={onSelectDoc} />
          ) : null}
          {backlinks.length > 0 ? (
            <RelatedSection title={`Referenced by (${backlinks.length})`} items={backlinks} onSelectDoc={onSelectDoc} />
          ) : null}
          {similar.length > 0 ? (
            <RelatedSection title={`Related topics (${similar.length})`} items={similar} onSelectDoc={onSelectDoc} />
          ) : null}
        </div>
      </div>
    </div>
  ) : (
    <EmptyState
      label="Select a document to read."
      detail="The detail pane stays readable and persistent on desktop so operators can scan results without losing context."
      className="h-full"
    />
  );

  return (
    <>
      <div
        ref={backdropRef}
        className="fixed inset-0 z-40 bg-black/20 opacity-0 pointer-events-none backdrop-blur-sm xl:hidden"
        onClick={onClose}
      />

      <div
        ref={sidebarRef}
        className="fixed right-0 top-0 z-50 h-full w-full translate-x-full overflow-y-auto px-4 py-4 sm:w-[38rem] xl:static xl:h-auto xl:w-auto xl:translate-x-0 xl:overflow-visible xl:px-0 xl:py-0"
      >
        <div className="detail-drawer-panel h-full xl:sticky xl:top-24 xl:h-[calc(100vh-7rem)] xl:p-6">
          {content}
        </div>
      </div>
    </>
  );
}
