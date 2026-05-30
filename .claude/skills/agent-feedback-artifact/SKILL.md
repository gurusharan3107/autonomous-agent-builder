---
name: agent-feedback-artifact
description: "Use when the user wants in-page annotation widget on HTML artifacts,
  marker-local chat, or comment-triggered agent work. Add, serve, queue, and
  process marker feedback. Triggers: annotation, feedback, marker, artifact."
---

# Agent Feedback Artifact

Injects a managed annotation widget into an HTML artifact (static file or running web app), serves it through a local feedback server, and queues marker-scoped user comments as push-delivered agent work items.

> Self-validate after edits: `./scripts/validate.sh` from the skill directory.

## Delivery modes

| Mode | When | Delivery |
|---|---|---|
| **Static artifact** | Single HTML file | `add-agent-feedback.mjs` injects widget; `artifact-feedback-server.mjs` serves it |
| **Running app** | Live web app (devpulse, dashboards) | `hermes-chrome` extension popup toggle injects widget into live page — no app code change |

## Operating sequence

```
preflight → add widget → serve → arm Monitor → process markers → disarm Monitor → closeout
```

Full step-by-step + script invocations → [`references/operate.md`](references/operate.md).

**Always pass `--root <serve-root>`** to every queue/watch script. Use the same path you passed to `artifact-feedback-server.mjs`.

## Per-marker action (every wake notification)

Wake payload: `{id, markerId, route, status, url, origin, artifactTitle, artifactPath, summary, visibleText, sentAt, createdAt, emittedAt}` (~400–460 chars). `origin` ∈ `localhost | external | github | file | blocked | unknown` — derived from `url`. `visibleText` is the marked element's text (≤60 chars), dedup'd to `null` when identical to `summary` — disambiguates deictic comments ("change this", "make the number red"). Pre-decide the action from these fields before paying any round-trip.

Decision is `origin` × `route` × `summary clarity`:

| `origin` | `route` + summary | What to do |
|---|---|---|
| `localhost` | direct + clear ("make X red") | Act on the local app — file follows from URL/artifactPath. **Skip details.** |
| `localhost` | direct + vague, or any `cheap_marker_worker` | Pull details once for selector/rect/ui |
| `external` | direct/cheap + clear question | **Answer from summary + URL.** Skip details. |
| `external` | direct/cheap + vague | Pull details (selectedText, visibleText) |
| `github` | any | URL is the work target — fetch/inspect the linked repo, then answer or act |
| `file` | any | Static artifact mode — file path is in the URL |
| `blocked` | any | Surface as warning (`chrome://`, `about:`, `view-source:`) |
| any | `deep_marker_worker` | Pull details. Spawn fresh-once worker if doing data/calc work |

After applying the fix:
```
node scripts/agent-feedback-mark.mjs <id> done "reply" [--reload | --reload-full] --root <serve-root>
```
- `--reload` — CSS hot-swap (use for every CSS change; ~700 ms to visible)
- `--reload-full` — full page reload (use for HTML/template edits)
- *(no flag)* — reply only, no auto-refresh (question-only replies)

**Batch concurrent wakes into one turn** — ~2× wall-clock savings on 3 markers.

Rationale + reply conventions → [`references/best-practices.md`](references/best-practices.md).

## Load references on need

| When | Load |
|---|---|
| Step-by-step operating procedure | [`references/operate.md`](references/operate.md) |
| Diagnosing a runtime issue | [`references/optimize.md`](references/optimize.md) |
| Skill-specific defaults + conventions | [`references/best-practices.md`](references/best-practices.md) |
| Modifying or extending the skill itself | [`references/agent-handbook.md`](references/agent-handbook.md) |
| Wake adapter (Monitor / file-watch / Hermes) | [`references/wake-bridge.md`](references/wake-bridge.md) |
| CORS issues | [`references/cors-setup.md`](references/cors-setup.md) |
| Browser acceptance checklist | [`references/browser-acceptance.md`](references/browser-acceptance.md) |
| Widget HTML/CSS/JS internals | [`references/overlay.html`](references/overlay.html) (canonical source) |
| Headed browser testing for running-app mode | `hermes-chrome` skill (separate top-level skill) |
