# Knowledge Base UI Patterns - Visual Reference

This doc is the focused pattern reference for the `Knowledge` page. It inherits the authoritative rules from `design-language.md`, and makes the mockup direction concrete for implementation.

## Canonical Pattern

Knowledge is not a gallery. It is an explorer workspace:

```
┌───────────────┬──────────────────────┬──────────────────────────────┐
│ left rail     │ scan lane            │ reading pane                 │
│               │                      │                              │
│ scope         │ result list          │ selected document            │
│ search        │ dense summaries      │ readable prose               │
│ active tags   │ status/meta          │ related docs                 │
│ retrieval     │                      │                              │
│ state         │                      │                              │
└───────────────┴──────────────────────┴──────────────────────────────┘
```

## Layout Rules

### Left Rail

- Compact and calm
- Holds scope, search, filters, and lightweight retrieval state
- Should never be visually louder than the selected document

### Scan Lane

- Dense vertical list, not card gallery
- Each item should show: type, title, short excerpt, small metadata, minimal tag context
- Hover can add slight lift, but scanability matters more than animation

### Reading Pane

- Persistent on desktop
- Drawer fallback on smaller screens
- Must render content as structured prose, not raw `pre`
- Related docs belong below or beside the document, secondary to the main reading surface

## Document Rendering Rules

- Headings must create visible editorial hierarchy
- Paragraphs should use constrained line length and generous line height
- Lists should read like product guidance, not terminal output
- Code blocks can remain monospace, but must be isolated inside their own framed container
- Metadata must stay compact and move out of the main reading flow

## Visual Hierarchy

### Loudest

- Selected document title
- Result list titles

### Medium

- Rail section titles
- Document subsection headings
- Scope/search labels

### Quiet

- Tags
- Doc-type pills
- Source metadata
- Link counts

If filters or metadata feel louder than the selected document, the page is wrong.

## Responsive Behavior

### Desktop

- Three columns: rail, scan lane, reading pane
- Reading pane stays visible while scanning results

### Tablet

- Rail can remain above or left depending on width
- Reading pane may compress but should remain readable

### Mobile

- Rail collapses into stacked controls
- Results remain primary
- Reading pane becomes a drawer / overlay

## Anti-Patterns

- Do not revert to a 3-column card gallery
- Do not hide the reading surface behind hover gimmicks
- Do not make related docs the main event
- Do not use large decorative empty states
- Do not render markdown-like content as a raw dump

## Reuse Beyond Knowledge

This pattern should also inform:

- Memory
- Approval review surfaces
- Future run-inspection / dead-letter / evidence pages

These pages can differ in detail, but they should reuse the same operating idea:
compact framing controls, dense scan lane, readable detail pane.
