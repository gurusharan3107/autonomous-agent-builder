import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export default function SetupPage() {
  const [features, setFeatures] = useState<any[]>([]);
  const [projectName, setProjectName] = useState("");
  const [stats, setStats] = useState({ total: 0, done: 0, pending: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());
  const [statusFilter, setStatusFilter] = useState<string>("all");

  const load = async () => {
    setLoading(true);
    try {
      const response = await fetch("/api/dashboard/features");
      const data = await response.json();
      setProjectName(data.project_name);
      setFeatures(data.features);
      setStats({ total: data.total, done: data.done, pending: data.pending });
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const toggleExpanded = (id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  if (error) {
    return (
      <div className="py-20 text-center">
        <div className="inline-flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3">
          <div className="h-2 w-2 rounded-full bg-destructive" />
          <p className="text-destructive text-sm font-medium">{error}</p>
        </div>
        <Button variant="ghost" size="sm" onClick={load} className="mt-3">
          Retry
        </Button>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="py-20 text-center">
        <div className="inline-flex gap-1">
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className="h-2 w-2 rounded-full bg-muted-foreground/30 animate-pulse"
              style={{ animationDelay: `${i * 150}ms` }}
            />
          ))}
        </div>
        <p className="text-sm text-muted-foreground mt-2">Loading project...</p>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{projectName}</h1>
        <p className="text-xs text-muted-foreground mt-1 font-mono tabular-nums">
          {stats.done} done · {stats.pending} pending · {stats.total} total
        </p>
      </div>

      <Separator />

      <div className="space-y-4">
        <section className="rounded-xl border bg-card shadow-sm">
          <div className="flex items-center justify-between p-5">
            <div className="flex items-center gap-3">
              <div className="h-2.5 w-2.5 rounded-full bg-status-active" />
              <h2 className="text-sm font-bold uppercase tracking-wider">
                Features
              </h2>
              <span className="font-mono text-xs font-semibold tabular-nums text-status-active">
                {features.filter((f) => {
                  if (statusFilter === "all") return true;
                  return f.status === statusFilter;
                }).length}
              </span>
            </div>
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger className="w-[140px] h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All</SelectItem>
                <SelectItem value="done">Done</SelectItem>
                <SelectItem value="pending">Pending</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="px-5 pb-5">
            {features.length === 0 ? (
              <div className="py-6 text-center text-sm text-muted-foreground rounded-lg bg-muted/30">
                No features yet
              </div>
            ) : (
              <div className="space-y-2">
                {features
                  .filter((f) => {
                    if (statusFilter === "all") return true;
                    return f.status === statusFilter;
                  })
                  .map((f) => {
                  const isExpanded = expandedIds.has(f.id);
                  return (
                    <div
                      key={f.id}
                      className="rounded-lg border border-border/50 bg-muted/20 transition-colors hover:bg-muted/40"
                    >
                      <button
                        onClick={() => toggleExpanded(f.id)}
                        className="w-full flex items-center justify-between px-4 py-3 text-left"
                      >
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-medium">
                            {f.id}: {f.title}
                          </p>
                        </div>
                        <div className="flex items-center gap-2 shrink-0 ml-4">
                          <Badge variant="outline" className="text-[10px] font-mono">
                            {f.priority}
                          </Badge>
                          <Badge
                            variant={f.status === "done" ? "secondary" : "default"}
                            className="text-[10px] uppercase tracking-wider"
                          >
                            {f.status}
                          </Badge>
                          <svg
                            className={`h-4 w-4 transition-transform ${
                              isExpanded ? "rotate-180" : ""
                            }`}
                            fill="none"
                            stroke="currentColor"
                            viewBox="0 0 24 24"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2}
                              d="M19 9l-7 7-7-7"
                            />
                          </svg>
                        </div>
                      </button>
                      {isExpanded && (
                        <div className="px-4 pb-3 pt-0 space-y-3">
                          <Separator className="mb-3" />
                          
                          {f.description && (
                            <div>
                              <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70 mb-1.5">
                                Description
                              </p>
                              <p className="text-[11px] text-muted-foreground leading-relaxed">
                                {f.description}
                              </p>
                            </div>
                          )}

                          {f.acceptance_criteria && f.acceptance_criteria.length > 0 && (
                            <div>
                              <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70 mb-1.5">
                                Acceptance Criteria
                              </p>
                              <ul className="space-y-1">
                                {f.acceptance_criteria.map((criterion: string, idx: number) => (
                                  <li key={idx} className="flex gap-2 text-[11px] text-muted-foreground">
                                    <span className="text-status-active shrink-0">•</span>
                                    <span className="leading-relaxed">{criterion}</span>
                                  </li>
                                ))}
                              </ul>
                            </div>
                          )}

                          {f.dependencies && f.dependencies.length > 0 && (
                            <div>
                              <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70 mb-1.5">
                                Dependencies
                              </p>
                              <div className="flex flex-wrap gap-1.5">
                                {f.dependencies.map((depId: string) => (
                                  <Badge
                                    key={depId}
                                    variant="outline"
                                    className="text-[10px] font-mono bg-muted/50"
                                  >
                                    {depId}
                                  </Badge>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
