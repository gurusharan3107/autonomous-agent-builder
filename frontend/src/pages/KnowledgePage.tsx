import { useEffect, useState } from "react";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { KnowledgeCard } from "@/components/KnowledgeCard";
import { RelatedSidebar } from "@/components/RelatedSidebar";
import { TagCloud } from "@/components/TagCloud";
import { listKBDocs, searchKBDocs, getKBDoc, getRelatedDocs, getKBTags } from "@/lib/api";
import type { KBDocument, RelatedDocs, TagInfo } from "@/lib/types";

export default function KnowledgePage() {
  const [scope, setScope] = useState<"local" | "global">("local");
  const [docs, setDocs] = useState<KBDocument[]>([]);
  const [search, setSearch] = useState("");
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [selectedDoc, setSelectedDoc] = useState<KBDocument | null>(null);
  const [relatedDocs, setRelatedDocs] = useState<RelatedDocs | null>(null);
  const [tags, setTags] = useState<TagInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // Load tags
  useEffect(() => {
    getKBTags(scope)
      .then(setTags)
      .catch(() => setTags([]));
  }, [scope]);

  // Load documents
  useEffect(() => {
    setLoading(true);
    const params: { scope?: "local" | "global" } = { scope };

    if (search.length >= 2) {
      searchKBDocs(search, scope)
        .then((results) => {
          // Filter by selected tags if any
          if (selectedTags.length > 0) {
            return results.filter((doc) =>
              selectedTags.some((tag) => doc.tags?.includes(tag))
            );
          }
          return results;
        })
        .then(setDocs)
        .finally(() => setLoading(false));
    } else {
      listKBDocs(params)
        .then((results) => {
          // Filter by selected tags if any
          if (selectedTags.length > 0) {
            return results.filter((doc) =>
              selectedTags.some((tag) => doc.tags?.includes(tag))
            );
          }
          return results;
        })
        .then(setDocs)
        .finally(() => setLoading(false));
    }
  }, [search, selectedTags, scope]);

  const handleSelectDoc = async (id: string) => {
    const doc = await getKBDoc(id, scope);
    setSelectedDoc(doc);
    setSidebarOpen(true);

    // Load related documents
    try {
      const related = await getRelatedDocs(id, scope);
      setRelatedDocs(related);
    } catch {
      setRelatedDocs(null);
    }
  };

  const handleCloseSidebar = () => {
    setSidebarOpen(false);
    setSelectedDoc(null);
    setRelatedDocs(null);
  };

  const handleTagToggle = (tag: string) => {
    setSelectedTags((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag]
    );
  };

  return (
    <div className="relative space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Knowledge Base</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Agent-written documentation — ADRs, contracts, runbooks, and project context.
        </p>
      </div>

      {/* Search and Scope Selector */}
      <div className="flex items-center gap-3">
        <Select value={scope} onValueChange={(v) => setScope(v as "local" | "global")}>
          <SelectTrigger className="w-[140px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="local">Local</SelectItem>
            <SelectItem value="global">Global</SelectItem>
          </SelectContent>
        </Select>
        
        <Input
          placeholder="Search documents..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-xs"
        />
      </div>

      {/* Tag Cloud */}
      {tags.length > 0 && (
        <TagCloud
          tags={tags}
          selectedTags={selectedTags}
          onTagToggle={handleTagToggle}
        />
      )}

      {/* Document Grid */}
      {loading ? (
        <p className="text-sm text-muted-foreground">Loading...</p>
      ) : docs.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No documents found. {selectedTags.length > 0 && "Try removing some tag filters."}
        </p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {docs.map((doc) => (
            <KnowledgeCard
              key={doc.id}
              doc={doc}
              onSelect={handleSelectDoc}
              isSelected={selectedDoc?.id === doc.id}
            />
          ))}
        </div>
      )}

      {/* Related Sidebar */}
      <RelatedSidebar
        doc={selectedDoc}
        relatedDocs={relatedDocs}
        onSelectDoc={handleSelectDoc}
        onClose={handleCloseSidebar}
        isOpen={sidebarOpen}
      />
    </div>
  );
}
