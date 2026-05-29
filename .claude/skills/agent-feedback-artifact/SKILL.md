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

Wake payload: `{id, route, summary, sentAt, createdAt, emittedAt}` (~250 chars).

| `route` field | What to do |
|---|---|
| `no_worker_main_agent_direct` + clear summary | Act directly. **Skip details.** |
| `no_worker_main_agent_direct` + vague summary | Pull details once via `agent-feedback-details.mjs <id> --root <root>` |
| `cheap_marker_worker` | Default fallback — usually means classifier missed a keyword. Act on summary; consider extending `agent-feedback-routing.mjs` |
| `deep_marker_worker` | Pull details. Spawn fresh-once worker if doing data/calc work |

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
