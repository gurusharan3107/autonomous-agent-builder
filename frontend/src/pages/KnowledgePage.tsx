import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { listKBDocs, searchKBDocs, getKBDoc } from "@/lib/api";
import type { KBDocument, KBDocType } from "@/lib/types";

const TYPE_LABELS: Record<KBDocType, string> = {
  adr: "ADR",
  api_contract: "API Contract",
  schema: "Schema",
  runbook: "Runbook",
  context: "Context",
};

export default function KnowledgePage() {
  const [docs, setDocs] = useState<KBDocument[]>([]);
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState<string>("");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [expandedDoc, setExpandedDoc] = useState<KBDocument | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    const params: { doc_type?: string } = {};
    if (typeFilter) params.doc_type = typeFilter;

    if (search.length >= 2) {
      searchKBDocs(search)
        .then(setDocs)
        .finally(() => setLoading(false));
    } else {
      listKBDocs(params)
        .then(setDocs)
        .finally(() => setLoading(false));
    }
  }, [search, typeFilter]);

  const handleExpand = async (id: string) => {
    if (expandedId === id) {
      setExpandedId(null);
      setExpandedDoc(null);
      return;
    }
    setExpandedId(id);
    const doc = await getKBDoc(id);
    setExpandedDoc(doc);
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Knowledge Base</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Agent-written documentation — ADRs, contracts, runbooks, and project context.
        </p>
      </div>

      <div className="flex items-center gap-3">
        <Input
          placeholder="Search documents..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-xs"
        />
        <div className="flex gap-1">
          <Badge
            variant={typeFilter === "" ? "default" : "outline"}
            className="cursor-pointer"
            onClick={() => setTypeFilter("")}
          >
            All
          </Badge>
          {(Object.keys(TYPE_LABELS) as KBDocType[]).map((t) => (
            <Badge
              key={t}
              variant={typeFilter === t ? "default" : "outline"}
              className="cursor-pointer"
              onClick={() => setTypeFilter(t)}
            >
              {TYPE_LABELS[t]}
            </Badge>
          ))}
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            Documents ({docs.length})
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <p className="text-sm text-muted-foreground">Loading...</p>
          ) : docs.length === 0 ? (
            <p className="text-sm text-muted-foreground">No documents found.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Type</TableHead>
                  <TableHead>Title</TableHead>
                  <TableHead>Version</TableHead>
                  <TableHead>Created</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {docs.map((doc) => (
                  <>
                    <TableRow
                      key={doc.id}
                      className="cursor-pointer hover:bg-accent/50"
                      onClick={() => handleExpand(doc.id)}
                    >
                      <TableCell>
                        <Badge variant="secondary">
                          {TYPE_LABELS[doc.doc_type] || doc.doc_type}
                        </Badge>
                      </TableCell>
                      <TableCell className="font-medium">{doc.title}</TableCell>
                      <TableCell className="text-muted-foreground">
                        v{doc.version}
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {new Date(doc.created_at).toLocaleDateString()}
                      </TableCell>
                    </TableRow>
                    {expandedId === doc.id && expandedDoc && (
                      <TableRow key={`${doc.id}-content`}>
                        <TableCell colSpan={4}>
                          <pre className="mt-2 max-h-96 overflow-auto whitespace-pre-wrap rounded-lg bg-muted p-4 text-sm">
                            {expandedDoc.content}
                          </pre>
                        </TableCell>
                      </TableRow>
                    )}
                  </>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
