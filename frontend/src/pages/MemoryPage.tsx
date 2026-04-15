import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { listMemories, getMemory } from "@/lib/api";
import type { MemoryEntry, MemoryType } from "@/lib/types";

const TYPE_STYLES: Record<MemoryType, { label: string; variant: "default" | "secondary" | "destructive" }> = {
  decision: { label: "Decision", variant: "default" },
  pattern: { label: "Pattern", variant: "secondary" },
  correction: { label: "Correction", variant: "destructive" },
};

export default function MemoryPage() {
  const [entries, setEntries] = useState<MemoryEntry[]>([]);
  const [expandedSlug, setExpandedSlug] = useState<string | null>(null);
  const [expandedContent, setExpandedContent] = useState<string>("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listMemories()
      .then(setEntries)
      .finally(() => setLoading(false));
  }, []);

  const grouped = entries.reduce<Record<string, MemoryEntry[]>>((acc, entry) => {
    const key = entry.type || "other";
    if (!acc[key]) acc[key] = [];
    acc[key].push(entry);
    return acc;
  }, {});

  const handleExpand = async (slug: string) => {
    if (expandedSlug === slug) {
      setExpandedSlug(null);
      setExpandedContent("");
      return;
    }
    setExpandedSlug(slug);
    const data = await getMemory(slug);
    setExpandedContent(data.content || "");
  };

  if (loading) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Agent Memory</h1>
          <p className="mt-1 text-sm text-muted-foreground">Loading...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Agent Memory</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Per-project decisions, patterns, and corrections the agent has learned.
        </p>
      </div>

      {entries.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            No memories recorded for this project yet.
          </CardContent>
        </Card>
      ) : (
        (["decision", "pattern", "correction"] as MemoryType[]).map((type) => {
          const items = grouped[type];
          if (!items || items.length === 0) return null;
          const style = TYPE_STYLES[type];

          return (
            <Card key={type}>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Badge variant={style.variant}>{style.label}s</Badge>
                  <span className="text-muted-foreground">({items.length})</span>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {items.map((entry) => (
                  <div key={entry.slug}>
                    <div
                      className="flex cursor-pointer items-center justify-between rounded-lg p-3 transition-colors hover:bg-accent/50"
                      onClick={() => handleExpand(entry.slug)}
                    >
                      <div className="space-y-1">
                        <p className="text-sm font-medium">{entry.title}</p>
                        <div className="flex items-center gap-2 text-xs text-muted-foreground">
                          <span>{entry.phase}</span>
                          <span>&middot;</span>
                          <span>{entry.entity}</span>
                          {entry.tags?.map((tag) => (
                            <Badge key={tag} variant="outline" className="text-xs">
                              {tag}
                            </Badge>
                          ))}
                        </div>
                      </div>
                      <span className="text-xs text-muted-foreground">{entry.date}</span>
                    </div>
                    {expandedSlug === entry.slug && (
                      <pre className="mx-3 mb-3 max-h-64 overflow-auto whitespace-pre-wrap rounded-lg bg-muted p-4 text-sm">
                        {expandedContent}
                      </pre>
                    )}
                  </div>
                ))}
              </CardContent>
            </Card>
          );
        })
      )}
    </div>
  );
}
