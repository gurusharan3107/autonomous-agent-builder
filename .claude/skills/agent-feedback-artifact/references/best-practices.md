# agent-feedback-artifact — Best Practices

Conventions + defaults. Read once; SKILL.md's per-marker table is the quick-reference.

## Per-marker decisions
Decide on `origin` × `route` × summary-clarity from the wake payload — full rubric in SKILL.md "Per-marker action". Pull `details.mjs` only when you need `selector`/`rect`/`ui` for a code fix (each pull ≈ 50 ms + ~2 KB context — compounds over a session). `visibleText` (≤60 chars, `null` when == summary) disambiguates deictic phrases ("change this" + `visibleText:"PRs Merged"`).

## Reload flag
Default **`--reload`** (CSS hot-swap) — CSS is the dominant edit; worst case is one operator F5. `--reload-full` only for template/HTML/DOM-structure edits (resets JS state). No flag = reply only. Tier table → [`wake-bridge.md`](wake-bridge.md).

## Batching concurrent markers
A wake arriving mid-processing → fold into the same turn (~2× wall-clock on 3 markers). Collect all edits, then mark all done. Same element + conflicting intent → later wins; mark the earlier done "overridden by your follow-up". Mixed reload flags → `--reload-full` wins (widget escalates).

## Routing classifier (`agent-feedback-routing.mjs`)
Server attaches the route to every item; you don't call it. Routes: `no_worker_main_agent_direct` (style or work-request → main agent), `cheap_marker_worker` (default fallback), `deep_marker_worker` (data/calc → fresh worker). **Selector is evidence, not intent** — classify on comment text, never `data-*`/CSS classes. Mis-route → append keyword to `styleIntent`/`dataIntent`/`actionIntent` and re-test (append-only, grown by experience).

## Token/context efficiency
1. Wake payload first, details second — don't auto-pull "to be sure".
2. Reply < ~140 chars (shows in the widget status bar); long justification → chat/commit, not the reply.
3. Don't poll — wake is push (`fs.watch` → SSE). Looping `next.mjs` means the Monitor isn't armed; fix that.
4. Batch (above).

## Reply conventions (shows live in the widget status bar)
- **Reply = outcome/answer, never in-progress narration.** Don't `mark done` with "investigating…/analyzing…" — it contradicts the `done` status and tells the operator nothing. Still working → `mark <id> processing "…"` (heartbeat); `done` only with the result.
- **Question marker → answer it** in the reply (the answer itself, not "looking into it").
- Lead with the change: "VELOCITY → teal #00d4d4 via CSS hot-swap", not "applied the change". Name the file edited so the operator can audit.
- Override → name the winner; follow-up question → end with the prompt.

## Arg defaults
- Mutating CLIs (`dispatch`, `mark`) = HTTP clients → `--port` (default 4177) or `--url`; server must be running.
- Read-only/file scripts (`next`, `details`, `watch`, `closeout`, `preflight`) → `--root` (same serve-root as the server).
- Widget `QUEUE_ORIGIN` default `http://localhost:4177` — not `127.0.0.1` (WSL2 IPv6; see [`agent-handbook.md`](agent-handbook.md)).
