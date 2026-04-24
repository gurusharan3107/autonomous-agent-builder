import { useLayoutEffect, useMemo, useRef } from "react";
import gsap from "gsap";
import { Sparkles, Play, RotateCcw, GitBranch, FolderTree, Database } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { OnboardingStatus } from "@/lib/types";
import {
  PageFrame,
  PageHeader,
  SectionLabel,
  StatPill,
  SurfacePanel,
} from "@/components/workspace";

const PHASE_TONE: Record<string, string> = {
  pending: "border-border/70 bg-background/65 text-muted-foreground",
  running: "border-status-active/30 bg-status-active/8 text-foreground",
  passed: "border-status-done/25 bg-status-done/8 text-foreground",
  failed: "border-status-blocked/30 bg-status-blocked/10 text-foreground",
  blocked: "border-status-blocked/30 bg-status-blocked/10 text-foreground",
};

function PhaseBadge({ status }: { status: string }) {
  return (
    <span
      className={[
        "inline-flex rounded-full border px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em]",
        PHASE_TONE[status] ?? PHASE_TONE.pending,
      ].join(" ")}
    >
      {status}
    </span>
  );
}

export default function OnboardingPage({
  status,
  actionPending,
  onStart,
  onRetry,
}: {
  status: OnboardingStatus;
  actionPending: boolean;
  onStart: () => void;
  onRetry: () => void;
}) {
  const shellRef = useRef<HTMLDivElement | null>(null);
  const phasesRef = useRef<HTMLDivElement | null>(null);

  useLayoutEffect(() => {
    if (!shellRef.current) return;
    const ctx = gsap.context(() => {
      gsap.fromTo(
        shellRef.current?.querySelectorAll("[data-onboarding-animate]") ?? [],
        { opacity: 0, y: 28 },
        {
          opacity: 1,
          y: 0,
          duration: 0.65,
          ease: "power2.out",
          stagger: 0.06,
        },
      );
    }, shellRef);
    return () => ctx.revert();
  }, []);

  useLayoutEffect(() => {
    if (!phasesRef.current) return;
    const active = phasesRef.current.querySelector(`[data-phase-id="${status.current_phase}"]`);
    if (!active) return;
    gsap.fromTo(
      active,
      { scale: 0.985, boxShadow: "0 0 0 rgba(0,0,0,0)" },
      {
        scale: 1,
        boxShadow: "0 18px 50px rgba(15, 23, 42, 0.12)",
        duration: 0.45,
        ease: "power2.out",
      },
    );
  }, [status.current_phase, status.updated_at]);

  const running = useMemo(
    () => status.phases.some((phase) => phase.status === "running"),
    [status.phases],
  );
  const latestError = status.errors.at(-1);

  return (
    <PageFrame className="pt-2">
      <div
        ref={shellRef}
        className="surface-elevated relative overflow-hidden rounded-[2rem] border border-border/70 px-5 py-6 sm:px-7 lg:px-8"
      >
        <div data-onboarding-animate>
          <SectionLabel>First-run onboarding</SectionLabel>
          <PageHeader
            eyebrow="First-run onboarding"
            title={`Bring ${status.repo.name} under builder control.`}
            description="The dashboard is the operator entrypoint now. Start onboarding to archive legacy generated artifacts, seed builder-managed project state, and generate the first trustworthy local operating context."
            meta={
              <div className="flex flex-wrap items-center gap-2">
                <StatPill label="Repo" value={status.repo.name} />
                <StatPill label="Language" value={status.repo.language || "unknown"} />
                <StatPill label="Branch" value={status.repo.branch || "n/a"} />
              </div>
            }
          />
        </div>

        <div data-onboarding-animate className="mt-6 grid gap-4 lg:grid-cols-[minmax(0,1.15fr)_minmax(320px,0.85fr)]">
          <SurfacePanel className="space-y-4 border-border/70 bg-background/60">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Sparkles className="h-4 w-4 text-status-active" />
              <span>Onboarding creates the first operational snapshot for this repo.</span>
            </div>

            <div className="grid gap-3 sm:grid-cols-3">
              <div className="min-w-0 rounded-[1.25rem] border border-border/70 bg-background/70 p-4">
                <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">
                  <GitBranch className="h-3.5 w-3.5" />
                  Repo state
                </div>
                <p className="mt-3 text-sm text-foreground [overflow-wrap:anywhere]">{status.repo.root}</p>
                <p className="mt-2 text-xs text-muted-foreground">
                  {status.repo.dirty ? `${status.repo.status_lines} local changes detected` : "working tree clean"}
                </p>
              </div>
              <div className="min-w-0 rounded-[1.25rem] border border-border/70 bg-background/70 p-4">
                <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">
                  <FolderTree className="h-3.5 w-3.5" />
                  Seed targets
                </div>
                <p className="mt-3 text-sm text-foreground [overflow-wrap:anywhere]">
                  {status.entity_counts.projects} project · {status.entity_counts.features} features · {status.entity_counts.tasks} tasks
                </p>
                <p className="mt-2 text-xs text-muted-foreground">builder-managed state will replace legacy empty-shell behavior</p>
              </div>
              <div className="min-w-0 rounded-[1.25rem] border border-border/70 bg-background/70 p-4">
                <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">
                  <Database className="h-3.5 w-3.5" />
                  KB status
                </div>
                <p className="mt-3 text-sm text-foreground [overflow-wrap:anywhere]">{status.kb_status.message}</p>
                <p className="mt-2 text-xs text-muted-foreground [overflow-wrap:anywhere]">
                  {status.kb_status.document_count} knowledge docs prepared so far
                </p>
              </div>
            </div>

            <div className="rounded-[1.35rem] border border-border/70 bg-background/68 p-4">
              <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">What happens next</p>
              <div className="mt-3 grid gap-2 text-sm text-foreground sm:grid-cols-2">
                <div>1. Detect repo + archive legacy generated inputs</div>
                <div>2. Seed builder-managed project state</div>
                <div>3. Derive work items from deterministic scan</div>
                <div>4. Prepare project knowledge once the first scope is concrete</div>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <Button
                onClick={onStart}
                disabled={actionPending || running || status.ready}
                className="rounded-full"
              >
                <Play className="mr-2 h-4 w-4" />
                {status.started_at ? "Resume onboarding" : "Start onboarding"}
              </Button>
              <Button
                variant="outline"
                onClick={onRetry}
                disabled={actionPending || running}
                className="rounded-full"
              >
                <RotateCcw className="mr-2 h-4 w-4" />
                Retry failed phases
              </Button>
            </div>
          </SurfacePanel>

          <div ref={phasesRef}>
            <SurfacePanel className="space-y-3 border-border/70 bg-background/60">
              <SectionLabel>Pipeline phases</SectionLabel>
              {status.phases.map((phase) => (
                <div
                  key={phase.id}
                  data-phase-id={phase.id}
                  className="rounded-[1.35rem] border border-border/70 bg-background/65 p-4 transition-shadow"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold text-foreground">{phase.title}</p>
                      <p className="mt-1 text-sm text-muted-foreground">{phase.message || "Pending execution."}</p>
                    </div>
                    <PhaseBadge status={phase.status} />
                  </div>
                  {phase.error ? (
                    <p className="mt-3 rounded-2xl border border-status-blocked/25 bg-status-blocked/8 px-3 py-2 text-sm text-foreground">
                      {phase.error}
                    </p>
                  ) : null}
                </div>
              ))}
            </SurfacePanel>
          </div>
        </div>

        {latestError ? (
          <div data-onboarding-animate className="mt-5 rounded-[1.4rem] border border-status-blocked/25 bg-status-blocked/8 px-4 py-4 text-sm text-foreground">
            Latest issue: {latestError.error}
          </div>
        ) : null}
      </div>
    </PageFrame>
  );
}
