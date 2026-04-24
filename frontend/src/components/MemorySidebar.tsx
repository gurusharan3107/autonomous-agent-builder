import { useRef } from "react";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { X } from "lucide-react";
import { EditorialContent } from "@/components/EditorialContent";
import type { MemoryEntry, MemoryType } from "@/lib/types";

const TYPE_STYLES: Record<
  MemoryType,
  { label: string; variant: "default" | "secondary" | "destructive" }
> = {
  decision: { label: "Decision", variant: "default" },
  pattern: { label: "Pattern", variant: "secondary" },
  correction: { label: "Correction", variant: "destructive" },
};

interface MemorySidebarProps {
  entry: MemoryEntry | null;
  content: string;
  isOpen: boolean;
  onClose: () => void;
}

export function MemorySidebar({
  entry,
  content,
  isOpen,
  onClose,
}: MemorySidebarProps) {
  const sidebarRef = useRef<HTMLDivElement>(null);
  const backdropRef = useRef<HTMLDivElement>(null);

  useGSAP(() => {
    if (!sidebarRef.current || !backdropRef.current) return;

    const prefersReducedMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;

    if (prefersReducedMotion) {
      sidebarRef.current.style.transform = isOpen
        ? "translateX(0)"
        : "translateX(100%)";
      backdropRef.current.style.opacity = isOpen ? "1" : "0";
      backdropRef.current.style.pointerEvents = isOpen ? "auto" : "none";
      return;
    }

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
  }, [isOpen]);

  if (!entry) return null;

  const style = TYPE_STYLES[entry.type];

  return (
    <>
      <div
        ref={backdropRef}
        className="fixed inset-0 z-40 bg-black/20 opacity-0 backdrop-blur-sm pointer-events-none lg:hidden"
        onClick={onClose}
      />

      <div
        ref={sidebarRef}
        className="fixed right-0 top-0 z-50 h-full w-full overflow-y-auto px-4 py-4 sm:w-[36rem]"
        style={{ transform: "translateX(100%)" }}
      >
        <div className="detail-drawer-panel space-y-6">
          <div className="flex items-start justify-between gap-4">
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant={style.variant} className="text-[10px] uppercase tracking-[0.18em]">
                  {style.label}
                </Badge>
                {entry.status && (
                  <Badge variant="outline" className="text-[10px] uppercase tracking-[0.18em]">
                    {entry.status}
                  </Badge>
                )}
              </div>
              <div>
                <h2 className="text-2xl font-semibold tracking-tight">
                  {entry.title}
                </h2>
                <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
                  {entry.phase && <span>{entry.phase}</span>}
                  {entry.phase && entry.entity && <span>•</span>}
                  {entry.entity && <span>{entry.entity}</span>}
                  {entry.date && <span>•</span>}
                  {entry.date && <span>{entry.date}</span>}
                </div>
              </div>
            </div>

            <Button
              variant="ghost"
              size="icon"
              className="shrink-0"
              onClick={onClose}
            >
              <X className="h-4 w-4" />
            </Button>
          </div>

          {entry.tags && entry.tags.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {entry.tags.map((tag) => (
                <Badge key={tag} variant="outline">
                  {tag}
                </Badge>
              ))}
            </div>
          )}

          <Separator />

          <div className="space-y-3">
            <h3 className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
              Memory Content
            </h3>
            <EditorialContent content={content || "No content available for this memory."} />
          </div>
        </div>
      </div>
    </>
  );
}
