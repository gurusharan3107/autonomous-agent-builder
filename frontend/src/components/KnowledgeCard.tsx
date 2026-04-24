import { useRef } from "react";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { Badge } from "@/components/ui/badge";
import type { KBDocument } from "@/lib/types";

const TYPE_LABELS: Record<string, string> = {
  adr: "ADR",
  api_contract: "API Contract",
  schema: "Schema",
  runbook: "Runbook",
  context: "Context",
  raw: "Article",
};

interface KnowledgeCardProps {
  doc: KBDocument;
  onSelect: (id: string) => void;
  isSelected: boolean;
}

export function KnowledgeCard({ doc, onSelect, isSelected }: KnowledgeCardProps) {
  const rowRef = useRef<HTMLButtonElement>(null);

  useGSAP(() => {
    const row = rowRef.current;
    if (!row) return;

    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (prefersReducedMotion) return;

    const onEnter = () => {
      gsap.to(row, {
        x: 4,
        duration: 0.18,
        ease: "power2.out",
      });
    };

    const onLeave = () => {
      gsap.to(row, {
        x: 0,
        duration: 0.18,
        ease: "power2.out",
      });
    };

    row.addEventListener("mouseenter", onEnter);
    row.addEventListener("mouseleave", onLeave);

    return () => {
      row.removeEventListener("mouseenter", onEnter);
      row.removeEventListener("mouseleave", onLeave);
    };
  }, [isSelected]);

  const excerpt = doc.content
    .replace(/^---[\s\S]*?---/, "")
    .replace(/^#+\s+.*$/gm, "")
    .replace(/\[\[([^\]|]+)\|([^\]]+)\]\]/g, "$2")
    .replace(/\[\[([^\]]+)\]\]/g, "$1")
    .trim()
    .slice(0, 170);

  return (
    <button
      ref={rowRef}
      type="button"
      data-selected={isSelected}
      className="surface-list-item"
      onClick={() => onSelect(doc.id)}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="secondary" className="text-[10px] uppercase tracking-[0.18em]">
              {TYPE_LABELS[doc.doc_type] || doc.doc_type}
            </Badge>
            <span className="text-[10px] font-mono uppercase tracking-[0.18em] text-muted-foreground">
              {doc.source_author ? doc.source_author : "local doc"}
            </span>
          </div>
          <div>
            <h3 className="text-base font-semibold leading-snug tracking-tight text-foreground">
              {doc.title}
            </h3>
            <p className="mt-2 max-w-[60ch] text-sm leading-6 text-muted-foreground">
              {excerpt || "No preview available."}
            </p>
          </div>
        </div>

        <div className="text-right text-[10px] font-mono uppercase tracking-[0.18em] text-muted-foreground">
          <div>{doc.wikilinks?.length ?? 0} links</div>
          <div className="mt-1">{doc.version ? `v${doc.version}` : "latest"}</div>
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-1.5">
        {doc.tags?.slice(0, 4).map((tag) => (
          <span
            key={tag}
            className="rounded-full border border-border/70 bg-background/65 px-2.5 py-1 text-[10px] uppercase tracking-[0.16em] text-muted-foreground"
          >
            {tag}
          </span>
        ))}
        {(doc.tags?.length ?? 0) > 4 ? (
          <span className="rounded-full border border-border/70 bg-background/65 px-2.5 py-1 text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
            +{(doc.tags?.length ?? 0) - 4}
          </span>
        ) : null}
      </div>
    </button>
  );
}
