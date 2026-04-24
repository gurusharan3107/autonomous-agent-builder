# Agent Page Hierarchy

## Intent

The Agent page is an operator console.

The primary job is to keep the live transcript and composer dominant. Session recall and run evidence are supporting surfaces. They should be available quickly without competing with the active thread.

## Hierarchy

| Level | Surface | Role |
|------|---------|------|
| Primary | Transcript + composer | Read, decide, send next instruction |
| Secondary | Session framing strip | Show live state, model, continuity, fast actions |
| On-demand | Previous sessions inspector | Resume or review prior threads |
| On-demand | Session evidence inspector | Read session id, load, turns, token and cost state |

## Desktop

- Use a two-column operator layout.
- Left column stays dominant and owns the transcript plus composer.
- Right column stays narrow and sticky.
- Right column always shows a small framing summary.
- Previous sessions and session evidence open inside the right-column inspector, one at a time.
- Do not keep both support panels open at once.

## Mobile

- Keep the transcript and composer in the main flow.
- Move previous sessions and evidence into modal overlays.
- Use the same labels and content as desktop so the interaction changes, not the information model.

## Motion

| Surface | Motion | Notes |
|------|--------|-------|
| Page entrance | GSAP two-phase entrance | Transcript framing first, then support cards |
| Transcript entrance | `y: 24 -> 0`, `opacity: 0 -> 1`, `duration: 0.45` | Establishes thread-first hierarchy |
| Support cards | `y: 16 -> 0`, `opacity: 0 -> 1`, stagger `0.04` | Secondary surfaces arrive after transcript |
| Inspector reveal | `x: 8 -> 0`, `y: 16 -> 0`, `opacity: 0 -> 1`, `duration: 0.3` | Use only when sessions/evidence panel changes |

Rules:

- One orchestrated entrance on load.
- CSS handles idle states and button hover.
- GSAP handles transcript entrance and inspector reveal only.
- Target motion with `data-*` attributes.

## Content Rules

- Do not duplicate assistant output in the evidence lane.
- Session history is for resuming and scanning, not for becoming a second transcript.
- Evidence stays compact and factual.
- Reset session remains available, but visually secondary to sending the next prompt.
