import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
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
  const [selectedType, setSelectedType] = useState<MemoryType>("decision");

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

  const availableTypes = (["decision", "pattern", "correction"] as MemoryType[]).filter(
    (type) => grouped[type] && grouped[type].length > 0
  );

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
        <div className="space-y-4">
          <Tabs value={selectedType} onValueChange={(v) => setSelectedType(v as MemoryType)}>
            <TabsList>
              {availableTypes.map((type) => {
                const style = TYPE_STYLES[type];
                const count = grouped[type]?.length || 0;
                return (
                  <TabsTrigger key={type} value={type}>
                    {style.label}s ({count})
                  </TabsTrigger>
                );
              })}
            </TabsList>
          </Tabs>

          <div className="grid gap-3">
            {grouped[selectedType]?.map((entry) => (
              <Card key={entry.slug}>
                <CardContent className="p-4">
                  <div
                    className="cursor-pointer space-y-2"
                    onClick={() => handleExpand(entry.slug)}
                  >
                    <div className="flex items-start justify-between">
                      <div className="space-y-1 flex-1">
                        <p className="text-sm font-medium">{entry.title}</p>
                        <div className="flex items-center gap-2 text-xs text-muted-foreground">
                          {entry.phase && <span>{entry.phase}</span>}
                          {entry.phase && entry.entity && <span>·</span>}
                          {entry.entity && <span>{entry.entity}</span>}
                        </div>
                        {entry.tags && entry.tags.length > 0 && (
                          <div className="flex flex-wrap gap-1 mt-2">
                            {entry.tags.map((tag) => (
                              <Badge key={tag} variant="outline" className="text-[10px] px-1.5 py-0">
                                {tag}
                              </Badge>
                            ))}
                          </div>
                        )}
                      </div>
                      {entry.date && (
                        <span className="text-xs text-muted-foreground">{entry.date}</span>
                      )}
                    </div>
                    {expandedSlug === entry.slug && (
                      <pre className="mt-3 overflow-auto whitespace-pre-wrap rounded-lg bg-muted p-4 text-xs">
                        {expandedContent}
                      </pre>
                    )}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
