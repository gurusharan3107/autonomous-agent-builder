# Agent Builder — Design Language

Authoritative reference for the dashboard's visual identity. Load before modifying any frontend page or component.

## Identity

**Tone:** Personal mission control for autonomous software delivery. Calm authority, clear system status, human-readable decisions. The product should feel more like a trusted operator workspace than a generic admin dashboard.

**Audience:** Senior engineers and technical operators reviewing autonomous agent pipelines. They value density, legibility, retrieval quality, and decision support over decoration.

**Foundation:** shadcn/ui Luma preset (Radix primitives, oklch color system, rounded geometry), but applied with a stronger opinionated shell: compact chrome, clear retrieval/workflow framing, and reading surfaces that feel editorial rather than raw.

**Canonical visual thesis:** controls frame the work, they do not compete with it. Every page should feel quiet when healthy and explicit when intervention is needed.

**Current product preference:** default to reduction. If a label, chip, helper sentence, or support box does not change a decision or unlock an action, remove it.

## Canonical Template

This is the default template for the app unless a page has a stronger, task-specific reason to diverge.

### Shell

```
Header (calm, compact)
  Brand left — nav center — utility right

Scroll state
  Only the centered nav pill becomes sticky
  At scroll top it returns to its original in-header position
  Utilities stay anchored in the header, not in the sticky layer

Main
  Page eyebrow
  Page title + short operator-facing subtitle
  Separator
  Primary working layout
```

### Primary Working Layout

The default app pattern is a framed operator workspace, not a free-floating card grid.

- Left rail: query framing, scope controls, filters, mode selection, lightweight context
- Center lane: dense list of results, tasks, runs, or items to scan
- Right lane: readable detail pane, evidence pane, thread, or selected record

This three-zone pattern is the canonical template for retrieval and review surfaces.

### Design Intent

- The left rail should be compact and calm.
- The center lane should optimize scanning, not decoration.
- The right lane should optimize reading and decision-making.
- The page should feel like one coordinated system, not a stack of unrelated widgets.
- Sticky behavior should preserve orientation, not duplicate chrome.

## App-Wide Principles

These principles apply across Agent, Board, Metrics, Knowledge, Memory, and Backlog.

### 1. Controls Frame Content

- Search, filters, tabs, and action buttons should sit around the work, not interrupt the work.
- Controls should be visually quieter than the selected content, task, or evidence.
- If the chrome is louder than the payload, the hierarchy is wrong.
- Healthy-state chrome should collapse to the minimum viable signal.

### 2. Reading Surfaces Are First-Class

- Long-form content, memories, knowledge articles, and approval threads must render as structured prose.
- Never present markdown-like or narrative content as a raw `pre` dump in the final UI.
- Good reading surfaces use width control, paragraph spacing, heading hierarchy, and restrained separators.

### 3. Remove Explanations That Repeat the Layout

- If the structure already communicates the purpose, do not add helper copy that restates it.
- Section intros like `Awaiting next prompt`, `Transcript stays primary`, or `Open one inspector at a time` should only exist if they change what the operator does next.
- Empty states should be short, factual, and action-adjacent.

### 4. Dense, Not Noisy

- Prefer compact rows, lists, and split panes over large empty cards.
- Density should improve scanability, not create clutter.
- Use whitespace to group meaning, not to simulate sophistication.

### 5. One System Status Language

- System state should be expressed consistently across the app using restrained status dots, mono metadata, and clear labels.
- Avoid inventing a different visual grammar for each page.
- Healthy state should feel quiet; warning and blocked state should be more explicit but still controlled.

### 6. Support Surfaces Stay Secondary

- Sessions, evidence, and side context are support surfaces, not co-equal canvases.
- Keep them in the right rail, drawer, or on-demand inspector until explicitly requested.
- Avoid “preview boxes” that summarize a support surface without enabling a real action.
- The transcript or primary work thread should dominate the page width and visual attention.

### 7. The Product Is the Interface

- Decorative icons, ornamental gradients, and novelty effects should not carry meaning.
- The meaningful objects are runs, tasks, memories, docs, costs, approvals, and decisions.
- The interface should make those objects legible with typography, spacing, and layout.

## Typography

| Role | Font | Weight | Size | Usage |
|------|------|--------|------|-------|
| Page title | SF Pro Display fallback stack | 600–700 | `text-[2.1rem]` to `text-[2.8rem]` | Shell titles, document titles, detail-pane headlines |
| Section title | SF Pro Text fallback stack | 600–700 | `text-[11px]` uppercase tracking-[0.18em] | Pane labels, pipeline sections, scan-lane groupings |
| Body text | SF Pro Text fallback stack | 400–500 | `text-sm` to `text-[15px]` | Descriptions, thread content, readable prose |
| Data values | JetBrains Mono Variable | 400–600 | `text-[11px]` | Costs, tokens, durations, task IDs, counts |
| Labels | SF Pro Text fallback stack | 500–600 | `text-[10px]–text-[11px]` uppercase tracking-[0.18em] | Table headers, KPI labels, badge text |
| Muted context | SF Pro Text fallback stack | 400 | `text-xs` | Breadcrumbs, feature names, timestamps |

**Rules:**
- All numeric/financial data uses `font-mono tabular-nums` — columns must align
- The primary UI face is the SF Pro style system stack with `Inter Variable` only as fallback, not as the designed personality
- Labels are uppercase with deliberate tracking — hierarchy comes from letter-spacing, rhythm, and whitespace, not extra ornament
- Never go below `text-[10px]` — readability floor

## Color System

### Base Palette

The app no longer uses a flat achromatic admin palette. The base is warm paper and ink:

- Background: warm off-white paper in light mode, warm charcoal in dark mode
- Card surfaces: lifted ivory light / softened charcoal dark
- Primary: inked charcoal, used sparingly for active controls and emphasis
- Accent: muted teal / sea-glass for selected states, health cues, and calm emphasis
- Borders: warm low-contrast separators, never cold gray strokes

### Status Palette

Five semantic colors. They stay restrained and semantic inside the warmer system rather than becoming decorative fills.

| Token | Hue | Meaning | Usage |
|-------|-----|---------|-------|
| `status-active` | 152 (green) | In progress, live, running | Active section dots, stepper progress, live indicator |
| `status-review` | 75 (amber) | Awaiting human action | Review section dots, pending approval badges |
| `status-pending` | 260 (blue) | Queued, not started | Pending section dots, human thread entries |
| `status-done` | 165 (teal) | Completed successfully | Done section dots, pass/approve indicators |
| `status-blocked` | 27 (red) | Failed, blocked, error | Blocked section dots, reject/fail indicators |

**Rules:**
- Status colors appear as dots, count labels, and subtle `bg-status-*/5` tints — never as the dominant paint on a whole page
- Accent teal is allowed for selection, shell health, and retrieval emphasis, but it should still stay quieter than the content itself
- Never let a semantic color become the main layout identity for a page — typography and spacing should carry the hierarchy first
- Always define both `:root` and `.dark` values when adding colors

## Layout

### Page Structure

```
Header (sticky, backdrop-blur, `h-[78px]`)
  Brand left — Nav center — Theme toggle right
Main (shell-framed, compact top offset, page-specific width)
  Page title + subtitle
  Separator
  Content
```

### Default Surface Pattern

For most pages, prefer:

```
Left rail (~300px)
Center lane (~430px)
Right detail pane (fluid, readable width)
```

Use this for:
- Knowledge
- Memory
- Approval/review surfaces
- Future logs / dead-letter / run inspection pages

### Page Archetypes

#### Knowledge + Memory

- Explorer layout, not gallery layout
- Compact filter rail
- Dense result list
- Persistent readable detail pane on desktop
- Drawer fallback on smaller screens

#### Agent

- Operator console, not blank chat canvas
- Session state, quick prompts, recent activity, and message surface should feel like one command workspace
- Use the new typography, spacing cadence, and shell treatment without turning the page into an explorer
- Put compact operational metrics inside the session-framing strip, not floating as disconnected header chrome
- Remove status headlines that do not change operator behavior
- Session actions should read as utilities: sessions, evidence, new session
- “New session” should be represented as a positive affordance (`+`), not a destructive trash/reset metaphor
- The right rail should show real inspector content or a minimal placeholder, not decorative explanatory cards

#### Board

- Lane-based operations view
- Emphasize active work and review bottlenecks
- Empty states should be compact, not large pastel wells

#### Metrics

- Chart-led evidence surface
- Summary metrics support the charts; they should not be the whole page

#### Backlog

- Structured ledger / program view
- More table-row rhythm, less “accordion stack in a card”

### Board Page

Vertical stack of collapsible pipeline sections. Each section:
- Header: status dot + title (uppercase) + count (mono, status-colored) + collapse toggle
- Body: responsive grid (`1 / md:2 / xl:3` columns) of task cards

### Metrics Page

KPI card grid (4-up) → Cost bar chart → Runs table. No sidebar.

### Approval Page

Single-column (max-w-3xl), linear flow: header → stepper → thread → gate results → agent runs → actions.

## Component Conventions

### Cards

- Cards are secondary containers, not the default page grammar
- Use when the content is truly self-contained
- Hover: subtle lift only (`shadow-lg` + `-translate-y-0.5`)
- Prefer rows, lists, panes, and ledgers before reaching for a card grid

### Explorer Panes

- Left rail and detail pane should feel like architectural surfaces, not modal afterthoughts
- Rounded containers are acceptable, but hierarchy must come from structure, not shadows
- Detail panes should support long reading sessions: generous line height, constrained measure, and clear subsection breaks

### Badges

| Variant | When |
|---------|------|
| `default` | Active status (planning, implementation, etc.) |
| `secondary` | Neutral status (pending, done, completed) |
| `destructive` | Error status (blocked, failed, capability_limit) |
| `outline` | Agent names, review-stage statuses |

Badge text: `text-[10px] uppercase tracking-wider` for status badges, `text-[10px] font-mono` for agent/data badges.

### Status Dots

Small colored circles (h-2 to h-2.5, rounded-full) using status palette. Used in:
- Section headers (with optional pulse animation for active)
- Stepper (progress indicator)
- Table status cells (inline before status text)
- Live indicator (with `animate-ping` overlay)
- Compact healthy-state utility pill collapsed form

### Utility Pills

Use small rounded pills for system health, message counts, assistant counts, model identity, and similar operator metadata.

- Default state: collapsed, icon-first, minimal width
- Hover state: expand to reveal label/value
- Use when the data is useful but should not dominate the hierarchy
- Keep them in a single family: same height, border treatment, and expansion behavior
- Prefer icon + number for counts, icon + short mono value for model/system identity
- Do not leave long-form labels permanently expanded in calm state
- Put utility pills near the surface they describe; avoid detached metric clusters

### Stepper (Phase Progress)

Horizontal dot-line sequence: `Plan → Design → Implement → Gates → PR → Build`

- Completed steps: `bg-status-active` dot + `text-status-active` label + filled connector
- Current step: `bg-status-active` dot with `ring-status-active/25` glow + `animate-ping` overlay
- Future steps: `bg-muted-foreground/25` dot + muted label + `bg-border` connector

### Tables

- Header: `text-[10px] uppercase tracking-wider` — same treatment as labels
- Cells: `text-[11px]` with `font-mono tabular-nums` for all numeric data
- Status column: colored dot + mono uppercase text (not a Badge — too heavy for table density)

### Loading States

Three-dot pulse animation, centered:
```tsx
<div className="inline-flex gap-1">
  {[0, 1, 2].map((i) => (
    <div key={i} className="h-2 w-2 rounded-full bg-muted-foreground/30 animate-pulse"
      style={{ animationDelay: `${i * 150}ms` }} />
  ))}
</div>
```

### Error States

Inline indicator with destructive border/background tint + dot:
```tsx
<div className="inline-flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3">
  <div className="h-2 w-2 rounded-full bg-destructive" />
  <p className="text-destructive text-sm font-medium">{message}</p>
</div>
```

## Animation Principles

| What | How | Why |
|------|-----|-----|
| Page entrance | GSAP two-phase: sections (0.45s, stagger 0.1) then cards (0.35s, stagger 0.04) | Creates reading hierarchy — sections frame, cards fill |
| Scroll reveals | GSAP ScrollTrigger on KPI cards, `once: true` | Single entrance, no replay on scroll-back |
| Live data | CSS `animate-ping` on active task dots | Always-on indicator, no JS cost |
| Section pulse | CSS `animate-status-pulse` on active section dot | Draws eye to where action is happening |
| Card hover | CSS `transition-all duration-200` (shadow + translateY) | Immediate feedback, no GSAP overhead |
| Chart bars | GSAP `fromTo` height 0→target, staggered delay | Data reveal feels like loading in |
| Utility pills | CSS width/opacity reveal on hover only | Quiet at rest, explicit on intent |
| Sticky nav | CSS opacity/translate reveal, no layout jump | Keeps orientation without duplicating header |

**Rules:**
- One orchestrated entrance per page load — not scattered micro-animations
- CSS for always-on and state transitions. GSAP for orchestrated entrances and scroll effects.
- Always `clearProps: "all"` on GSAP entrances — don't leave inline styles
- Target with `data-*` attributes, never Tailwind classes
- Sticky utility behavior should be reversible: when scroll returns to top, the element returns to its source position rather than leaving a second persistent shell

## Background

Subtle dot-grid (`radial-gradient`, 20px spacing) on body. Different opacity for light (5%) vs dark (3%). Creates depth without competing with content.

Use atmospheric depth sparingly:
- the shell can feel softer and more personal than the inner work surfaces
- inner panes should stay crisp and readable
- avoid decorative backgrounds inside the actual reading pane

## Anti-Patterns

| Do not | Do instead |
|--------|-----------|
| Colored left/top borders on cards or sections | Status dots + typography weight |
| Large colored backgrounds for status | Small dots + `bg-status-*/5` tints (max) |
| Multiple font families beyond Inter + JetBrains Mono | Two fonts is enough — differentiate with weight and case |
| Hex or hsl colors | oklch only — matches Luma system |
| Badge in every table cell | Reserve badges for primary identifiers; use dots + text for status |
| Decorative icons in headers | The data IS the interface — icons add clutter |
| Animated borders, gradients, or glow effects | Restrained motion — pulse dots and entrance staggers only |
| Card gallery as the default page layout | Use a rail + list + detail workspace |
| Raw `pre` blocks for knowledge or memory content | Render structured prose with readable hierarchy |
| Huge empty-state containers with pastel fills | Compact, neutral empty states with clear next action |
| A different layout grammar on every page | Reuse the same shell, status language, and reading logic |
| Repeating the same status in headline, chip, helper text, and sidecard | Keep one strongest expression and delete the rest |
| Destructive iconography for non-destructive actions | Use positive or neutral metaphors for additive/reset utilities |
| Sticky full-header clones | Only sticky the smallest orientation-critical unit |

## Canonical Reference

The `Knowledge` redesign mockup is the current canonical reference for the app's future direction:

- compact shell
- operator-left rail
- dense scan lane
- readable persistent detail pane
- quieter chrome than payload

The current `Agent` page iteration adds two canonical rules that should now generalize across the app:

- thread-first or content-first work surface wins over explanatory chrome
- compact hover-expand utility pills are preferred over permanently expanded status chips

When redesigning additional pages, move them toward this template unless the page has a specific operational need to differ.
