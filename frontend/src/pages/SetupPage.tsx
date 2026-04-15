import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  createProject,
  createFeature,
  listProjects,
  listFeatures,
} from "@/lib/api";
import type { ProjectResponse, FeatureResponse } from "@/lib/types";

const LANGUAGES = ["python", "java", "node", "go", "rust"] as const;

const PRIORITY_OPTIONS = [
  { value: "0", label: "P0 — Critical" },
  { value: "1", label: "P1 — High" },
  { value: "2", label: "P2 — Medium" },
  { value: "3", label: "P3 — Low" },
] as const;

function ProjectForm({ onCreated }: { onCreated: (p: ProjectResponse) => void }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [repoUrl, setRepoUrl] = useState("");
  const [language, setLanguage] = useState("python");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;

    setSubmitting(true);
    setError(null);
    createProject({
      name: name.trim(),
      description: description.trim(),
      repo_url: repoUrl.trim(),
      language,
    })
      .then((project) => {
        onCreated(project);
        setName("");
        setDescription("");
        setRepoUrl("");
        setLanguage("python");
      })
      .catch((err) => setError(err.message))
      .finally(() => setSubmitting(false));
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-semibold uppercase tracking-wider">
          New Project
        </CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label htmlFor="project-name" className="text-xs font-medium">
                Name
              </Label>
              <Input
                id="project-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="my-service"
                required
                maxLength={255}
                className="rounded-lg"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="project-language" className="text-xs font-medium">
                Language
              </Label>
              <Select value={language} onValueChange={setLanguage}>
                <SelectTrigger id="project-language" className="rounded-lg">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {LANGUAGES.map((lang) => (
                    <SelectItem key={lang} value={lang}>
                      {lang}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="project-repo" className="text-xs font-medium">
              Repository URL
            </Label>
            <Input
              id="project-repo"
              value={repoUrl}
              onChange={(e) => setRepoUrl(e.target.value)}
              placeholder="https://github.com/org/repo"
              className="rounded-lg"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="project-desc" className="text-xs font-medium">
              Description
            </Label>
            <Textarea
              id="project-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Brief project description"
              rows={2}
              className="rounded-lg resize-none"
            />
          </div>
          {error && (
            <div className="inline-flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2">
              <div className="h-1.5 w-1.5 rounded-full bg-destructive" />
              <p className="text-destructive text-xs font-medium">{error}</p>
            </div>
          )}
          <Button type="submit" size="sm" disabled={submitting || !name.trim()}>
            {submitting ? "Creating..." : "Create Project"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function FeatureForm({
  projectId,
  onCreated,
}: {
  projectId: string;
  onCreated: (f: FeatureResponse) => void;
}) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [priority, setPriority] = useState("1");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;

    setSubmitting(true);
    setError(null);
    createFeature(projectId, {
      title: title.trim(),
      description: description.trim(),
      priority: parseInt(priority, 10),
    })
      .then((feature) => {
        onCreated(feature);
        setTitle("");
        setDescription("");
        setPriority("1");
      })
      .catch((err) => setError(err.message))
      .finally(() => setSubmitting(false));
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <div className="grid grid-cols-1 md:grid-cols-[1fr_auto] gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="feature-title" className="text-xs font-medium">
            Title
          </Label>
          <Input
            id="feature-title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Add user authentication"
            required
            maxLength={255}
            className="rounded-lg"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="feature-priority" className="text-xs font-medium">
            Priority
          </Label>
          <Select value={priority} onValueChange={setPriority}>
            <SelectTrigger id="feature-priority" className="rounded-lg w-44">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {PRIORITY_OPTIONS.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="feature-desc" className="text-xs font-medium">
          Description
        </Label>
        <Textarea
          id="feature-desc"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="What should this feature do?"
          rows={2}
          className="rounded-lg resize-none"
        />
      </div>
      {error && (
        <div className="inline-flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2">
          <div className="h-1.5 w-1.5 rounded-full bg-destructive" />
          <p className="text-destructive text-xs font-medium">{error}</p>
        </div>
      )}
      <Button type="submit" size="sm" disabled={submitting || !title.trim()}>
        {submitting ? "Adding..." : "Add Feature"}
      </Button>
    </form>
  );
}

function ProjectCard({
  project,
  isSelected,
  onSelect,
}: {
  project: ProjectResponse;
  isSelected: boolean;
  onSelect: () => void;
}) {
  return (
    <Card
      className={`group cursor-pointer transition-all duration-200 hover:shadow-lg hover:-translate-y-0.5 ${
        isSelected ? "ring-2 ring-primary shadow-md" : ""
      }`}
      onClick={onSelect}
    >
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-2">
          <CardTitle className="text-sm font-semibold leading-tight">
            {project.name}
          </CardTitle>
          <Badge variant="outline" className="text-[10px] font-mono shrink-0">
            {project.language}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="pt-0 space-y-1.5">
        {project.description && (
          <p className="text-[11px] text-muted-foreground truncate">
            {project.description}
          </p>
        )}
        {project.repo_url && (
          <p className="text-[11px] text-muted-foreground font-mono truncate">
            {project.repo_url}
          </p>
        )}
        <p className="text-[10px] text-muted-foreground/60 font-mono tabular-nums">
          {new Date(project.created_at).toLocaleDateString()}
        </p>
      </CardContent>
    </Card>
  );
}

function FeatureList({
  projectId,
  projectName,
}: {
  projectId: string;
  projectName: string;
}) {
  const [features, setFeatures] = useState<FeatureResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    listFeatures(projectId)
      .then(setFeatures)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, [projectId]);

  const handleFeatureCreated = (feature: FeatureResponse) => {
    setFeatures((prev) => [feature, ...prev]);
  };

  return (
    <section className="rounded-xl border bg-card shadow-sm">
      <div className="flex items-center gap-3 p-5">
        <div className="h-2.5 w-2.5 rounded-full bg-status-active" />
        <h2 className="text-sm font-bold uppercase tracking-wider">
          Features
        </h2>
        <span className="text-xs text-muted-foreground font-mono">
          {projectName}
        </span>
        <span className="font-mono text-xs font-semibold tabular-nums text-status-active">
          {features.length}
        </span>
      </div>

      <div className="px-5 pb-5 space-y-4">
        <FeatureForm projectId={projectId} onCreated={handleFeatureCreated} />

        <Separator />

        {loading ? (
          <div className="py-6 text-center">
            <div className="inline-flex gap-1">
              {[0, 1, 2].map((i) => (
                <div
                  key={i}
                  className="h-2 w-2 rounded-full bg-muted-foreground/30 animate-pulse"
                  style={{ animationDelay: `${i * 150}ms` }}
                />
              ))}
            </div>
          </div>
        ) : error ? (
          <div className="py-4 text-center">
            <div className="inline-flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2">
              <div className="h-1.5 w-1.5 rounded-full bg-destructive" />
              <p className="text-destructive text-xs font-medium">{error}</p>
            </div>
            <Button variant="ghost" size="sm" onClick={load} className="mt-2">
              Retry
            </Button>
          </div>
        ) : features.length === 0 ? (
          <div className="py-6 text-center text-sm text-muted-foreground rounded-lg bg-muted/30">
            No features yet
          </div>
        ) : (
          <div className="space-y-2">
            {features.map((f) => (
              <div
                key={f.id}
                className="flex items-center justify-between rounded-lg border border-border/50 bg-muted/20 px-4 py-3 transition-colors hover:bg-muted/40"
              >
                <div className="min-w-0 space-y-0.5">
                  <p className="text-sm font-medium truncate">{f.title}</p>
                  {f.description && (
                    <p className="text-[11px] text-muted-foreground truncate">
                      {f.description}
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-2 shrink-0 ml-4">
                  <Badge variant="outline" className="text-[10px] font-mono">
                    P{f.priority}
                  </Badge>
                  <Badge
                    variant={f.status === "done" ? "secondary" : "default"}
                    className="text-[10px] uppercase tracking-wider"
                  >
                    {f.status}
                  </Badge>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

export default function SetupPage() {
  const [projects, setProjects] = useState<ProjectResponse[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);

  const load = () => {
    setLoading(true);
    listProjects()
      .then(setProjects)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
  }, []);

  const handleProjectCreated = (project: ProjectResponse) => {
    setProjects((prev) => [project, ...prev]);
    setSelectedId(project.id);
    setShowForm(false);
  };

  const selectedProject = projects.find((p) => p.id === selectedId);

  if (error && projects.length === 0) {
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

  return (
    <div className="space-y-5">
      <div className="flex items-baseline justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Project Setup</h1>
          <p className="text-xs text-muted-foreground mt-1 font-mono tabular-nums">
            {projects.length} project{projects.length !== 1 ? "s" : ""}
          </p>
        </div>
        <Button
          size="sm"
          variant={showForm ? "secondary" : "default"}
          onClick={() => setShowForm((s) => !s)}
        >
          {showForm ? "Cancel" : "New Project"}
        </Button>
      </div>

      <Separator />

      {showForm && (
        <ProjectForm onCreated={handleProjectCreated} />
      )}

      <div className="space-y-4">
        <section className="rounded-xl border bg-card shadow-sm">
          <div className="flex items-center gap-3 p-5">
            <div className="h-2.5 w-2.5 rounded-full bg-status-pending" />
            <h2 className="text-sm font-bold uppercase tracking-wider">
              Projects
            </h2>
            <span className="font-mono text-xs font-semibold tabular-nums text-status-pending">
              {projects.length}
            </span>
          </div>

          <div className="px-5 pb-5">
            {loading ? (
              <div className="py-8 text-center">
                <div className="inline-flex gap-1">
                  {[0, 1, 2].map((i) => (
                    <div
                      key={i}
                      className="h-2 w-2 rounded-full bg-muted-foreground/30 animate-pulse"
                      style={{ animationDelay: `${i * 150}ms` }}
                    />
                  ))}
                </div>
                <p className="text-sm text-muted-foreground mt-2">Loading projects...</p>
              </div>
            ) : projects.length === 0 ? (
              <div className="py-8 text-center text-sm text-muted-foreground rounded-lg bg-status-pending/5">
                No projects yet. Create one to get started.
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
                {projects.map((p) => (
                  <ProjectCard
                    key={p.id}
                    project={p}
                    isSelected={p.id === selectedId}
                    onSelect={() =>
                      setSelectedId((prev) => (prev === p.id ? null : p.id))
                    }
                  />
                ))}
              </div>
            )}
          </div>
        </section>

        {selectedProject && (
          <FeatureList
            projectId={selectedProject.id}
            projectName={selectedProject.name}
          />
        )}
      </div>
    </div>
  );
}
