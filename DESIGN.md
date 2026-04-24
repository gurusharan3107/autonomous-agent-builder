---
version: alpha
name: Autonomous Agent Builder
description: "An operator console with editorial calm where content is primary and chrome is conditional. The default system is warm paper, precise charcoal typography, quiet cobalt emphasis, and status color used as telemetry rather than decoration."
colors:
  background: "#FCFAF6"
  background-sunk: "#F6F4EF"
  surface: "#FFFEFB"
  surface-subtle: "#FBFAF6"
  surface-muted: "#F3F2ED"
  surface-raised: "#FFFFFF"
  on-surface: "#1E1A15"
  on-surface-2: "#47413A"
  on-surface-3: "#736E67"
  on-surface-muted: "#9C9792"
  outline: "#E1DDD8"
  outline-subtle: "#EDEBE7"
  outline-strong: "#C7C3BD"
  primary: "#075EA9"
  primary-soft: "#E1F0FF"
  primary-ink: "#003363"
  info: "#008DA7"
  warning: "#AD7D00"
  pending: "#5C79B6"
  success: "#298954"
  danger: "#CB473D"
  dark-background: "#0D1013"
  dark-background-sunk: "#07090C"
  dark-surface: "#13161A"
  dark-surface-subtle: "#191D22"
  dark-surface-muted: "#20252A"
  dark-surface-raised: "#171B1F"
  dark-on-surface: "#F3F2ED"
  dark-on-surface-2: "#CCCAC5"
  dark-on-surface-3: "#95928A"
  dark-on-surface-muted: "#6B6961"
  dark-primary: "#5EA8F9"
  dark-primary-soft: "#152F4B"
  dark-primary-ink: "#A7DCFF"
  dark-info: "#00C0DA"
  dark-warning: "#E7B551"
  dark-pending: "#91B1F1"
  dark-success: "#6DC88F"
  dark-danger: "#FF7B6C"
typography:
  display-xl:
    fontFamily: Newsreader
    fontSize: 48px
    fontWeight: 400
    lineHeight: 1
    letterSpacing: -0.022em
  headline-page:
    fontFamily: Newsreader
    fontSize: 40px
    fontWeight: 400
    lineHeight: 1.08
    letterSpacing: -0.022em
  headline-lg:
    fontFamily: Geist
    fontSize: 34px
    fontWeight: 600
    lineHeight: 1.05
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Geist
    fontSize: 26px
    fontWeight: 600
    lineHeight: 1.15
    letterSpacing: -0.02em
  title-lg:
    fontFamily: Geist
    fontSize: 20px
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: -0.02em
  body-lg:
    fontFamily: Geist
    fontSize: 17px
    fontWeight: 400
    lineHeight: 1.6
    letterSpacing: -0.005em
  body-md:
    fontFamily: Geist
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.6
    letterSpacing: -0.005em
  body-sm:
    fontFamily: Geist
    fontSize: 12.5px
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: -0.003em
  label-md:
    fontFamily: Geist
    fontSize: 13px
    fontWeight: 500
    lineHeight: 1
    letterSpacing: 0
  label-mono:
    fontFamily: Geist Mono
    fontSize: 11px
    fontWeight: 500
    lineHeight: 1
    letterSpacing: 0.14em
    fontFeature: "\"zero\", \"tnum\" 1, \"ss02\""
  eyebrow:
    fontFamily: Geist Mono
    fontSize: 10.5px
    fontWeight: 500
    lineHeight: 1
    letterSpacing: 0.18em
    fontFeature: "\"zero\", \"tnum\" 1, \"ss02\""
  stat-mono:
    fontFamily: Geist Mono
    fontSize: 34px
    fontWeight: 500
    lineHeight: 1
    letterSpacing: -0.02em
    fontFeature: "\"zero\", \"tnum\" 1, \"ss02\""
rounded:
  xs: 4px
  sm: 7px
  md: 10px
  lg: 16px
  xl: 24px
  full: 999px
spacing:
  xs: 4px
  sm: 8px
  md: 12px
  lg: 16px
  xl: 20px
  2xl: 24px
  3xl: 32px
  4xl: 40px
  control-gap: 8px
  card-gap: 16px
  section-gap: 24px
  page-gap: 40px
  shell-padding: 24px
  panel-padding: 20px
  compact-padding: 12px
elevation:
  canvas:
    borderColor: "{colors.outline-subtle}"
    boxShadow: "none"
  surface:
    borderColor: "{colors.outline}"
    boxShadow: "0 1px 2px rgba(30, 26, 21, 0.06), inset 0 1px 0 rgba(255, 255, 255, 0.6)"
  raised:
    borderColor: "{colors.outline}"
    boxShadow: "0 4px 14px -6px rgba(30, 26, 21, 0.10), inset 0 1px 0 rgba(255, 255, 255, 0.6)"
  overlay:
    borderColor: "{colors.outline}"
    boxShadow: "0 22px 60px -30px rgba(30, 26, 21, 0.35), inset 0 1px 0 rgba(255, 255, 255, 0.6)"
motion:
  duration-fast: 120ms
  duration-medium: 220ms
  duration-slow: 420ms
  easing-emphasized: "cubic-bezier(0.16, 1, 0.3, 1)"
  easing-standard: "cubic-bezier(0.65, 0, 0.35, 1)"
  pulse-ring:
    duration: 1800ms
    easing: "{motion.easing-emphasized}"
  breathe:
    duration: 2200ms
    easing: "{motion.easing-standard}"
  ambient-scan:
    duration: 3500ms
    easing: linear
  fade-up:
    duration: "{motion.duration-slow}"
    easing: "{motion.easing-emphasized}"
shadows:
  xs: "0 1px 0 rgba(30, 26, 21, 0.04)"
  sm: "0 1px 2px rgba(30, 26, 21, 0.06), inset 0 1px 0 rgba(255, 255, 255, 0.60)"
  md: "0 4px 14px -6px rgba(30, 26, 21, 0.10), inset 0 1px 0 rgba(255, 255, 255, 0.60)"
  lg: "0 22px 60px -30px rgba(30, 26, 21, 0.35), inset 0 1px 0 rgba(255, 255, 255, 0.60)"
themePresets:
  calm-paper:
    mode: light
    accentHue: "252"
    density: "1"
    radiusBase: 10px
    uiFont: Geist
    displayFont: Newsreader
  operator:
    mode: dark
    accentHue: "212"
    density: "0.82"
    radiusBase: 4px
    uiFont: Geist
    displayFont: Geist
  sage-studio:
    mode: light
    accentHue: "180"
    density: "1"
    radiusBase: 16px
    uiFont: Geist
    displayFont: Newsreader
  ember:
    mode: light
    accentHue: "28"
    density: "1.15"
    radiusBase: 14px
    uiFont: Geist
    displayFont: Newsreader
  midnight:
    mode: dark
    accentHue: "264"
    density: "0.82"
    radiusBase: 8px
    uiFont: Geist
    displayFont: Newsreader
  paper-mono:
    mode: light
    accentHue: "0"
    density: "1"
    radiusBase: 6px
    uiFont: Geist
    displayFont: Geist
components:
  app-shell:
    backgroundColor: "{colors.background}"
    textColor: "{colors.on-surface}"
    rounded: "{rounded.xl}"
    padding: "{spacing.shell-padding}"
  panel-surface:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface}"
    rounded: "{rounded.lg}"
    padding: "{spacing.panel-padding}"
  panel-surface-raised:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.on-surface}"
    rounded: "{rounded.lg}"
    padding: "{spacing.panel-padding}"
  nav-pill-track:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.full}"
    padding: 4px
  nav-pill-active:
    backgroundColor: "{colors.on-surface}"
    textColor: "{colors.surface}"
    typography: "{typography.label-md}"
    rounded: "{rounded.full}"
    height: 36px
    padding: 0 20px
  nav-pill-idle:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface-3}"
    typography: "{typography.label-md}"
    rounded: "{rounded.full}"
    height: 36px
    padding: 0 20px
  shell-header-full:
    backgroundColor: "rgba(252, 250, 246, 0.78)"
    textColor: "{colors.on-surface}"
    rounded: "{rounded.full}"
    padding: 12px 24px
  shell-header-condensed:
    backgroundColor: "rgba(252, 250, 246, 0)"
    textColor: "{colors.on-surface}"
    rounded: "{rounded.full}"
    padding: 8px 0
  utility-icon-button:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface-2}"
    typography: "{typography.label-mono}"
    rounded: "{rounded.full}"
    height: 36px
    width: 36px
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.surface}"
    typography: "{typography.label-md}"
    rounded: "{rounded.sm}"
    height: 32px
    padding: 0 12px
  button-outline:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface}"
    typography: "{typography.label-md}"
    rounded: "{rounded.sm}"
    height: 32px
    padding: 0 12px
  button-soft:
    backgroundColor: "{colors.primary-soft}"
    textColor: "{colors.primary-ink}"
    typography: "{typography.label-md}"
    rounded: "{rounded.sm}"
    height: 32px
    padding: 0 12px
  input-field:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface}"
    typography: "{typography.body-md}"
    rounded: "{rounded.sm}"
    padding: 0 12px
    height: 32px
  text-area:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface}"
    typography: "{typography.body-lg}"
    rounded: "{rounded.lg}"
    padding: "{spacing.panel-padding}"
  status-chip-active:
    backgroundColor: "{colors.primary-soft}"
    textColor: "{colors.info}"
    typography: "{typography.label-mono}"
    rounded: "{rounded.full}"
    padding: 0 8px
  status-chip-review:
    backgroundColor: "#F8EFD8"
    textColor: "{colors.warning}"
    typography: "{typography.label-mono}"
    rounded: "{rounded.full}"
    padding: 0 8px
  status-chip-pending:
    backgroundColor: "#E9EEFA"
    textColor: "{colors.pending}"
    typography: "{typography.label-mono}"
    rounded: "{rounded.full}"
    padding: 0 8px
  status-chip-done:
    backgroundColor: "#E4F2E9"
    textColor: "{colors.success}"
    typography: "{typography.label-mono}"
    rounded: "{rounded.full}"
    padding: 0 8px
  status-chip-blocked:
    backgroundColor: "#F8E5E2"
    textColor: "{colors.danger}"
    typography: "{typography.label-mono}"
    rounded: "{rounded.full}"
    padding: 0 8px
  metrics-bar:
    backgroundColor: "{colors.surface-muted}"
    rounded: "{rounded.full}"
    height: 4px
  metrics-bar-fill:
    backgroundColor: "{colors.info}"
    rounded: "{rounded.full}"
    height: 4px
  diff-added:
    backgroundColor: "#E8F4EC"
    textColor: "{colors.success}"
    typography: "{typography.label-mono}"
    padding: 2px 12px
  diff-removed:
    backgroundColor: "#F8E5E2"
    textColor: "{colors.danger}"
    typography: "{typography.label-mono}"
    padding: 2px 12px
---

## Overview
Autonomous Agent Builder should feel like a control room that learned restraint from editorial design. It is not glossy, futuristic chrome. It is composed, deliberate, and readable first. The dominant mood is warm paper and dark ink, with a single cool accent used to guide attention instead of claiming the whole screen.

The visual personality is "operator console with editorial calm." That means:

- content is king and chrome earns its right to stay visible
- operational information is dense but never noisy
- hierarchy comes from rhythm, tone, and typography before it comes from color
- telemetry colors mean state, not brand
- the serif voice appears only at moments of framing, narrative, and emphasis

When the operator is reading, scanning, or comparing, the interface should bias toward disappearance. Secondary controls, support metadata, and utility affordances should fade back until the operator needs them. Healthy state should feel quiet enough that the content plane is the dominant visual object.

The default expression is `calm-paper`: warm light surfaces, charcoal text, cobalt accent, rounded but not playful geometry, and quiet motion. The preset themes are legitimate variants of the same product language, not separate brands. They may shift hue, density, radius, and mode, but they should preserve the same underlying temperament.

## Colors
The core palette is built around near-white mineral paper, soft limestone borders, and dark espresso-charcoal text. Pure white is reserved for the most elevated surfaces. This keeps the product feeling tactile and human rather than sterile.

- **Backgrounds:** Use `background`, `background-sunk`, and the surface tiers to build depth through tonal contrast, not through colored fills.
- **Text:** `on-surface` is the primary reading color. `on-surface-2`, `on-surface-3`, and `on-surface-muted` step down in clear, measured intervals for metadata, help text, timestamps, and scaffolding.
- **Accent:** `primary` is a cool cobalt used for focused actions, selected states, and quiet system emphasis. It should feel precise, not promotional.
- **Status colors:** `info`, `warning`, `pending`, `success`, and `danger` are reserved for runtime state. They should appear as small indicators, chips, progress fills, and diff highlights. They should not wash entire screens.
- **Dark mode:** The dark theme is deep graphite rather than true black. It should feel authored, warm, and first-class, not like an inverted afterthought.

The page canvas should keep a subtle atmospheric treatment: a dotted grid and faint radial glows near the corners. Those ambient details should stay almost subliminal. If they become a visible pattern, they are too strong.

## Typography
Typography does most of the emotional work.

- **Newsreader** is the editorial voice. Use it for page titles, big framing lines, and occasional italic emphasis inside hero statements.
- **Geist** is the operational workhorse. Use it for navigation, body copy, cards, forms, and almost all interface furniture.
- **Geist Mono** is the systems voice. Use it for telemetry, IDs, chips, timestamps, logs, keyboard cues, metrics, and any place where tabular rhythm matters.

The contrast between serif framing and sans-serif execution is essential. The serif should feel rare and intentional. If too many surfaces use Newsreader, the product loses its operator discipline. If everything uses Geist, the product loses its authored calm.

Letterspacing is slightly tightened for reading text and deliberately expanded for mono labels. Eyebrows and section metadata should read like quiet machine labels rather than marketing overlines.

## Layout
The layout is a broad desktop workspace made of large, softly bordered surfaces floating on an open canvas. It should feel panoramic and calm rather than crowded.

- Use generous outer framing around the entire shell.
- Group content into large panels with consistent internal padding.
- Let borders, tonal steps, and measured whitespace define structure.
- Keep sidebars and secondary rails visually subordinate and collapse or fade them when they are not actively supporting a decision.
- Favor clear grid splits, especially two-column and three-column operator layouts.

The prototype uses a comfortable base density by default, with density presets that compress or relax the system without changing the core proportions. Even in compact mode, the UI should still feel intentional and breathable.

Capsule navigation is important. The main route switcher should feel like a quiet instrument panel floating above the content, not a traditional website navbar.

Header behavior follows a two-state model:

- At scroll top, the full header may appear: brand, nav, and utility controls.
- After the operator enters the page, the shell should reduce to the centered nav pill.
- In condensed state, the header background should become visually transparent so the page content remains visible behind the nav.
- Secondary header controls should fade out rather than detach into another persistent toolbar.

## Elevation & Depth
Depth is subtle and paper-like.

- Primary hierarchy comes from tonal layering: sunk canvas, standard surface, raised surface.
- Borders are hairline-soft and warm, never icy or high-contrast.
- Shadows are shallow, diffused, and mostly there to separate planes, not to create drama.
- Raised surfaces may use a stronger shadow, but only enough to imply separation.

The most active operational panels may carry a restrained scanning wash or pulse treatment. Motion-based depth should feel like a live system breathing, not a dashboard trying to impress.

## Shapes
The shape language is rounded with discipline.

- Small controls use tight radii.
- Cards and panels use medium-to-large radii.
- Navigation pills and status chips use fully rounded capsules.

Corners should feel softened for touch and calm, but never bubbly or consumer-social. If the UI begins to feel cute, the radius is too large or too universal.

## Components
Component behavior should preserve the design system's quiet hierarchy.

### Shell and Panels
The app shell is a large framed surface on a warm canvas. Interior panels are clean paper cards with light borders and restrained shadows. Dashed treatments can be used for empty states, support drawers, and optional scaffolding, but they should remain low-contrast.

The shell must privilege the page payload over the shell itself. Full header chrome is a top-of-page affordance, not a permanently competing layer. The condensed shell should behave like orientation scaffolding, not a second banner.

### Navigation
Primary navigation lives in a capsule track. The selected pill inverts to dark ink with light text. Unselected pills stay almost flat and rely on typography plus hover response, not aggressive fills.

The nav pill is the one header element allowed to persist during reading scroll. It should remain centered, calm, and compact.

### Utility Controls
Command, compare, inbox, system, theme, and similar tools should prefer icon form when their text is not necessary for immediate decision-making. Their expanded meaning can be revealed on hover, focus, or open state. Utility rows should not compete with route navigation or the page title.

### Buttons
Buttons should be short, compact, and precise. The system favors small heights and concise padding.

- Primary buttons use the cobalt accent.
- Outline buttons are the default neutral action.
- Soft buttons use tinted accent backgrounds for secondary emphasis.

Destructive actions should use the danger tone directly and sparingly.

### Inputs and Writing Surfaces
Inputs should feel integrated with the paper system: white or near-white interiors, clear borders, and modest rounding. Text areas for prompts or logs should have more generous padding and feel like framed composition spaces.

### Status and Telemetry
Status chips, dots, progress meters, log lines, and diff blocks are where color becomes vivid. Each state color should be paired with a pale tonal background so the signal is legible without shouting. Active states may pulse or breathe. Review states should glow amber. Blocked states may use hatching or red-tinted diff treatments.

### Data Surfaces
Metrics, confidence indicators, costs, task IDs, gates, and timestamps should lean on mono typography and aligned rhythm. Numeric interfaces should feel trustworthy and measured.

## Do's and Don'ts
- Do keep the default mood calm, literate, and operational.
- Do let the content plane win over persistent shell chrome.
- Do use the serif only for framing, not for dense utility content.
- Do reserve saturated color for action focus and runtime state.
- Do let borders, spacing, and tonal layering carry most of the hierarchy.
- Do keep motion purposeful: pulse for liveness, scan for active processing, fade-up for entrance.
- Do collapse, fade, or defer secondary UI when it is not helping the operator decide or act.
- Don't turn the accent into a full-screen brand wash.
- Don't use heavy shadows, glassmorphism, neon, or high-gloss effects.
- Don't let status colors become decorative.
- Don't keep support metadata, pills, or utility text visible just because space exists.
- Don't mix playful radii with hard-edged terminal styling on the same screen unless a preset explicitly calls for it.
- Don't make dark mode feel like a simple inversion of light mode.
