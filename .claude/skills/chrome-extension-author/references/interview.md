# Interview — the AskUserQuestion script

The interview gathers everything needed to scaffold the extension without making a single architectural assumption silently. Each question maps to a specific scaffolding decision; the agent should never invent answers, but it MAY skip a question whose answer is unambiguous from the operator's typed prompt (e.g., "build a Chrome extension that streams page text to a local Python tool" → native messaging = yes).

## Batch policy

The skill issues at most 4 questions per `AskUserQuestion` call (the tool's hard cap). Group them into two batches:

- **Batch A — Core architecture** (questions 1–4): purpose, architecture pieces, visual presence, native messaging.
- **Batch B — Surface details** (questions 5–8): icon style, permissions scope, storage, lifecycle trigger.

If the operator's free-form description already names a piece (e.g., "popup-only", "no UI"), pre-fill that answer mentally and only ask the others.

---

## Batch A — Core architecture

### Q1 — Primary purpose

```python
{
  "question": "What does this extension do for the operator? One sentence.",
  "header": "Purpose",
  "multiSelect": False,
  "options": [
    {"label": "Page interaction / form fill",
     "description": "Read or modify content on web pages the operator visits."},
    {"label": "Data extraction / scraping",
     "description": "Capture text, tables, or DOM structure from pages into a usable format."},
    {"label": "UI overlay on existing pages",
     "description": "Add a floating panel, sidebar, or annotation layer on top of pages."},
    {"label": "Agent automation bridge",
     "description": "Let an external agent drive Chrome (clicks, navigation, screenshots) via native messaging."}
  ]
}
```

*Maps to:* the extension's `name` + `description` in `manifest.json`. Operator's *Other* free-text becomes the description verbatim.

### Q2 — Architecture pieces

```python
{
  "question": "Which architecture pieces does the extension need?",
  "header": "Pieces",
  "multiSelect": True,
  "options": [
    {"label": "Service worker (background)",
     "description": "Always-included on MV3. Handles message routing, alarms, tab events."},
    {"label": "Content scripts (injected per page)",
     "description": "Read or modify the DOM of web pages the operator visits."},
    {"label": "Popup UI",
     "description": "Small window that opens when the operator clicks the extension icon."},
    {"label": "Native messaging host",
     "description": "Local OS-side process (Python/Node/etc.) for file/shell/IPC the extension itself cannot do."}
  ]
}
```

*Maps to:* which template files get copied. Service worker is always scaffolded; the rest are conditional.

### Q3 — Visual presence

```python
{
  "question": "How should the operator see the extension is active?",
  "header": "Presence",
  "multiSelect": False,
  "options": [
    {"label": "Badge on extension icon (Recommended)",
     "description": "Number / dot on the toolbar icon. Lowest-friction, no DOM intrusion."},
    {"label": "Floating overlay cursor on page",
     "description": "Animated cursor that shows where the agent / extension is acting. Triggers the full hermes-chrome cursor patterns."},
    {"label": "Toast notifications in the page",
     "description": "Slide-in messages near a page corner. Visible but disruptive if frequent."},
    {"label": "None — silent operation",
     "description": "Extension acts entirely in the background. Operator sees results in their own UI."}
  ]
}
```

*Maps to:* whether `visual-presence.md` patterns are folded into the scaffold. *Floating overlay cursor* additionally copies the cursor-agent.js template hardened with the hermes-chrome fixes.

### Q4 — Native messaging required

```python
{
  "question": "Does the extension need to talk to a local OS-side process?",
  "header": "Native host",
  "multiSelect": False,
  "options": [
    {"label": "No",
     "description": "Pure browser-only. Skip the native host."},
    {"label": "Yes — for file system access",
     "description": "The extension needs to read or write files the browser can't reach."},
    {"label": "Yes — for shell / external process control",
     "description": "The extension needs to run local commands or talk to another local service."},
    {"label": "Yes — for an agent / IPC bridge",
     "description": "An external agent drives the extension; both sides speak through the native host."}
  ]
}
```

*Maps to:* whether `templates/native-host.py.template` + `templates/native-host.json.template` are scaffolded. Any "Yes" triggers the Unix-socket + line-delimited-JSON pattern proven in hermes-chrome.

---

## Batch B — Surface details

### Q5 — Icon style

```python
{
  "question": "What style for the extension icon set?",
  "header": "Icon style",
  "multiSelect": False,
  "options": [
    {"label": "Minimal mono-glyph",
     "description": "Single shape (circle, square, arrow) on flat background. Best for utility extensions.",
     "preview": "  ●\n  Single shape, single color. Reads at 16px."},
    {"label": "Detailed pictogram",
     "description": "Recognizable object (gear, eye, bridge). Two-color, more visual identity.",
     "preview": "  ⚙\n  Detailed at 48/128px; degrades at 16px."},
    {"label": "Animated cursor / pointer",
     "description": "Stylized cursor with motion. Use ONLY if the extension has an on-page cursor presence (Q3).",
     "preview": "  ➤ (with subtle pulse)\n  Animated SVG; matches in-page cursor."},
    {"label": "Branded text mark",
     "description": "1–3 letter monogram in a custom typeface. For extensions with a strong brand.",
     "preview": "  XY\n  Monogram; legible at 32px+."}
  ]
}
```

*Maps to:* which `templates/icon-*.svg` source is copied as `extension/images/icon.svg`. The icon-design reference then generates the 16/32/48/128 PNG pack at scaffold time.

### Q6 — Permissions scope

```python
{
  "question": "How broad should the page-access permissions be?",
  "header": "Permissions",
  "multiSelect": False,
  "options": [
    {"label": "activeTab only (Recommended)",
     "description": "Access the current tab only when the operator clicks the icon. Minimum privilege, no install warning."},
    {"label": "Specific host(s)",
     "description": "Named host patterns (e.g., '*://*.devpulse.local/*'). Some install warning."},
    {"label": "all_urls",
     "description": "Every page the operator visits. Loud install warning. Only if the extension is genuinely universal."}
  ]
}
```

*Maps to:* the `permissions` + `host_permissions` arrays in `manifest.json`. The skill MUST warn the operator if Q1 (purpose) doesn't justify `all_urls`.

### Q7 — Storage

```python
{
  "question": "Does the extension need to persist state across sessions?",
  "header": "Storage",
  "multiSelect": False,
  "options": [
    {"label": "None",
     "description": "Stateless. Everything is computed each time."},
    {"label": "chrome.storage.local (Recommended)",
     "description": "Extension-scoped key-value store. Survives reloads; cleared on uninstall."},
    {"label": "localStorage (per-page)",
     "description": "Page-scoped, only useful for content scripts. The skill auto-includes the safeParseArray defensive pattern if chosen."},
    {"label": "IndexedDB",
     "description": "For large structured data. Heavier API; only choose if you actually need it."}
  ]
}
```

*Maps to:* the `permissions` array (`"storage"`) and which defensive-parse pattern is included. Any storage choice triggers the `safeParseArray` template; IndexedDB additionally pulls in an `idb.js` wrapper.

### Q8 — Lifecycle trigger

```python
{
  "question": "When should the extension's content scripts run?",
  "header": "Lifecycle",
  "multiSelect": False,
  "options": [
    {"label": "Auto on every page navigation",
     "description": "Service worker injects on `tabs.onUpdated`. For always-present extensions (overlays, monitors)."},
    {"label": "Only when the operator clicks the icon",
     "description": "Single-use per session. Lowest footprint."},
    {"label": "Only when an external trigger fires",
     "description": "Agent / native host requests injection via message. For agent-driven extensions."},
    {"label": "On a schedule (chrome.alarms)",
     "description": "Periodic background work. Service-worker-friendly; no persistent timer."}
  ]
}
```

*Maps to:* the SW's `chrome.tabs.onUpdated` handler shape (or its absence). Auto-on-navigation gets the full re-inject pattern from hermes-chrome.

---

## After the interview

Once all answers are collected, the agent:

1. Echoes the choices back to the operator in a short summary table — "here's what I'm about to scaffold."
2. Names the target directory (default `extensions/<name>/`) and asks for confirmation.
3. Proceeds to the **Plan → Scaffold → Verify** phases described in [`operate.md`](operate.md).

If the operator picks the *Other* option on any question, the agent treats that input as overriding the default mapping; if the *Other* input is incompatible with another answer (e.g., "no UI" + "popup UI"), the agent asks one clarifying question rather than scaffolding the conflict.
