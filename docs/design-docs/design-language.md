# Agent Builder — Design Language

Authoritative reference for the dashboard's visual identity. Load before modifying any frontend page or component.

## Identity

**Tone:** Precision engineering control panel. Calm authority, not flashy. The UI should feel like monitoring a well-run system — quiet when things work, clear when they don't.

**Audience:** Senior engineers reviewing autonomous agent pipelines. They value density, scanability, and trust signals over decoration.

**Foundation:** shadcn/ui Luma preset (Radix primitives, oklch color system, rounded geometry).

## Typography

| Role | Font | Weight | Size | Usage |
|------|------|--------|------|-------|
| Page title | Inter Variable | 700 (bold) | `text-2xl` | One per page, top-left |
| Section title | Inter Variable | 700 (bold) | `text-sm` uppercase tracking-wider | Pipeline sections, card groups |
| Body text | Inter Variable | 400–500 | `text-sm` | Descriptions, thread content |
| Data values | JetBrains Mono Variable | 400–600 | `text-[11px]` | Costs, tokens, durations, task IDs, counts |
| Labels | Inter Variable | 500–600 | `text-[10px]–text-[11px]` uppercase tracking-wider | Table headers, KPI labels, badge text |
| Muted context | Inter Variable | 400 | `text-xs` | Breadcrumbs, feature names, timestamps |

**Rules:**
- All numeric/financial data uses `font-mono tabular-nums` — columns must align
- Labels are uppercase with `tracking-wider` — creates visual hierarchy through letter-spacing, not size
- Never go below `text-[10px]` — readability floor

## Color System

### Base Palette (Luma)

Luma's base is achromatic — all neutrals use `oklch(L 0 0)` (zero chroma). This keeps the UI calm and lets status colors carry semantic meaning.

- Background: near-white light / near-black dark
- Card surfaces: pure white light / slightly lifted dark
- Primary: near-black light / near-white dark (inverts across modes)
- All borders: low-contrast for subtlety

### Status Palette

Five semantic colors. Defined in oklch with separate light/dark values (muted in light, brighter in dark).

| Token | Hue | Meaning | Usage |
|-------|-----|---------|-------|
| `status-active` | 152 (green) | In progress, live, running | Active section dots, stepper progress, live indicator |
| `status-review` | 75 (amber) | Awaiting human action | Review section dots, pending approval badges |
| `status-pending` | 260 (blue) | Queued, not started | Pending section dots, human thread entries |
| `status-done` | 165 (teal) | Completed successfully | Done section dots, pass/approve indicators |
| `status-blocked` | 27 (red) | Failed, blocked, error | Blocked section dots, reject/fail indicators |

**Rules:**
- Status colors appear as small dots (2–2.5px), count labels, and subtle `bg-status-*/5` tints — never as large painted surfaces
- Never use status colors for borders, backgrounds, or card decorations — they signal meaning, not decoration
- Always define both `:root` and `.dark` values when adding colors

## Layout

### Page Structure

```
Header (sticky, backdrop-blur, h-14)
  Brand left — Nav center — Theme toggle right
Main (max-w-screen-xl, px-6, py-8)
  Page title + subtitle
  Separator
  Content
Footer (centered, text-xs, muted)
```

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

- Standard shadcn `Card` — no custom borders, no colored accents
- Hover: `shadow-lg` + `-translate-y-0.5` (subtle lift, 200ms transition)
- Overflow: `overflow-hidden` to contain child elements

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

**Rules:**
- One orchestrated entrance per page load — not scattered micro-animations
- CSS for always-on and state transitions. GSAP for orchestrated entrances and scroll effects.
- Always `clearProps: "all"` on GSAP entrances — don't leave inline styles
- Target with `data-*` attributes, never Tailwind classes

## Background

Subtle dot-grid (`radial-gradient`, 20px spacing) on body. Different opacity for light (5%) vs dark (3%). Creates depth without competing with content.

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
