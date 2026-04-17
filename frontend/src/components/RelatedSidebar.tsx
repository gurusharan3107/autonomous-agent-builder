import { useRef } from "react";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { X } from "lucide-react";
import { Button } from "@/components/ui/button";
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
    } else {
      gsap.to(sidebarRef.current, {
        x: isOpen ? 0 : "100%",
        duration: 0.4,
        ease: "power3.out",
      });

      gsap.to(backdropRef.current, {
        opacity: isOpen ? 1 : 0,
        duration: 0.3,
        onComplete: () => {
          if (backdropRef.current) {
            backdropRef.current.style.pointerEvents = isOpen ? "auto" : "none";
          }
        },
      });
    }
  }, [isOpen]);

  if (!doc) return null;

  const hasWikilinks = relatedDocs?.wikilinks && relatedDocs.wikilinks.length > 0;
  const hasBacklinks = relatedDocs?.backlinks && relatedDocs.backlinks.length > 0;
  const hasSimilar = relatedDocs?.similar && relatedDocs.similar.length > 0;
  const hasAnyRelated = hasWikilinks || hasBacklinks || hasSimilar;

  return (
    <>
      {/* Backdrop for mobile */}
      <div
        ref={backdropRef}
        className="fixed inset-0 bg-black/20 backdrop-blur-sm z-40 lg:hidden opacity-0 pointer-events-none"
        onClick={onClose}
      />

      {/* Sidebar */}
      <div
        ref={sidebarRef}
        className="fixed right-0 top-0 h-full w-full sm:w-96 bg-background border-l shadow-2xl overflow-y-auto z-50"
        style={{ transform: "translateX(100%)" }}
      >
        <div className="p-6 space-y-6">
          {/* Header */}
          <div className="flex items-start justify-between gap-3">
            <div className="flex-1 min-w-0">
              <h2 className="text-lg font-semibold line-clamp-2">{doc.title}</h2>
              <Badge variant="secondary" className="mt-2">
                {TYPE_LABELS[doc.doc_type] || doc.doc_type}
              </Badge>
            </div>
            <Button
              variant="ghost"
              size="icon"
              onClick={onClose}
              className="shrink-0"
            >
              <X className="h-4 w-4" />
            </Button>
          </div>

          <Separator />

          {/* Document Content */}
          <div className="prose prose-sm max-w-none">
            <pre className="whitespace-pre-wrap text-sm bg-muted p-4 rounded-lg max-h-96 overflow-y-auto">
              {doc.content}
            </pre>
          </div>

          <Separator />

          {!hasAnyRelated && (
            <p className="text-sm text-muted-foreground">
              No related documents found. This document has no wikilinks, backlinks, or similar topics.
            </p>
          )}

          {/* Outgoing Links (Wikilinks) */}
          {hasWikilinks && (
            <div>
              <h3 className="text-sm font-medium mb-3 flex items-center gap-2">
                <span className="text-blue-600">→</span>
                Links to ({relatedDocs.wikilinks.length})
              </h3>
              <div className="space-y-2">
                {relatedDocs.wikilinks.map((link) => (
                  <Card
                    key={link.id}
                    className="cursor-pointer hover:bg-accent/50 transition-colors"
                    onClick={() => onSelectDoc(link.id)}
                  >
                    <CardContent className="p-3">
                      <div className="flex items-start justify-between gap-2">
                        <p className="text-sm font-medium flex-1 line-clamp-2">
                          {link.title}
                        </p>
                        <Badge variant="outline" className="text-xs shrink-0">
                          {TYPE_LABELS[link.doc_type] || link.doc_type}
                        </Badge>
                      </div>
                      <p className="text-xs text-muted-foreground mt-1 line-clamp-2">
                        {link.content
                          .replace(/^---[\s\S]*?---/, "")
                          .replace(/^#+\s+.*$/gm, "")
                          .trim()
                          .substring(0, 80)}
                        ...
                      </p>
                    </CardContent>
                  </Card>
                ))}
              </div>
            </div>
          )}

          {/* Backlinks */}
          {hasBacklinks && (
            <div>
              <h3 className="text-sm font-medium mb-3 flex items-center gap-2">
                <span className="text-green-600">←</span>
                Referenced by ({relatedDocs.backlinks.length})
              </h3>
              <div className="space-y-2">
                {relatedDocs.backlinks.map((backlink) => (
                  <Card
                    key={backlink.id}
                    className="cursor-pointer hover:bg-accent/50 transition-colors"
                    onClick={() => onSelectDoc(backlink.id)}
                  >
                    <CardContent className="p-3">
                      <p className="text-sm font-medium line-clamp-2">
                        {backlink.title}
                      </p>
                      <p className="text-xs text-muted-foreground mt-1 line-clamp-2">
                        {backlink.content
                          .replace(/^---[\s\S]*?---/, "")
                          .replace(/^#+\s+.*$/gm, "")
                          .trim()
                          .substring(0, 80)}
                        ...
                      </p>
                    </CardContent>
                  </Card>
                ))}
              </div>
            </div>
          )}

          {/* Similar Documents */}
          {hasSimilar && (
            <div>
              <h3 className="text-sm font-medium mb-3 flex items-center gap-2">
                <span className="text-purple-600">≈</span>
                Related topics ({relatedDocs.similar.length})
              </h3>
              <div className="space-y-2">
                {relatedDocs.similar.map((similar) => (
                  <Card
                    key={similar.id}
                    className="cursor-pointer hover:bg-accent/50 transition-colors"
                    onClick={() => onSelectDoc(similar.id)}
                  >
                    <CardContent className="p-3">
                      <p className="text-sm font-medium line-clamp-2">
                        {similar.title}
                      </p>
                      {similar.shared_tags && similar.shared_tags.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-2">
                          <span className="text-xs text-muted-foreground">Shared:</span>
                          {similar.shared_tags.map((tag) => (
                            <Badge key={tag} variant="secondary" className="text-xs">
                              {tag}
                            </Badge>
                          ))}
                        </div>
                      )}
                      {similar.similarity_score && (
                        <p className="text-xs text-muted-foreground mt-1">
                          {Math.round(similar.similarity_score * 100)}% match
                        </p>
                      )}
                    </CardContent>
                  </Card>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
