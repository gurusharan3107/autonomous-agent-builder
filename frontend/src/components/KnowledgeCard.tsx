import { useRef } from "react";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { Card } from "@/components/ui/card";
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
  const cardRef = useRef<HTMLDivElement>(null);
  const previewRef = useRef<HTMLDivElement>(null);

  useGSAP(() => {
    const card = cardRef.current;
    const preview = previewRef.current;
    if (!card || !preview) return;

    // Check for reduced motion preference
    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const onEnter = () => {
      if (prefersReducedMotion) {
        card.style.transform = "scale(1.02)";
        card.style.boxShadow = "0 20px 25px -5px rgb(0 0 0 / 0.1)";
        preview.style.height = "auto";
        preview.style.opacity = "1";
      } else {
        gsap.to(card, {
          scale: 1.02,
          boxShadow: "0 20px 25px -5px rgb(0 0 0 / 0.1), 0 8px 10px -6px rgb(0 0 0 / 0.1)",
          duration: 0.3,
          ease: "power2.out",
        });

        gsap.to(preview, {
          height: "auto",
          opacity: 1,
          duration: 0.3,
          ease: "power2.out",
        });
      }
    };

    const onLeave = () => {
      if (prefersReducedMotion) {
        card.style.transform = "scale(1)";
        card.style.boxShadow = "";
        preview.style.height = "0";
        preview.style.opacity = "0";
      } else {
        gsap.to(card, {
          scale: 1,
          boxShadow: "0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1)",
          duration: 0.3,
          ease: "power2.out",
        });

        gsap.to(preview, {
          height: 0,
          opacity: 0,
          duration: 0.3,
          ease: "power2.out",
        });
      }
    };

    card.addEventListener("mouseenter", onEnter);
    card.addEventListener("mouseleave", onLeave);

    return () => {
      card.removeEventListener("mouseenter", onEnter);
      card.removeEventListener("mouseleave", onLeave);
    };
  }, []);

  // Extract clean content (backend already removed frontmatter)
  const cleanContent = doc.content
    .replace(/^#+\s+.*$/gm, "") // Remove headers
    .replace(/\[\[([^\]]+)\]\]/g, "$1") // Remove wikilink brackets
    .trim();

  const excerpt = cleanContent.substring(0, 120);
  const extendedPreview = cleanContent.substring(120, 320);

  return (
    <Card
      ref={cardRef}
      className={`cursor-pointer transition-colors ${
        isSelected ? "ring-2 ring-primary" : ""
      }`}
      onClick={() => onSelect(doc.id)}
    >
      <div className="p-4">
        <div className="flex items-start justify-between gap-2">
          <h3 className="font-medium line-clamp-2 flex-1">{doc.title}</h3>
          <Badge variant="secondary" className="shrink-0">
            {TYPE_LABELS[doc.doc_type] || doc.doc_type}
          </Badge>
        </div>

        {(doc.date_published || doc.source_author) && (
          <p className="mt-1 text-xs text-muted-foreground">
            {doc.date_published && new Date(doc.date_published).toLocaleDateString('en-US', { 
              year: 'numeric', 
              month: 'short', 
              day: 'numeric' 
            })}
            {doc.date_published && doc.source_author && ' • '}
            {doc.source_author}
          </p>
        )}

        <p className="mt-2 text-sm text-muted-foreground line-clamp-2">
          {excerpt || "No preview available"}
        </p>

        {doc.tags && doc.tags.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1">
            {doc.tags.slice(0, 3).map((tag) => (
              <Badge key={tag} variant="outline" className="text-xs">
                {tag}
              </Badge>
            ))}
            {doc.tags.length > 3 && (
              <Badge variant="outline" className="text-xs">
                +{doc.tags.length - 3}
              </Badge>
            )}
          </div>
        )}

        {/* Hover preview - hidden by default */}
        <div
          ref={previewRef}
          className="overflow-hidden opacity-0"
          style={{ height: 0 }}
        >
          <div className="mt-3 pt-3 border-t">
            <p className="text-xs text-muted-foreground line-clamp-4">
              {extendedPreview || ""}
            </p>
          </div>
        </div>

        {/* Connection indicator */}
        {(doc.wikilinks?.length || 0) + (doc.tags?.length || 0) > 0 && (
          <div className="mt-3 flex items-center gap-3 text-xs text-muted-foreground">
            {doc.wikilinks && doc.wikilinks.length > 0 && (
              <span className="flex items-center gap-1">
                <span className="text-blue-600">→</span>
                {doc.wikilinks.length} {doc.wikilinks.length === 1 ? "link" : "links"}
              </span>
            )}
          </div>
        )}
      </div>
    </Card>
  );
}
